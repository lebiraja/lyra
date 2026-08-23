# Emotion-Aware Conversation — Research & Implementation Plan

> **Scope:** English-only (`eng_Latn`). Streaming mode only.  
> **Goal:** Make Clarity feel like talking to a human by adding two new real-time sensing channels — **facial expression** (webcam) and **voice emotion** (same audio stream) — and feeding both as context into the conversation layer.

---

## 1. The Problem We're Solving

Right now Clarity's streaming pipeline receives **pure audio** and produces **pure audio**. It has zero awareness of how the speaker *feels*. It can't tell if you're frustrated, confused, excited, or grieving. This means:

- The LLM response (if there is one) is emotionally blind — same tone regardless of what you're feeling
- TTS output is monotone per session — no prosody shift based on emotional state
- The conversation feels like talking to a robotic translator, not a person

A human conversation partner adjusts constantly:
- They see your face and soften when you look stressed
- They hear your voice crack and slow down
- They notice you're excited and match your energy

This doc defines how to replicate that for Clarity — what models to use, how they fit in the pipeline, what the latency cost is, and what the UX difference looks like.

---

## 2. Current Pipeline (Streaming Mode)

This is what exists today in Clarity:

```
Browser webcam mic audio
         │
         ▼ (PCM chunks over WebSocket)
[VAD — Silero VAD]  ←── sentence boundary detection
         │ sentence audio (numpy array)
         ▼
[STT — faster-whisper large-v3-turbo]   ~350ms
         │ text + language
         ▼
[LLM — Qwen3-4B via llama.cpp]
         │ token stream
         ▼
[TTS — Kokoro / Piper]   ~150ms to first sentence audio
         │ PCM audio
         ▼
Browser plays audio via Web Audio API
```

**What's missing:** Clarity knows *what* was said but not *how* the speaker feels. The response is contextually accurate but emotionally deaf.

---

## 3. The New Vision — Emotionally-Aware Streaming

```
Browser: webcam + mic running simultaneously
         │                      │
         │ (video frames)       │ (PCM audio)
         ▼                      ▼
[FER — facial expression]  [VAD — sentence boundary]
  every ~200ms, CPU              │
  EmotiEffNet-B0 ONNX            │ sentence audio clip
  ~4–6ms per frame               ▼
         │              [SER — speech emotion]
         │                wav2vec2-base-finetuned
         │                runs on sentence clip
         │                ~80–120ms, CPU
         │                      │
         └──────────┬───────────┘
                    ▼
          [Emotion Fusion Layer]
            weighted average of
            FER (visual) + SER (audio)
            → EmotionState {label, confidence, arousal, valence}
                    │
                    ▼
          [STT — faster-whisper]  ~350ms
                    │ text + EmotionState
                    ▼
          [Context Builder]
            builds emotion-aware
            system prompt fragment
                    │
                    ▼
          [Qwen3-4B via llama.cpp]
            emotion-enriched system context
                    │ response text
                    ▼
          [TTS with prosody hints]
            Kokoro / Piper
            (future: speed/pitch adjust
             based on emotion)
                    │
                    ▼
          Browser plays audio
```

---

## 4. The Two New Models

### 4.1 Facial Expression Recognition (FER) — Visual Channel

**What it reads:** Video frames from the user's webcam (sent alongside audio over the same WebSocket connection).

#### Why we need a separate FER model

Voice alone misses ~40% of emotional information. Face adds:
- Microexpressions that contradict spoken words (detecting discomfort while saying "I'm fine")
- Engagement levels — is the person paying attention or zoning out?
- Confirmation of valence when voice is ambiguous

#### Model Selection: EmotiEffNet-B0 (ONNX)

After evaluating the field, **EmotiEffNet-B0** from the [EmotiEffLib / HSEmotion](https://github.com/sb-ai-lab/EmotiEffLib) library is the winner for our constraints.

| Model | Params | AffectNet-8 Accuracy | Inference (CPU) | VRAM usage |
|---|---|---|---|---|
| DeepFace (VGG-Face backend) | ~138M | ~65% | ~80–150ms/frame | GPU required for speed |
| EfficientNet-B0 (FER2013) | ~5.3M | ~72% | ~15–25ms/frame | 0 (CPU ONNX) |
| **EmotiEffNet-B0 (ONNX)** | **~5.3M** | **~65% (8-class AffectNet)** | **~4–6ms/frame** | **0 (CPU only)** |
| MobileViT-XS | ~2.3M | ~61% | ~8ms/frame | 0 (CPU ONNX) |
| OpenFace 3.0 | N/A | AU-based | ~20ms/frame | 0 (CPU) |

**Why EmotiEffNet-B0:**
- Designed specifically for real-time affective computing
- ONNX export is first-class — ships with quantized ONNX weights
- Runs entirely on CPU, leaving the GPU exclusively for Whisper + Qwen inference
- 4–6ms per frame means we can run at 5 FPS (200ms intervals) with negligible CPU load
- Outputs 8 emotion classes (neutral, happy, sad, surprise, fear, disgust, anger, contempt) + valence/arousal dimensions
- Production-tested in ABAW (Affective Behavior Analysis in-the-Wild) competitions

**Frame pipeline:**
```
webcam frame (JPEG)
    ↓
decode to RGB
    ↓
HSEmotion / EmotiEffNet-B0 ONNX inference
    ↓
softmax → {emotion: str, confidence: float, valence: float, arousal: float}
```

The current implementation uses `hsemotion-onnx` directly rather than a separate MediaPipe crop stage.

#### FER Sampling Rate

Running FER on every camera frame (30fps) is wasteful and unnecessary — emotions don't change that fast. We sample at **5 FPS** (every 200ms). Each new FER result is pushed to a sliding window buffer (last 5 readings). When a VAD sentence boundary fires, we snapshot the most common emotion in that window.

```
FER inference every 200ms → [neutral, neutral, happy, happy, happy]
VAD fires → majority vote → "happy" (confidence 0.6)
```

This avoids single-frame noise from blinking or looking away mid-sentence.

---

### 4.2 Speech Emotion Recognition (SER) — Audio Channel

**What it reads:** The same sentence audio clip that gets sent to Whisper.

#### Why voice emotion matters separately from face

- Works in low-light or when user looks away
- Captures paralinguistic cues: pace, pitch, energy, voice breaks
- More reliable for high-arousal states (anger, excitement) where voice spikes before the face shows it
- Natural "ground truth" for what's emotionally in the speech

#### Model Selection: wav2vec2-base + SER head

After evaluating options:

| Model | Training Data | Accuracy (RAVDESS) | Inference | VRAM |
|---|---|---|---|---|
| **wav2vec2-base-finetuned-ravdess** (HuggingFace) | RAVDESS | ~93% (7-class) | **~80–120ms CPU** | 0 (CPU) |
| emotion2vec+ base | Multiple corpora | ~75–82% | ~100–150ms CPU | 0 |
| wav2vec2-large-xlsr-53 | Multilingual | ~96% | ~400ms CPU | heavy |
| CNN-BiGRU (custom) | IEMOCAP | ~74% | ~15ms | 0 |
| SpeechBrain ECAPA-TDNN | VoxCeleb + Emo | ~85% | ~50ms CPU | 0 |

**Why wav2vec2-base (frozen) with SER head:**
- Runs fully on CPU — GPU left free for STT + TTS
- Processes a 3–8s sentence clip in ~80–120ms, which is within our STT latency window (STT takes ~350ms, so SER runs in parallel, arriving before STT finishes)
- HuggingFace model: `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition` or `superb/wav2vec2-base-superb-er` (both available, quantized base is faster)
- 7 emotion labels: neutral, calm, happy, sad, angry, fearful, disgust, surprised
- Important: we use the **base** not the large — large is too slow for real-time on CPU

**SER architecture:**
```
sentence audio (numpy float32, 16kHz)
    ↓
wav2vec2-base feature extractor (frozen)
    ↓
mean-pooled hidden states
    ↓
Linear classification head (7 classes)
    ↓
softmax → {emotion: str, confidence: float}
```

SER runs in a separate thread, kicked off in parallel with STT when the VAD fires. Both results converge at the Emotion Fusion Layer before the LLM call.

---

## 5. Emotion Fusion Layer

Two signals, one combined EmotionState. We use **weighted late fusion** — simple, transparent, no additional model needed.

```python
@dataclass
class EmotionState:
    label: str           # dominant emotion label
    confidence: float    # 0.0–1.0
    valence: float       # -1.0 (negative) to +1.0 (positive)
    arousal: float       # 0.0 (calm) to 1.0 (activated)
    source: str          # "face", "voice", "fused", "voice_only"
```

**Fusion logic:**

```python
def fuse(fer_result: EmotionState | None, ser_result: EmotionState) -> EmotionState:
    # FER may be None if face not detected
    if fer_result is None or fer_result.confidence < 0.4:
        return ser_result.copy(source="voice_only")

    # Weighted combination: voice gets higher weight for label, face for arousal
    voice_weight = 0.55
    face_weight  = 0.45

    # For the label: take higher-confidence signal
    if ser_result.confidence >= fer_result.confidence:
        label = ser_result.label
    else:
        label = fer_result.label

    # Blend valence and arousal
    valence = voice_weight * ser_result.valence + face_weight * fer_result.valence
    arousal = voice_weight * ser_result.arousal + face_weight * fer_result.arousal
    confidence = max(ser_result.confidence, fer_result.confidence)

    return EmotionState(label, confidence, valence, arousal, source="fused")
```

Voice gets slightly higher weight because SER is more accurate on clean English speech. The weights are configurable in `config.py`.

---

## 6. How Emotion Changes the Conversation

This is the most important part — what actually changes in the user experience.

### 6.1 Emotion-Aware System Prompt (LLM Layer)

The detected EmotionState gets injected into the system prompt for every LLM call:

```python
EMOTION_CONTEXT_TEMPLATE = """
[User Emotional State]
Current detected emotion: {label} (confidence: {confidence:.0%})
Arousal: {arousal_desc}  |  Valence: {valence_desc}

Adjust your response accordingly:
- If frustrated/angry: be concise, direct, acknowledge the difficulty
- If sad/fearful: be warm, slow down, use shorter sentences
- If happy/excited: match the energy, be engaged
- If confused (neutral + low confidence): clarify, repeat key points
- If calm: normal conversational tone
"""
```

This runs silently on every sentence. The LLM doesn't see raw audio — it sees a structured emotional annotation.

**Example system context assembled per sentence:**

```
[User says: "I don't understand what you just said"]
[FER: sad, 0.71 confidence]
[SER: frustrated, 0.63 confidence]
[Fused: frustrated, valence=-0.6, arousal=0.5]

System prompt prefix:
"User appears frustrated and confused. Respond with patience.
 Acknowledge the difficulty first, then re-explain more simply.
 Use shorter sentences. Do not rush."
```

### 6.2 TTS Prosody Hints (Future: v0.6)

Currently Kokoro / Piper do not expose a rich emotion-control surface. But the emotion state can influence:

- **nfe_step**: increase from 16 to 20 for sad/calm states (more careful synthesis) 
- **Sentence pacing**: insert longer pauses between sentences for sad/fearful
- **Future**: when a more controllable TTS backend is integrated, map arousal → speed and valence → pitch shift

For now, the emotional response is purely at the **text level** via the LLM.

### 6.3 What Changes Concretely — Before vs After

| Scenario | Before (Emotionally Blind) | After (Emotion-Aware) |
|---|---|---|
| User is frustrated and repeats a question | "Here is the translation: ..." | "I can see this is frustrating — let me be more direct. [concise answer]" |
| User is excited about something | Generic neutral response | Matches energy, affirms, shorter snappier sentences |
| User sounds confused (low confidence speech) | Same output style | Slows down, rephrases, checks understanding |
| User is upset/sad | No adjustment | Softer tone, longer pauses, empathetic opening |
| Face shows contempt but voice is neutral | No signal | Cross-modal dissonance detected; respond carefully |

---

## 7. New Pipeline Flow (Detailed)

```
┌─────────────────────────────────────────────────────────────┐
│ Browser                                                      │
│  • MediaRecorder → PCM 16kHz chunks over WS (audio)        │
│  • getUserMedia video → JPEG frames over WS every 200ms    │
└─────────────────────────────────────────────────────────────┘
                    │ audio chunks    │ video frames
                    ▼                 ▼
┌─────────────────┐   ┌──────────────────────────────────────┐
│ VAD Loop        │   │ FER Loop (runs every 200ms)          │
│ Silero VAD      │   │  HSEmotion / EmotiEffNet-B0 ONNX     │
│ sentence detect │   │  → emotion buffer                    │
│                 │   │  → sliding window buffer (last 5)    │
└────────┬────────┘   └─────────────────────┬────────────────┘
         │ sentence audio                    │ FER snapshot
         │ (numpy float32)                   │ at VAD boundary
         ▼                                   │
    ┌────┴──────────────┐                    │
    │ PARALLEL FORK      │                    │
    │                   │                    │
    ▼                   ▼                    │
[STT]              [SER]                    │
faster-whisper     wav2vec2-base            │
~350ms CPU         ~80–120ms CPU            │
    │                   │                    │
    └────────┬──────────┘                    │
             │ text + SER result             │ FER result
             ▼                               │
         [Emotion Fusion] ←─────────────────┘
             │ EmotionState
             ▼
         [Context Builder]
           assembles system prompt
           with emotion annotation
             │
             ▼
         [LLM Call — Qwen3-4B / llama.cpp]
           emotion-aware response
             │ response text
             ▼
         [TTS — Kokoro / Piper]
             │ PCM audio
             ▼
         Browser plays via Web Audio API
```

---

## 8. Latency Analysis

### 8.1 Added Latency Per Component

| Component | Where it runs | Latency | When |
|---|---|---|---|
| FER (EmotiEffNet-B0 ONNX) | CPU | ~4–6ms | Every 200ms, async, NOT in critical path |
| JPEG decode + FER preprocessing | CPU | ~1–3ms | Every 200ms, async |
| SER (wav2vec2-base) | CPU | ~80–120ms | In parallel with STT at VAD boundary |
| Emotion fusion | CPU | <1ms | After SER result arrives |
| Context builder | CPU | <1ms | Immediately after fusion |
| LLM call | GPU + local network hop | existing path | Already present in Clarity |

### 8.2 Overall Latency Budget (Revised)

| Stage | Original streaming | New emotion-aware |
|---|---|---|
| VAD silence window | 400ms | 400ms (unchanged) |
| STT | ~350ms | ~350ms (unchanged) |
| SER (parallel with STT) | — | +0ms net (parallel) |
| Emotion fusion | — | <1ms |
| LLM call (new) | — | +300–800ms |
| TTS (nfe=16) | ~2.7–5s | ~2.7–5s (unchanged) |
| **Total TTFA** | **~3.5–3.8s** | **~3.8–4.6s** |

**Key insight:** FER adds literally zero latency to the critical path — it runs on a 200ms background loop. SER adds zero net latency because it runs in parallel with STT, which is longer. The only real new latency is the **LLM call** (~300–800ms depending on API). This pushes TTFA from ~3.5s to ~4–4.6s — acceptable tradeoff.

### 8.3 CPU Budget (RTX 4050 Host)

| Process | CPU load |
|---|---|
| FER loop at 5fps | ~2–3% per core |
| SER per sentence | ~8–15% for ~100ms burst |
| Silero VAD | ~1% |
| Existing pipeline | ~5–10% |
| **Total new CPU** | **~10–18% peak, ~5% steady** |

No GPU VRAM impact — both FER and SER run on CPU.

---

## 9. Model Comparison — Final Picks

### 9.1 FER Model Decision

| Candidate | Verdict |
|---|---|
| **EmotiEffNet-B0 (ONNX)** | ✅ **CHOSEN** — fastest CPU inference, ABAW-validated, 0 GPU VRAM |
| DeepFace | ❌ Too slow on CPU, GPU-dependent for real-time |
| OpenFace 3.0 | ❌ Action unit output requires secondary mapping to emotions; more complexity |
| EfficientNet-B0 (FER2013) | ⚠️ Viable fallback — FER2013 has 7 class labels, slightly lower accuracy on AffectNet |
| MobileViT-XS | ❌ Less mature for production FER tasks |

### 9.2 SER Model Decision

| Candidate | Verdict |
|---|---|
| **wav2vec2-base + SER head (frozen)** | ✅ **CHOSEN** — ~100ms CPU, 7 classes, proven on RAVDESS |
| emotion2vec+ base | ⚠️ Strong alternative — better cross-corpus generalization but slightly slower |
| wav2vec2-large-xlsr-53 | ❌ Too slow (~400ms) for real-time on CPU |
| SpeechBrain ECAPA-TDNN | ⚠️ Good option — ECAPA-TDNN is speaker-verification-adapted, emotion accuracy slightly lower |
| CNN-BiGRU (custom) | ❌ Needs custom training data; not available off-shelf for English |

**HuggingFace model IDs to use:**
- FER: `sb-ai-lab/EmotiEffLib` → EmotiEffNet-B0 ONNX export
- SER: `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition` (base variant preferred for speed) or `superb/wav2vec2-base-superb-er`

---

## 10. What Makes It Feel Human

Here's the full picture of signals a human uses, and which we now cover:

| Human cue | What it reveals | Now detected? |
|---|---|---|
| Facial microexpression | True internal state, often contradicts words | ✅ FER every 200ms |
| Voice pitch rise | Excitement, question, surprise | ✅ SER (wav2vec2 captures F0 implicitly) |
| Voice energy drop | Sadness, exhaustion, defeat | ✅ SER |
| Speaking rate | Urgency (fast) vs. hesitation (slow) | ✅ SER indirectly via temporal features |
| Voice breaks/cracks | Emotional distress | ✅ SER (wav2vec2 very sensitive to this) |
| Word choice | Sentiment, topic | ✅ STT text → LLM already handles this |
| Pausing | Uncertainty, emphasis | Partial (VAD buffer captures silence) |
| Eye contact | Engagement level | ❌ Not added (requires gaze tracking) |
| Gesture/posture | Confidence, openness | ❌ Not added |
| Context history | What was discussed | ✅ LLM conversation history |

We're now capturing 6 out of the 10 primary human conversational cues. The two uncovered ones (gaze, posture) require more invasive camera-side processing and are v0.7+ territory.

---

## 11. Files Created & Modified

### New Files

| File | Purpose |
|---|---|
| `backend/core/emotion.py` | Contains `EmotionState` definition, `SpeechEmotionRecognizer` (wav2vec2-base), `FacialEmotionRecognizer` (EmotiEffNet-B0 ONNX), `EmotionBuffer`, `EmotionFusion` weighted blender, and `emotion_context` compiler. |
| `tests/test_emotion.py` | Unit tests for emotion dataclasses, sliding-window buffers, and blending/context-formatting logic. |
| `tests/test_emotion_pipeline.py` | Integration tests verifying VAD boundary processing, parallel SER execution, and context prompt injection. |

### Modified Files

| File | Change |
|---|---|
| `backend/config.py` | Added configuration variables for emotion enabling, model IDs, confidence thresholds, and weights. |
| `backend/main.py` | Added lifespans for loading models into app memory at server start, pre-warming on CPU. |
| `backend/core/pipeline.py` | Embedded parallel voice recognition, majority-vote face recognition snapshotting, and system prompt injection. |
| `backend/api/ws.py` | Handled `video_frame` payload, running async background loop for frame classification. |
| `frontend/src/types/protocol.ts` | Added `emotion` event schemas to standard type signatures. |
| `frontend/src/hooks/useConversation.ts` | Added `currentEmotion` state and frame sender callbacks. |
| `frontend/src/hooks/useMicStream.ts` | Embedded dynamic video capture (5 FPS canvas capture fallback to audio-only on block). |
| `frontend/src/App.tsx` | Wire up the frame sender and render the italic/pulsing user state indicator. |
| `requirements.txt` | Add packages: `hsemotion-onnx`, `mediapipe`, `transformers`. |
| `scripts/download_models.sh` | Integrated automated warm-ups for superb/wav2vec2-base-superb-er and HSEmotion models. |

---

## 12. Verification & Testing

Verify that all tests run successfully within the docker container:
```bash
docker compose run --rm backend pytest tests/ -v
```
Verify that frontend compiles without errors:
```bash
docker compose build frontend
```

---

## 13. VRAM Budget (Unchanged)

Both new models run on CPU only. VRAM budget is **identical** to the current streaming mode:

| Component | VRAM |
|---|---|
| Qwen3-4B Q4_K_M via llama.cpp | ~3.5 GB |
| faster-whisper large-v3-turbo | ~1.3 GB |
| Kokoro + Piper + Silero | 0 |
| EmotiEffNet-B0 ONNX | **0 — CPU only** |
| wav2vec2-base SER | **0 — CPU only** |
| **Total** | **~4.8 GB** |

---

## 14. Open Questions

| Question | Options | Recommendation |
|---|---|---|
| **LLM backend** | Current local llama.cpp service, larger future local model | Keep current local llama.cpp service |
| **Video frame format over WS** | JPEG at quality 50, WebP, raw pixels | JPEG q50 — good balance of bandwidth vs decode speed |
| **FER sampling interval** | 100ms, 200ms, 500ms | 200ms — 5fps is plenty for emotion changes, minimal CPU |
| **Emotion label mapping** | 7-class to 5-class (PERMA style)? | Keep 7-class natively; map to 5-class (happy/sad/angry/fearful/neutral) for prompt injection |
| **No-face scenario** | Camera off, dark room, face out of frame | Fall back to voice-only (`source="voice_only"`) gracefully |
| **SER model storage size** | wav2vec2-base ~360MB | Acceptable — include in Docker image via `prefetch_models.py` |
| **Privacy** | Video frames sent to server | All processing server-side; frames not stored. Add explicit consent UX. |

---

## 15. References

- [EmotiEffLib (sb-ai-lab)](https://github.com/sb-ai-lab/EmotiEffLib) — FER model library, ONNX export
- [MediaPipe Face Detection](https://developers.google.com/mediapipe/solutions/vision/face_detector) — BlazeFace for face crop
- [wav2vec2-base emotion](https://huggingface.co/superb/wav2vec2-base-superb-er) — SER baseline on HuggingFace SUPERB benchmark
- [ehcalabres SER](https://huggingface.co/ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition) — alternative SER head on RAVDESS
- [emotion2vec (ddlBoJack)](https://github.com/ddlBoJack/emotion2vec) — alternative SER foundation model
- [ABAW Challenge](https://ibug.doc.ic.ac.uk/resources/eccv-2023-4th-abaw/) — benchmark where EmotiEffNet was evaluated
- [EmotionPrompt paper](https://arxiv.org/abs/2307.11760) — using emotional context in LLM prompts
- [AffectNet dataset](http://mohammadmahoor.com/affectnet/) — 8-class FER training data
- [RAVDESS dataset](https://zenodo.org/record/1188976) — SER training data
- [MELD dataset](https://affective-meld.github.io/) — conversational SER benchmark
