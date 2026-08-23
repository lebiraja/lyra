# Emotion-Aware Conversation — Implementation Plan

## Goal

Make Clarity respond more like a human conversation partner by feeding **voice emotion** and **facial expression** into the existing local voice pipeline without regressing response latency.

This document now reflects:

- the current Clarity codebase
- the emotion implementation already added in this workspace
- the remaining work needed to make that implementation production-safe

## Current Status

### Implemented in code

- `backend/core/emotion.py`
  - `EmotionState`
  - `SpeechEmotionRecognizer`
  - `FacialEmotionRecognizer`
  - `EmotionBuffer`
  - `EmotionFusion`
  - `emotion_context()`
- `backend/core/pipeline.py`
  - parallel STT + SER execution
  - FER + SER fusion at utterance boundary
  - prompt injection via an extra system message
  - `emotion` event emission to the client
- `backend/api/ws.py`
  - `video_frame` WebSocket message support
  - background FER loop
- `backend/main.py`
  - SER / FER model loading in lifespan
- `backend/config.py`
  - emotion feature flags and tuning settings
- `frontend/src/hooks/useMicStream.ts`
  - optional webcam capture with audio fallback
  - JPEG frame export at ~5 FPS
- `frontend/src/hooks/useConversation.ts`
  - `emotion` event handling
  - `sendVideoFrame()` support
- `frontend/src/types/protocol.ts`
  - emotion event schema
- `frontend/src/App.tsx`
  - emotion indicator in the UI
- `tests/test_emotion.py`
- `tests/test_emotion_pipeline.py`

### Not finished until validated

- Docker dependency path
- backend image rebuild with new emotion dependencies
- backend test run against rebuilt image
- frontend image rebuild against current source
- final doc alignment

## Architecture

### Existing core path

```text
Mic audio -> Silero VAD -> Whisper STT -> Qwen via llama.cpp -> Sentence TTS -> Browser playback
```

### New emotion-aware path

```text
Mic audio ----------------------------------------> VAD -> utterance clip
Webcam frames -> FER buffer (background, CPU)  ----^

utterance clip -> STT (GPU)
utterance clip -> SER (CPU, parallel)

FER snapshot + SER result -> EmotionFusion -> emotion_context()

Prompt =
  persona system prompt
  + optional emotion system prompt
  + recent conversation history
```

## Design Decisions

### 1. Camera permission UX

Decision: **graceful degradation**

Reason:

- lowest-friction UX
- preserves the current audio-first flow
- avoids blocking the user before first interaction

Behavior:

- try `audio + video`
- if denied or unavailable, fall back to `audio` only
- do not fail the session because webcam access failed

### 2. Emotion persistence

Decision: **ephemeral for now**

Reason:

- avoids DB schema churn during this feature pass
- keeps rollout smaller
- prevents storing noisy signals before calibration

Implication:

- emotion affects the current turn only
- no analytics or memory use yet

Future option:

- add per-turn emotion metadata once the signal quality is proven

### 3. Tamil emotion prompt language

Decision: **keep internal emotion prompt in English**

Reason:

- it is internal system context, not user-visible text
- Qwen can use English control instructions while still answering in Tamil
- avoids premature localization work for a non-user-facing fragment

## Runtime Constraints

### Latency

Target:

- no meaningful increase in turn latency

Why this should hold:

- STT is slower than SER
- SER runs in parallel with STT
- FER runs off the critical path in the background

Expected net overhead:

- prompt assembly only
- effectively near-zero relative to existing STT + LLM + TTS latency

### Compute

- STT stays on GPU
- SER stays on CPU
- FER stays on CPU
- TTS stays on CPU

### Failure behavior

If any emotion component fails:

- no crash
- no session failure
- pipeline behaves like the previous non-emotion version

## Remaining Work

### Phase 1. Dependency and image validation

Required:

- ensure `requirements.txt` installs successfully in Docker
- rebuild backend image
- confirm the new packages import inside the container

Success criteria:

- `transformers`, `torch`, `hsemotion_onnx`, and `PIL` import successfully
- backend container starts with emotion enabled

### Phase 2. Backend verification

Required:

- run backend tests in Docker against rebuilt image
- ensure the new emotion tests are included

Success criteria:

- all backend tests pass
- no regressions in existing persona / pipeline tests

### Phase 3. Frontend verification

Required:

- rebuild frontend image
- confirm TypeScript and Vite build success

Success criteria:

- no frontend compile errors
- WebSocket protocol remains compatible

### Phase 4. Documentation cleanup

Required:

- align `docs/emotion-aware-conversation.md` with Clarity terminology
- remove stale Athena / IndicF5 / external-LLM assumptions where they are no longer true

Success criteria:

- docs describe the actual Clarity stack

## Risks

### Risk: dependency weight

`torch` and `transformers` materially increase image size and build time.

Mitigation:

- keep SER CPU-only
- evaluate a smaller SER model later if build time becomes a problem

### Risk: FER library behavior

`hsemotion-onnx` may change model download or runtime behavior upstream.

Mitigation:

- tolerate load failure
- keep feature optional behind config

### Risk: noisy emotion signal

False positives could degrade answers.

Mitigation:

- threshold gating
- neutral default
- no persistence yet

### Risk: privacy / user surprise

Silent webcam use can be surprising even if technically allowed.

Mitigation:

- graceful fallback now
- explicit UI disclosure later if needed

## Validation Checklist

### Backend

- rebuild backend image
- run `pytest`
- confirm startup without disabling emotion
- verify `emotion` WebSocket event appears on non-neutral input

### Frontend

- rebuild frontend image
- verify audio-only fallback still works
- verify webcam path does not break typed chat

### UX

- emotion indicator appears only when confidence clears threshold
- no visible regression in first-audio latency

## Recommended Next Step Order

1. finish Docker rebuild
2. run backend tests in container
3. rebuild frontend image
4. smoke-test live conversation path
5. clean remaining docs drift

## Notes For This Branch

This branch should be treated as:

- implementation mostly done
- integration validation still required

The main technical risk is no longer the pipeline logic. It is the dependency and container path.
