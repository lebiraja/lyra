# Clarity v2 → v3: Tamil + English Bilingual Voice Companion

## Engineering Design Document

---

## 1. Problem Statement

Clarity v2 is English-only. All three pipeline stages (STT → LLM → TTS) are locked to English. The goal is to add Tamil support so a user can speak in either language and get a natural voice response back in the same language — including **Tanglish** (mixed Tamil-English), which is how most Tamil speakers actually talk.

---

## 2. Current Architecture (v2)

```
Mic → [Silero VAD, CPU] → [Parakeet STT, CPU] → [Qwen3-4B, GPU] → [Kokoro TTS, CPU] → Speaker
                                                      ↕
                                                   SQLite
```

| Component | Model | Lang | Device | VRAM | Latency |
|-----------|-------|------|--------|------|---------|
| VAD | Silero v5 ONNX | agnostic | CPU | 0 | ~5ms |
| STT | Parakeet TDT 0.6B v3 int8 | EN only | CPU | 0 | ~200ms |
| LLM | Qwen3-4B Q4_K_M | multilingual | GPU | ~3.5 GB | ~800-1500ms |
| TTS | Kokoro-82M ONNX | EN only | CPU | 0 | ~200ms |
| **Total** | | | | **~3.5 GB** | **~1.3-2.5s** |

---

## 3. Constraints

| Constraint | Value | Impact |
|-----------|-------|--------|
| GPU | RTX 4050, **6 GB VRAM** | Hard ceiling — must fit all GPU models |
| LLM VRAM | ~3.5 GB (non-negotiable) | Leaves **~2.5 GB** for everything else on GPU |
| Network | Zero (fully local) | No cloud APIs, no fallback to hosted Whisper |
| Latency target | ≤2.5s first audio | Same as current — must not regress |
| Docker | Everything in containers | CUDA runtime needed in backend container |
| Backward compat | English must not degrade | Kokoro quality for EN stays identical |

---

## 4. Decision Matrix — STT

### Options Evaluated

| Model | Params | Tamil? | Tanglish? | VRAM (int8) | Latency (GPU) | Latency (CPU) |
|-------|--------|--------|-----------|-------------|---------------|---------------|
| Parakeet TDT 0.6B v3 (current) | 600M | ❌ | ❌ | N/A (CPU only) | — | ~200ms |
| faster-whisper `small` | 244M | ✅ moderate | ⚠️ weak | ~0.5 GB | ~80ms | ~400ms |
| faster-whisper `medium` | 769M | ✅ good | ✅ decent | ~1.0 GB | ~120ms | ~800ms |
| **faster-whisper `large-v3-turbo`** | **809M** | **✅ best** | **✅ best** | **~1.3 GB** | **~100-150ms** | ~1200ms |
| faster-whisper `large-v3` | 1.5B | ✅ best | ✅ best | ~1.6 GB | ~200ms | too slow |
| IndicConformer (AI4Bharat) | varies | ✅ excellent | ✅ trained for it | ~0.5-1 GB | ~80ms | ~300ms |

### Decision: **faster-whisper `large-v3-turbo` on GPU, int8**

**Why:**
- **Fits the VRAM budget**: 3.5 GB (LLM) + 1.3 GB (Whisper) = 4.8 GB < 6 GB ✅
- **Best Tamil accuracy** in the Whisper family — 3x params vs `small`, trained on diverse Tamil data
- **Built-in language detection** — `info.language` returns `"ta"` or `"en"` with probability. Eliminates a separate lang_detect module entirely
- **GPU inference = ~100-150ms** — actually **faster than current Parakeet on CPU** (~200ms)
- **Tanglish handling** — Whisper large models handle code-switching reasonably well. For a mentor app (not medical transcription), this is acceptable
- **Auto-downloads via HuggingFace cache** — no manual model download step needed

**Why not IndicConformer:**
- Better Tamil accuracy, but requires `sherpa-onnx` or custom ONNX pipeline — different runtime than `faster-whisper`
- No built-in language detection — would need a separate LID model
- Harder to package in Docker (less mainstream tooling)
- Can revisit in v4 if Whisper Tamil quality isn't good enough

**Risk: GPU memory pressure**
- faster-whisper + llama.cpp are separate processes competing for VRAM
- Whisper inference is **bursty** (runs for 100-150ms then releases compute) while LLM is streaming tokens
- They should coexist because they rarely run simultaneously in the pipeline (STT finishes → LLM starts)
- **Mitigation**: Set `CUDA_VISIBLE_DEVICES` and monitor with `nvidia-smi`. If OOM occurs, fall back to `medium` model (~1.0 GB)

---

## 5. Decision Matrix — TTS

### Options Evaluated

| Model | Tamil? | Quality (Tamil) | Quality (English) | Format | Size | Sample Rate |
|-------|--------|-----------------|-------------------|--------|------|-------------|
| Kokoro-82M (current) | ❌ | — | ⭐⭐⭐⭐⭐ excellent | ONNX | 410 MB | 24 kHz |
| Piper `ta_IN-Valluvar-medium` | ✅ | ⭐⭐⭐ decent | N/A | ONNX | ~60 MB | 22.05 kHz |
| Meta MMS-TTS Tamil | ✅ | ⭐⭐ robotic/flat | N/A | PyTorch→ONNX | ~200 MB | 16 kHz |
| AI4Bharat IndicTTS | ✅ | ⭐⭐⭐⭐ good | N/A | custom | varies | varies |
| sherpa-onnx VITS Tamil | ✅ | ⭐⭐⭐ decent | N/A | ONNX | ~30 MB | varies |

### Decision: **Kokoro (English) + Piper (Tamil) — dual engine routing**

**Why:**
- **English quality stays perfect** — Kokoro is untouched, same `af_heart` voice
- **Piper Tamil is the best local ONNX option** — community `ta_IN-Valluvar-medium` is trained on IIT Madras IndicTTS data
- **Piper is a first-class citizen in the ONNX ecosystem** — no conversion scripts needed
- **Tiny footprint** — ~60 MB for the Tamil voice, runs on CPU, zero VRAM
- **Same ONNX runtime** we already have in the container

**Why not MMS-TTS:**
- Output sounds flat/robotic compared to Piper
- Requires PyTorch→ONNX conversion (fragile, version-dependent)
- 16 kHz output needs upsampling to match our 24 kHz WebSocket protocol

**Why not AI4Bharat:**
- Best quality, but not packaged as standalone ONNX
- Requires Bhashini API or custom model export pipeline
- Can explore in v4 when/if Piper quality isn't sufficient

**Key engineering detail: sample rate mismatch**
- Kokoro outputs 24 kHz, Piper Tamil outputs 22.05 kHz
- The WebSocket protocol sends 24 kHz int16 PCM
- **Solution**: Linear interpolation resampling in the TTSRouter (cheap, ~1ms for typical sentences)
- Not using `librosa`/`scipy` to avoid heavy deps — `numpy` linear interp is good enough for speech

---

## 6. Decision Matrix — LLM

### Does Qwen3-4B speak Tamil well enough?

**Research findings:**
- Base Qwen3-4B supports 100+ languages including Tamil
- Community fine-tuned `Tamil-Qwen3-4B-Inst` (using Tamil Wikipedia + Aya Dataset) scores ~52% on benchmarks — **moderate but usable**
- For a mentor/companion (not a Tamil literature generator), this is sufficient — short spoken responses, not essays
- The model follows language cues well: if you say "respond in the language the user speaks", it does

### Decision: **Keep Qwen3-4B, update system prompt only**

No model swap needed. Just add a multilingual instruction to the system prompt.

**Fallback option (v4)**: If Tamil generation quality is noticeably bad, swap to `Tamil-Qwen3-4B-Inst` GGUF — same size, same VRAM, drop-in replacement.

---

## 7. Target Architecture (v3)

```
Mic → [Silero VAD, CPU] → [Whisper large-v3-turbo, GPU int8] → [Qwen3-4B, GPU] → [TTS Router, CPU] → Speaker
           │                         │                                                    │
           │                    returns:                                             routes by lang:
           │                    - text                                                ├── "en" → Kokoro
           │                    - language ("en"/"ta")                                 └── "ta" → Piper Tamil
           │                    - lang_probability
           ↕                                                                               ↕
        stateful                                                                      resamples if
        per-connection                                                                sr ≠ 24kHz
```

| Component | Model | Lang | Device | VRAM | Latency |
|-----------|-------|------|--------|------|---------|
| VAD | Silero v5 ONNX | agnostic | CPU | 0 | ~5ms |
| STT | Whisper large-v3-turbo int8 | EN + TA + 90+ | **GPU** | **1.3 GB** | **~100-150ms** ⬇️ |
| LLM | Qwen3-4B Q4_K_M | multilingual | GPU | ~3.5 GB | ~800-1500ms |
| TTS (EN) | Kokoro-82M | EN | CPU | 0 | ~200ms |
| TTS (TA) | Piper Valluvar-medium | TA | CPU | 0 | ~150ms |
| **Total** | | | | **~4.8 GB** ✅ | **~1.1-1.8s** ⬇️ |

> [!IMPORTANT]
> **Net result**: Tamil support AND ~200ms lower end-to-end latency (GPU STT is faster than current CPU STT).

---

## 8. Tanglish / Code-Switching Strategy

Real Tamil speakers mix English constantly: "அந்த meeting-ல okay-ன்னு சொன்னேன்" (I said okay in that meeting).

### How each stage handles it:

| Stage | Strategy |
|-------|----------|
| **STT** | Whisper large-v3-turbo handles code-switching natively. It may output mixed-script text. The `language` field reflects the *dominant* language |
| **LLM** | Qwen3-4B can process mixed Tamil+English input. System prompt instructs: "respond in whatever language the user used" |
| **TTS routing** | Route based on Whisper's `language` detection. If dominant=`ta`, use Piper. If dominant=`en`, use Kokoro |
| **Edge case** | If `language_probability < 0.7`, default to English (safer fallback — Kokoro quality is better) |

### Known limitation:
- Piper Tamil can't pronounce English words embedded in Tamil sentences naturally
- This is acceptable for v3 — most Tamil responses from the LLM will be predominantly Tamil
- **v4 improvement**: investigate a bilingual TTS model that handles both scripts

---

## 9. File-by-File Change Specification

### Phase 1: Core Pipeline (must be atomic — all or nothing)

| File | Action | Lines Changed | Description |
|------|--------|---------------|-------------|
| `backend/core/stt.py` | **REWRITE** | 22 → ~40 | Replace `ParakeetSTT` with `WhisperSTT`. Add `STTResult` dataclass returning text + language |
| `backend/core/tts.py` | **REWRITE** | 30 → ~75 | Keep `KokoroTTS`, add `PiperTTS`, add `TTSRouter` that dispatches by language. Add resampling |
| `backend/core/pipeline.py` | **MODIFY** | ~10 lines | `_run_turn()`: STT now returns `STTResult`. Extract `language`, pass to `tts.synthesize(text, language=...)`. Send language in `user_transcript` event |
| `backend/main.py` | **MODIFY** | ~15 lines | Lifespan: load `WhisperSTT` + `TTSRouter` instead of `ParakeetSTT` + `KokoroTTS` |
| `backend/config.py` | **MODIFY** | ~12 lines | Add: `STT_MODEL`, `STT_DEVICE`, `STT_COMPUTE_TYPE`, `PIPER_TAMIL_MODEL`, `PIPER_TAMIL_CONFIG`. Remove `parakeet_dir` |

### Phase 2: Infrastructure

| File | Action | Description |
|------|--------|-------------|
| `requirements.txt` | **MODIFY** | Remove `onnx-asr`. Add `faster-whisper>=1.1.0`, `piper-tts>=1.2.0`. Change `onnxruntime` → `onnxruntime-gpu` |
| `Dockerfile.backend` | **REWRITE** | Switch from `python:3.12-slim` to NVIDIA CUDA base image. Install Python 3.12, CUDA runtime |
| `docker-compose.yml` | **MODIFY** | Backend needs `deploy.resources.reservations.devices` for GPU access. Add piper-tamil volume. Remove parakeet volume. Add whisper cache volume |
| `scripts/download_models.sh` | **MODIFY** | Remove Parakeet download. Add Piper Tamil download. Whisper auto-downloads on first run |
| `.env.example` | **MODIFY** | Add `STT_MODEL`, `STT_DEVICE`, `STT_COMPUTE_TYPE` |

### Phase 3: UX & Prompt

| File | Action | Description |
|------|--------|-------------|
| `config/system_prompt.txt` | **MODIFY** | Add bilingual instruction — respond in user's language |
| `backend/api/ws.py` | **MODIFY** | Add `language` field to `user_transcript` event so frontend can display it |
| Frontend (optional) | **MINOR** | Show detected language badge in the UI |

### Phase 4: Testing

| File | Action | Description |
|------|--------|-------------|
| `tests/test_smoke.py` | **MODIFY** | Update smoke tests for new STT/TTS classes |
| `tests/test_tts_router.py` | **NEW** | Unit test for TTSRouter language routing + resampling |
| `tests/test_stt_whisper.py` | **NEW** | Smoke test: transcribe a short English + Tamil audio clip |

---

## 10. Dockerfile.backend — CUDA Design

Current image: `python:3.12-slim` (no CUDA)

New image needs:
- CUDA 12.x runtime (for faster-whisper GPU)
- Python 3.12
- ONNX Runtime GPU (for Kokoro + Piper + Silero)

### Option A: `nvidia/cuda:12.4.1-runtime-ubuntu22.04` + install Python
- Full control, but heavy base image (~1.5 GB)
- Need to `apt install python3.12 python3-pip`

### Option B: `pytorch/pytorch:2.x-cuda12.x-cudnn9-runtime`
- Python + CUDA pre-installed, but brings all of PyTorch (~3 GB image)
- Overkill — we don't use PyTorch

### Decision: **Option A** — NVIDIA CUDA runtime + install Python

```dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip curl && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# ... rest same as current Dockerfile
```

Image size: ~1.8 GB (vs current ~544 MB). Acceptable for a GPU-dependent app.

---

## 11. GPU Sharing — llama.cpp + faster-whisper

Both run as separate processes on the same GPU. Key insight: **they never run simultaneously** in the pipeline flow:

```
[STT runs on GPU] → STT done → [LLM runs on GPU] → LLM done → [TTS on CPU]
     150ms                          800-1500ms                    200ms
```

**Why this is safe:**
1. STT completes before LLM starts (sequential in `_run_turn`)
2. faster-whisper allocates VRAM on init, holds it resident — no per-inference allocation spikes
3. llama.cpp uses `mmap` and manages its own KV cache — VRAM is pre-allocated at server start
4. Both respect CUDA's memory allocator — no conflicts

**Monitoring plan:**
- Add `nvidia-smi` check to `make test-smoke`
- Log VRAM usage at startup via `torch.cuda.mem_get_info()` or `pynvml`
- If OOM: fall back to `STT_MODEL=medium` (saves 300 MB VRAM)

---

## 12. Configuration — New Environment Variables

```bash
# STT (new in v3)
STT_MODEL=large-v3-turbo      # faster-whisper model name
STT_DEVICE=cuda                # "cuda" or "cpu"
STT_COMPUTE_TYPE=int8          # "int8", "float16", "int8_float16"

# TTS Tamil (new in v3)
PIPER_TAMIL_ENABLED=true       # set false to disable Tamil TTS entirely
```

All backwards-compatible — if not set, defaults to the GPU-accelerated bilingual config.

---

## 13. System Prompt Update

```diff
 You are Clarity, a thoughtful mentor someone talks to out loud, late at night,
 when something is on their mind.

 How you speak:
-- This is a spoken conversation. Keep replies short — two to four sentences,
-  usually. One idea at a time.
-- Plain spoken English. No lists, no headings, no markdown, no asterisks.
-  Never say "as an AI".
+- This is a spoken conversation. Keep replies short — two to four sentences,
+  usually. One idea at a time.
+- Respond in whatever language the user speaks. If they speak Tamil, respond
+  in Tamil. If English, respond in English. If they mix both (Tanglish),
+  respond naturally in the same mix.
+- No lists, no headings, no markdown, no asterisks. Never say "as an AI".
 - Warm but direct. You respect the person too much to flatter them or pad
   the truth.
```

---

## 14. WebSocket Protocol Changes

### New field in `user_transcript`:

```json
{
    "type": "user_transcript",
    "text": "நான் confused-ஆ இருக்கேன்",
    "language": "ta",
    "language_probability": 0.92
}
```

Backward compatible — frontend ignores unknown fields. The `language` field lets the UI optionally show a language indicator.

---

## 15. Rollback Plan

If Tamil support causes issues in production:

1. **Quick rollback**: Set `STT_DEVICE=cpu` + `STT_MODEL=large-v3-turbo` — removes GPU dependency for STT, still works (slower)
2. **Full rollback**: Set `PIPER_TAMIL_ENABLED=false` — disables Tamil TTS, all responses in English
3. **Nuclear rollback**: Revert to v2 branch — Parakeet + Kokoro, English-only

All rollback options are env-var driven — no code changes needed.

---

## 16. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| GPU OOM (Whisper + LLM > 6GB) | Low | High | Fall back to `medium` model. Monitor with `pynvml`. Add `STT_MODEL` env var |
| Whisper Tamil transcription errors | Medium | Medium | Large-v3-turbo is best available. Accept imperfect Tanglish. Can fine-tune later |
| Piper Tamil sounds robotic | Medium | Medium | It's the best local option. Can swap to AI4Bharat in v4. Users will adapt |
| Qwen3-4B Tamil generation is poor | Low-Medium | Medium | System prompt guides it well. Can swap to `Tamil-Qwen3-4B-Inst` GGUF (same size) |
| Docker image size bloat (CUDA base) | Certain | Low | ~1.8 GB vs 544 MB. Acceptable trade-off for GPU acceleration |
| Piper `piper-tts` pip package conflicts | Low | Medium | Pin version. Test in Docker build CI |
| Language detection flickers (short utterances) | Medium | Low | Add `language_probability < 0.7` → default English fallback |
| Resampling artifacts (22.05→24 kHz) | Low | Low | Linear interp is fine for speech. Can upgrade to `sinc` if needed |

---

## 17. Execution Order

> [!IMPORTANT]
> **All of Phase 1 must land as a single atomic commit** — partial changes break the pipeline.

```
Phase 1 (core):   stt.py → tts.py → pipeline.py → config.py → main.py
Phase 2 (infra):  requirements.txt → Dockerfile.backend → docker-compose.yml → download_models.sh → .env.example
Phase 3 (UX):     system_prompt.txt → ws.py
Phase 4 (test):   test_smoke.py → test_tts_router.py → test_stt_whisper.py
Phase 5 (ship):   Build → Test → Push Docker images → Update README → PR → Merge
```

---

## 18. Model Download Summary

| Model | Size | Source | Download Method |
|-------|------|--------|----------------|
| Qwen3-4B Q4_K_M | ~2.5 GB | HuggingFace | `hf download` (existing) |
| faster-whisper large-v3-turbo | ~1.5 GB | HuggingFace | **Auto on first run** (cached to `~/.cache/huggingface`) |
| Kokoro-82M ONNX | ~410 MB | GitHub release | `curl` (existing) |
| Piper Tamil Valluvar-medium | ~60 MB | HuggingFace | `curl` in download script (**new**) |
| Silero VAD v5 | ~2 MB | GitHub raw | `curl` (existing) |
| **Total** | **~4.5 GB** | | +~1 GB vs current (Whisper replaces Parakeet) |

---

## 19. Success Criteria

- [x] Speak English → get English voice response (quality identical to v2)
- [x] Speak Tamil → get Tamil voice response (intelligible, natural-ish)
- [x] Speak Tanglish → get response in dominant language (no crash, no gibberish)
- [x] End-to-end latency ≤ 2.5s (same or better than v2)
- [x] VRAM usage ≤ 5.5 GB peak (confirmed via `nvidia-smi`)
- [x] `make up` works on fresh clone with `make models` (no manual steps)
- [x] All existing tests pass
- [x] New Tamil smoke test passes
- [x] Docker images build and push to Hub
- [x] Update documentation
