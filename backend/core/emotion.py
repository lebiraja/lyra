"""Emotion detection: FER (face) + SER (voice) + fusion + prompt context.

All models run CPU-only — zero GPU VRAM impact.
Gracefully degrades: any component can be None without breaking the pipeline.
"""

from __future__ import annotations

import base64
import io
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Canonical label set used for prompt injection (superset mapped down to these).
CANONICAL_LABELS = ("neutral", "happy", "sad", "angry", "fearful", "surprised", "disgusted", "contempt")

# Mapping from various model label sets to our canonical labels.
_LABEL_MAP: dict[str, str] = {
    "calm": "neutral",
    "disgust": "disgusted",
    "fear": "fearful",
    "surprise": "surprised",
    "anger": "angry",
    "happiness": "happy",
    "sadness": "sad",
}


def _normalize_label(raw: str) -> str:
    raw = raw.lower().strip()
    return _LABEL_MAP.get(raw, raw if raw in CANONICAL_LABELS else "neutral")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EmotionState:
    label: str = "neutral"
    confidence: float = 0.0
    valence: float = 0.0   # -1.0 (negative) to +1.0 (positive)
    arousal: float = 0.0   # 0.0 (calm) to 1.0 (activated)
    source: str = "none"   # "face", "voice", "fused", "voice_only"

    def with_source(self, source: str) -> EmotionState:
        return EmotionState(self.label, self.confidence, self.valence, self.arousal, source)


# Valence/arousal lookup for canonical labels (empirical defaults from AffectNet).
_VALENCE_AROUSAL: dict[str, tuple[float, float]] = {
    "neutral":   ( 0.0,  0.1),
    "happy":     ( 0.8,  0.6),
    "sad":       (-0.7,  0.2),
    "angry":     (-0.6,  0.8),
    "fearful":   (-0.5,  0.7),
    "surprised": ( 0.2,  0.8),
    "disgusted": (-0.6,  0.4),
    "contempt":  (-0.4,  0.3),
}

EMPTY_EMOTION = EmotionState()


# ---------------------------------------------------------------------------
# Speech Emotion Recognition (SER) — wav2vec2-base, CPU
# ---------------------------------------------------------------------------

class SpeechEmotionRecognizer:
    """wav2vec2-base finetuned for speech emotion recognition. CPU-only, blocking."""

    def __init__(self, model_id: str = "superb/wav2vec2-base-superb-er") -> None:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        logger.info("Loading SER model: %s", model_id)
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(model_id)
        self.model = AutoModelForAudioClassification.from_pretrained(model_id)
        self.model.eval()
        self.model.to("cpu")
        self.labels: list[str] = list(self.model.config.id2label.values())
        self._torch = torch
        logger.info("SER ready — %d classes: %s", len(self.labels), self.labels)

    def predict(self, audio: np.ndarray, sample_rate: int = 16000) -> EmotionState:
        """Classify emotion from a speech clip. `audio` is float32 mono."""
        if audio.size < sample_rate * 0.5:
            return EMPTY_EMOTION

        inputs = self.feature_extractor(
            audio, sampling_rate=sample_rate, return_tensors="pt", padding=True
        )
        with self._torch.no_grad():
            logits = self.model(**inputs).logits

        probs = self._torch.nn.functional.softmax(logits, dim=-1)[0]
        idx = int(probs.argmax())
        raw_label = self.labels[idx]
        label = _normalize_label(raw_label)
        confidence = float(probs[idx])
        valence, arousal = _VALENCE_AROUSAL.get(label, (0.0, 0.0))

        return EmotionState(
            label=label,
            confidence=confidence,
            valence=valence,
            arousal=arousal,
            source="voice",
        )


# ---------------------------------------------------------------------------
# Facial Expression Recognition (FER) — EmotiEffNet-B0 ONNX, CPU
# ---------------------------------------------------------------------------

class FacialEmotionRecognizer:
    """MediaPipe face detection + EmotiEffNet-B0 ONNX for facial emotion. CPU-only."""

    def __init__(self) -> None:
        try:
            from hsemotion_onnx import HSEmotionRecognizer
            logger.info("Loading FER model: EmotiEffNet-B0 (ONNX)")
            self._recognizer = HSEmotionRecognizer(model_name="enet_b0_8_best_afew")
            logger.info("FER ready")
        except Exception:
            logger.exception("FER model load failed — facial emotion disabled")
            raise

    def predict_from_jpeg(self, jpeg_bytes: bytes) -> EmotionState | None:
        """Classify emotion from a JPEG-encoded frame. Returns None if no face found."""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            frame = np.array(img)
        except Exception:
            return None

        return self._predict_frame(frame)

    def predict_from_base64(self, b64_data: str) -> EmotionState | None:
        """Classify from a base64-encoded JPEG string."""
        try:
            jpeg_bytes = base64.b64decode(b64_data)
        except Exception:
            return None
        return self.predict_from_jpeg(jpeg_bytes)

    def _predict_frame(self, frame: np.ndarray) -> EmotionState | None:
        """Run FER on an RGB numpy frame (H, W, 3)."""
        try:
            emotion, scores = self._recognizer.predict_emotions(frame, logits=False)
        except Exception:
            return None

        if emotion is None or scores is None:
            return None

        label = _normalize_label(str(emotion))
        confidence = float(max(scores)) if scores is not None else 0.0
        valence, arousal = _VALENCE_AROUSAL.get(label, (0.0, 0.0))

        return EmotionState(
            label=label,
            confidence=confidence,
            valence=valence,
            arousal=arousal,
            source="face",
        )


# ---------------------------------------------------------------------------
# Emotion Buffer — sliding window for FER results
# ---------------------------------------------------------------------------

class EmotionBuffer:
    """Ring buffer of recent FER readings. Snapshot via majority vote at VAD boundary."""

    def __init__(self, max_size: int = 5) -> None:
        self._buf: deque[EmotionState] = deque(maxlen=max_size)

    def push(self, state: EmotionState) -> None:
        self._buf.append(state)

    def snapshot(self) -> EmotionState | None:
        """Majority-vote over buffered readings. Returns None if buffer empty."""
        if not self._buf:
            return None

        # Count label occurrences, weighted by confidence.
        scores: dict[str, float] = {}
        total_valence = 0.0
        total_arousal = 0.0
        total_weight = 0.0

        for s in self._buf:
            scores[s.label] = scores.get(s.label, 0.0) + s.confidence
            total_valence += s.valence * s.confidence
            total_arousal += s.arousal * s.confidence
            total_weight += s.confidence

        if total_weight < 1e-6:
            return None

        winner = max(scores, key=scores.get)  # type: ignore[arg-type]
        winner_confidence = scores[winner] / len(self._buf)

        return EmotionState(
            label=winner,
            confidence=min(winner_confidence, 1.0),
            valence=total_valence / total_weight,
            arousal=total_arousal / total_weight,
            source="face",
        )

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# Emotion Fusion — weighted late fusion of FER + SER
# ---------------------------------------------------------------------------

class EmotionFusion:
    def __init__(
        self,
        voice_weight: float = 0.55,
        face_weight: float = 0.45,
        face_confidence_threshold: float = 0.4,
    ) -> None:
        self.voice_weight = voice_weight
        self.face_weight = face_weight
        self.face_threshold = face_confidence_threshold

    def fuse(
        self, fer: EmotionState | None, ser: EmotionState | None
    ) -> EmotionState:
        if ser is None or ser.confidence < 0.1:
            if fer is not None and fer.confidence >= self.face_threshold:
                return fer.with_source("face")
            return EMPTY_EMOTION

        if fer is None or fer.confidence < self.face_threshold:
            return ser.with_source("voice_only")

        # Both signals available — blend.
        if ser.confidence >= fer.confidence:
            label = ser.label
        else:
            label = fer.label

        valence = self.voice_weight * ser.valence + self.face_weight * fer.valence
        arousal = self.voice_weight * ser.arousal + self.face_weight * fer.arousal
        confidence = max(ser.confidence, fer.confidence)

        return EmotionState(
            label=label,
            confidence=confidence,
            valence=valence,
            arousal=arousal,
            source="fused",
        )


# ---------------------------------------------------------------------------
# Emotion → LLM prompt context
# ---------------------------------------------------------------------------

_AROUSAL_DESC = {True: "high energy", False: "low energy"}
_VALENCE_DESC = {True: "positive mood", False: "negative mood"}

_BEHAVIOR_MAP: dict[str, str] = {
    "happy": "Match their energy casually. Be warm, upbeat, and enthusiastic, but avoid being overly bubbly or fake.",
    "sad": "Be gentle, warm, supportive, and real. Talk like a close friend. Avoid any robotic empathy clichés like 'I hear you' or 'It sounds like you're feeling sad'. Be down-to-earth, e.g., 'Damn, I'm sorry' or 'That sucks.'",
    "angry": "Be concise and direct, down-to-earth, and stay on their side. Do NOT give therapist-like validation. Skip standard pleasantries, just match their mood supportively.",
    "fearful": "Be a grounding, calm presence. Speak casually and reassure them naturally without over-explaining or sounding clinical.",
    "surprised": "Acknowledge the surprise casually, match their focus.",
    "disgusted": "Be direct, brief, and supportive.",
    "contempt": "Stay respectful, simple, and objective.",
    "neutral": "",
}


def emotion_context(state: EmotionState, confidence_threshold: float = 0.3) -> str:
    """Build a compact prompt fragment from an EmotionState.

    Returns empty string if emotion is neutral or below confidence threshold —
    in that case, the pipeline should NOT inject anything into the prompt.
    """
    if state.label == "neutral" or state.confidence < confidence_threshold:
        return ""

    behavior = _BEHAVIOR_MAP.get(state.label, "")
    if not behavior:
        return ""

    arousal_desc = _AROUSAL_DESC[state.arousal > 0.5]
    valence_desc = _VALENCE_DESC[state.valence > 0.0]

    return (
        f"[Current User State]\n"
        f"Emotion: {state.label} (confidence: {state.confidence:.0%})\n"
        f"Energy: {arousal_desc} | Mood: {valence_desc}\n"
        f"\nBehavioral adjustment for this turn:\n{behavior}"
    )
