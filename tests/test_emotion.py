"""Unit tests for backend.core.emotion — types, fusion, buffer, context builder."""

import numpy as np
import pytest

from backend.core.emotion import (
    EMPTY_EMOTION,
    EmotionBuffer,
    EmotionFusion,
    EmotionState,
    emotion_context,
)


class TestEmotionState:
    def test_defaults(self):
        s = EmotionState()
        assert s.label == "neutral"
        assert s.confidence == 0.0
        assert s.source == "none"

    def test_with_source(self):
        s = EmotionState(label="happy", confidence=0.9, source="voice")
        new = s.with_source("fused")
        assert new.source == "fused"
        assert new.label == "happy"
        assert new.confidence == 0.9

    def test_frozen(self):
        s = EmotionState()
        with pytest.raises(AttributeError):
            s.label = "sad"  # type: ignore[misc]


class TestEmotionBuffer:
    def test_empty_snapshot(self):
        buf = EmotionBuffer(max_size=5)
        assert buf.snapshot() is None
        assert len(buf) == 0

    def test_single_reading(self):
        buf = EmotionBuffer(max_size=5)
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        snap = buf.snapshot()
        assert snap is not None
        assert snap.label == "happy"

    def test_majority_vote(self):
        buf = EmotionBuffer(max_size=5)
        buf.push(EmotionState("happy", 0.7, 0.8, 0.6, "face"))
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        buf.push(EmotionState("sad", 0.6, -0.7, 0.2, "face"))
        snap = buf.snapshot()
        assert snap is not None
        assert snap.label == "happy"

    def test_ring_buffer_eviction(self):
        buf = EmotionBuffer(max_size=3)
        buf.push(EmotionState("sad", 0.9, -0.7, 0.2, "face"))
        buf.push(EmotionState("sad", 0.9, -0.7, 0.2, "face"))
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        snap = buf.snapshot()
        assert snap is not None
        assert snap.label == "happy"

    def test_clear(self):
        buf = EmotionBuffer(max_size=3)
        buf.push(EmotionState("happy", 0.8, 0.8, 0.6, "face"))
        buf.clear()
        assert buf.snapshot() is None


class TestEmotionFusion:
    def setup_method(self):
        self.fusion = EmotionFusion(voice_weight=0.55, face_weight=0.45, face_confidence_threshold=0.4)

    def test_both_none(self):
        result = self.fusion.fuse(None, None)
        assert result == EMPTY_EMOTION

    def test_voice_only(self):
        ser = EmotionState("angry", 0.85, -0.6, 0.8, "voice")
        result = self.fusion.fuse(None, ser)
        assert result.label == "angry"
        assert result.source == "voice_only"

    def test_face_only(self):
        fer = EmotionState("happy", 0.7, 0.8, 0.6, "face")
        result = self.fusion.fuse(fer, None)
        assert result.label == "happy"
        assert result.source == "face"

    def test_face_below_threshold(self):
        fer = EmotionState("happy", 0.2, 0.8, 0.6, "face")
        ser = EmotionState("angry", 0.85, -0.6, 0.8, "voice")
        result = self.fusion.fuse(fer, ser)
        assert result.source == "voice_only"

    def test_fused_uses_higher_confidence_label(self):
        fer = EmotionState("happy", 0.6, 0.8, 0.6, "face")
        ser = EmotionState("angry", 0.85, -0.6, 0.8, "voice")
        result = self.fusion.fuse(fer, ser)
        assert result.label == "angry"
        assert result.source == "fused"

    def test_fused_blended_values(self):
        fer = EmotionState("happy", 0.7, 0.8, 0.6, "face")
        ser = EmotionState("sad", 0.8, -0.7, 0.2, "voice")
        result = self.fusion.fuse(fer, ser)
        expected_valence = 0.55 * (-0.7) + 0.45 * 0.8
        assert abs(result.valence - expected_valence) < 0.01


class TestEmotionContext:
    def test_neutral_returns_empty(self):
        assert emotion_context(EMPTY_EMOTION) == ""

    def test_neutral_label_returns_empty(self):
        s = EmotionState("neutral", 0.8, 0.0, 0.1, "voice")
        assert emotion_context(s) == ""

    def test_below_threshold_returns_empty(self):
        s = EmotionState("angry", 0.2, -0.6, 0.8, "voice")
        assert emotion_context(s, confidence_threshold=0.3) == ""

    def test_angry_produces_directive(self):
        s = EmotionState("angry", 0.85, -0.6, 0.8, "voice")
        ctx = emotion_context(s)
        assert "[Current User State]" in ctx
        assert "angry" in ctx
        assert "85%" in ctx
        assert "direct" in ctx.lower()

    def test_happy_produces_directive(self):
        s = EmotionState("happy", 0.75, 0.8, 0.6, "voice")
        ctx = emotion_context(s)
        assert "happy" in ctx
        assert "enthusiastic" in ctx.lower()

    def test_sad_produces_directive(self):
        s = EmotionState("sad", 0.7, -0.7, 0.2, "voice")
        ctx = emotion_context(s)
        assert "sad" in ctx
        assert "gentle" in ctx.lower()
