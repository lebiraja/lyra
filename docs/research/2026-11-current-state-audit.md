# Current-State Audit (v3, Medusa)

**Date:** 2026-11-10 · **Scope:** backend pipeline, memory, emotion, frontend UI · **Code changes:** none (read-only audit)

This audit records what the code does today and what blocks the v4 goal: a companion that sees, hears, remembers and answers fast in English, Tamil and Tanglish on one RTX 4050 laptop. Findings cite `file:line` at commit `75eace7`.

## 1. Hardware this has to fit

| Resource | Value | Notes |
|---|---|---|
| GPU | RTX 4050 Laptop, **6141 MiB**, sm_89 (Ada) | Driver 615.78. Supports FP8 and INT4 kernels in llama.cpp/TensorRT. |
| CPU | i7-13650HX, 14 cores / 20 threads | Good for ONNX CPU models (VAD, turn, SER, CTC ASR). |
| RAM | **15 GiB** total, about 8 GiB available with the desktop running | Neo4j (JVM) plus browser plus CPU models is a real squeeze. |
| Disk | 293 GB free | Not a constraint. |

Today's GPU load: Qwen3-4B Q4_K_M (~3.5 GB) plus Whisper large-v3-turbo int8 (~1.3 GB), about 4.8 GB. **Adding vision or an LLM-based TTS means something else has to shrink or leave the GPU.** This is the main constraint behind every model decision in [`../v4/architecture.md`](../v4/architecture.md).

## 2. What exists and works

- **Streaming voice loop:** Silero VAD → faster-whisper → llama.cpp stream → sentence segmenter → Kokoro (EN) / Piper (TA) → 24 kHz PCM over WS (`backend/core/pipeline.py`).
- **Half-duplex echo guard** with playback-time estimation (`pipeline.py:281-289`, `:528-533`). This works around laptop-speaker feedback and was a real fix (see `docs/FIXES.md`).
- **Emotion:** SER (wav2vec2, CPU) runs in parallel with STT. FER (EmotiEffNet ONNX) runs on JPEG frames sent at 5 Hz. The two are fused and injected as a system fragment.
- **Memory seam:** Protocol interfaces (`backend/memory/interfaces.py`), event log table, memory artifacts, rolling summaries, optional Neo4j store. The architecture is right. The extraction and retrieval inside it are placeholders (see §3).
- **Tests:** 81 tests with fake engines (`tests/conftest.py`), plus e2e clients that synthesise speech.

## 3. Findings (ranked by impact on v4)

### 3.1 Memory is blind to Tamil and Tanglish *(bug, high)*
- `backend/memory/retriever.py:11`, `backend/memory/extractor.py:15` and `backend/memory/neo4j_store.py:18` tokenise with `[a-z0-9]+`. Tamil-script text produces **zero tokens**, so `_score()` returns 0 and Tamil memories never rank.
- `backend/memory/extractor.py:112` and the lines after it extract preferences, goals and employment with English-only regexes (`i like|i love|…`). A Tamil sentence like "எனக்கு biryani ரொம்ப பிடிக்கும்" is never stored.
- **Effect:** "knows me" only works in English today.
- **v4 direction:** LLM-based extraction during idle time, plus multilingual embeddings (see the model research doc §6).

### 3.2 Prompt layout defeats llama.cpp's prefix cache *(perf, high)*
- `backend/memory/context_assembler.py:123-131` builds `[system, emotion_fragment, memory_block, …history]`. The emotion fragment and memory block change every turn and sit **before** the history.
- llama.cpp reuses the KV cache only for an identical prefix. Each turn therefore re-processes the whole history, which grows with conversation length and adds TTFT.
- **v4 direction:** stable prefix first (persona → session-stable long-term memory → history), with volatile context (emotion, perception, per-query retrieval) placed **last**, next to the user turn.

### 3.3 Memory summaries are injected twice *(bug, low)*
- `pipeline._load_prompt` fills `{memory}` in the system prompt from `db.get_memories()`. `retriever.py:97` also appends the last 4 summaries to `semantic_memories`. The same text appears twice and wastes context.

### 3.4 A DB write per LLM token on the hot path *(perf, medium)*
- `pipeline.py:536` awaits `_record_event(event, …)` for **every streamed delta**, so an SQLite insert runs between tokens.
- **v4 direction:** buffer and write once per sentence/turn, or move event writes to a background queue.

### 3.5 TTS blocks the token loop *(latency, medium)*
- `pipeline.py:537-541`: `await speak(sentence)` runs inside `async for delta in llm.stream_chat(...)`. While a sentence is being synthesised, the loop does not consume tokens or emit text deltas.
- With sentence-sized chunks this serialises LLM and TTS instead of overlapping them.
- **v4 direction:** producer/consumer: a token reader feeds a sentence queue, and a TTS worker drains it.

### 3.6 Tanglish is forced to English voice *(language, high)*
- `backend/core/stt.py:41`: `language_probability < 0.7 → "en"`. Code-mixed speech is exactly where Whisper's LID is unsure, so Tanglish is routed to Kokoro (English voice) even when the reply is mostly Tamil.
- The greeting is hard-coded to English (`pipeline.py:455`).
- The TTS language is chosen from the **user's** language, not from the **reply text's** script.
- **v4 direction:** choose the voice per sentence from the reply text's script mix, and prefer a single voice model that speaks both languages.

### 3.7 Fixed 0.9 s end-of-turn silence *(latency, high)*
- `VAD_END_SILENCE_S=0.9` adds 900 ms of dead air before every reply. Lowering it causes cut-offs mid-thought.
- **v4 direction:** a semantic turn-end model (Smart Turn v3.x, ONNX CPU) that decides from the audio. Silence can then drop to about 0.2–0.4 s.

### 3.8 Camera path is the expensive kind *(perf + privacy, medium)*
- `frontend/src/hooks/useMicStream.ts:131-134` sends a 320×240 JPEG as base64 JSON every 200 ms. The server decodes it and runs FER on the CPU (`backend/api/ws.py:44-62`).
- About 5 JPEGs/s of bandwidth and decode buy only an emotion label. Nothing understands the scene, the activity or the posture.
- **v4 direction:** run per-frame perception **in the browser** (MediaPipe Face/Pose/Hand landmarkers on WebGL) and send compact feature JSON. Send a keyframe to the VLM only when it is needed.

### 3.9 SER model is English-acted, 4-class *(quality, medium)*
- `config.py:60`: `superb/wav2vec2-base-superb-er` is trained on IEMOCAP (acted English, 4 classes). Expect weak transfer to Tamil conversational speech.
- It also pulls `torch` and `transformers` into the backend image just for SER.
- **v4 direction:** emotion2vec+ (base or large) or an ONNX export of it.

### 3.10 Smaller issues
- `print()` instead of `logger` in failure paths (`pipeline.py:427`, `:478`, `:581`), so failures miss the rotating log.
- On disconnect, `shutdown()` runs the LLM summary and consolidation synchronously. That ties up the single llama.cpp slot right when a new session may start.
- Stale docs: `README.md`, `docs/docker.md:39` and `docs/API.md:48` still describe five personas (Clarity/Friend…). `tests/conftest.py` still mocks a Clarity persona.
- The Tamil TTS (Piper Valluvar medium) is intelligible but flat and robotic next to Kokoro. The voice changes from female EN to a different TA timbre mid-conversation.

## 4. UI audit (`frontend/src`)

**What it is:** "Quiet Room", a warm charcoal and amber single-column transcript. It has a serif assistant voice, a waveform footer, a status dot, a text fallback and a session drawer. The welcome screen is a single "begin" button.

**Strengths:** restrained and calm. Typography does the work (Newsreader + Inter). No card grids or gradients. Good bones.

**Gaps against the v4 goal:**
1. **Transcript-first, not presence-first.** The main thing on screen is text. A voice companion should foreground *the companion*: who is listening, thinking or speaking. Text should be secondary.
2. **No camera surface.** The camera turns on silently with the mic (`useMicStream.ts:71-78`). There is no self-view, no "camera is on" indicator and no off switch, which is a trust problem for a seeing companion.
3. **Perception is invisible**, apart from a debug-ish `user state: sad (63% confidence)` line (`App.tsx`). The user can't see what Medusa sees or correct it.
4. **Memory is invisible.** No way to see, edit or delete "what Medusa knows about me". For a long-term companion this is the core trust feature.
5. **No language affordance:** nothing shows EN/TA/mixed detection, and there is no way to pin the reply language.
6. **No latency or health view**, although the backend already exposes per-stage timings at `/api/health`.
7. **Mobile/second-device:** layout is fine, but nothing is designed for phone-as-camera or tablet-on-desk use.

The redesign proposal is in [`../v4/ui-redesign.md`](../v4/ui-redesign.md).

## 5. Latency today (from `docs/architecture.md`)

About 1.5–3 s from end of speech to first audio. Rough decomposition:

| Stage | Today | Main cause |
|---|---|---|
| End-of-turn wait | **900 ms** | fixed silence timeout (§3.7) |
| STT | ~250–300 ms | Whisper turbo on GPU, full utterance after the turn ends |
| LLM TTFT | ~300 ms+, grows with history | no prefix reuse (§3.2) |
| First sentence complete | +200–600 ms | waits for `.`/`?`/`!` before TTS |
| First TTS chunk | ~100–300 ms | Kokoro CPU per sentence |

The v4 target and the levers to reach it are in [`../v4/architecture.md`](../v4/architecture.md) §6.
