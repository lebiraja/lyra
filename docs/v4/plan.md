# Medusa v4: Master Plan

**Status:** APPROVED PLAN (2026-11-10), implementation not started · **Owner:** Lebi · **Checklist:** [checklist.md](checklist.md)
**Supersedes the decision content of** [architecture.md](architecture.md) and [roadmap.md](roadmap.md). Those stay as background and rationale; where they differ, **this file wins**.
**Evidence:** [audit](../research/2026-11-current-state-audit.md) · [model landscape](../research/2026-11-model-landscape.md) · [similar projects](../research/2026-11-similar-projects.md) · [reference repos](../research/2026-11-reference-repos.md)

Conventions:
- `[est]` = estimate, to be replaced by a measured number at the named gate.
- `D-nn` = a decision in `DECISIONS.md`.
- Every model choice has a **pre-decided fallback** if its gate fails, so no gate failure stops the project.

---

## 1. Goal, success criteria, non-goals

**Goal:** Medusa is a friend who lives on Lebi's laptop. She **hears** (words and tone), **sees** (face, expression, posture, activity via the webcam), **remembers** (facts, events, routines, moods, editable by him), and **talks back fast** in English, Tamil or Tanglish, mirroring him, in **one consistent Indian female voice**. Everything runs on one RTX 4050 6 GB with no cloud at runtime.

**v4.0 is done when all of these hold** (measured at gate G7, §20):

| # | Criterion | Target |
|---|---|---|
| S1 | End of speech → first audio, reflex turns | median ≤ 1.0 s, p90 ≤ 1.5 s |
| S2 | Think turns | spoken ack ≤ 0.8 s, answer audio ≤ 5 s |
| S3 | Language mirroring | reply language matches user (EN/TA/mix) in ≥ 90% of dialog-set turns |
| S4 | Memory recall | ≥ 8/10 recall probes answered correctly across sessions, EN↔TA cross-lingual |
| S5 | Vision | ≥ 80% correct activity/object answers on the vision set; never claims to see something absent |
| S6 | Stability | 30-min soak: no OOM, no echo loop, no crash, VRAM ≤ 5.9 GB peak |
| S7 | Degradation | killing `tts` or `llm` mid-session gives a spoken or visible degraded response within 3 s, and recovery happens without a reload |
| S8 | Privacy | no pixel or audio bytes persisted, verified by DB/volume scan |

**Non-goals for v4.0** (D-13, D-16, D-40): screen awareness, tools/MCP/web, wake word, desktop wrapper, multi-user, speaker verification, avatar, end-to-end speech-to-speech models, public distribution.

---

## 2. Decisions at a glance

Full text is in `DECISIONS.md`.

**From Lebi (D-11…D-22):**
- one Indian female voice for everything
- balanced initiative (≤ 1 unprompted line / 15 min)
- camera only
- abstract "Marginalia" UI
- personal use only
- pure companion
- open app, then hands-free
- Medusa owns the GPU
- mirror the user's language
- remember everything, editable
- think ack ≤ 0.8 s and answer ≤ 5 s
- eval voice from `voice-auth`, open-source images

**Technical (D-23…D-40):**
- Gemma 4 E4B is the single brain that hears and sees
- 2 llama.cpp slots with a priority scheduler
- parallel hear
- self-routing control tags
- mood tags plus a PAD mood
- cache-stable prompt
- two-lane perception
- GLaDOS-style initiative engine
- SQLite as source of truth with vec, FTS5-trigram and Neo4j projections
- numbered migrations
- Pydantic-first protocol v4
- single-user takeover
- half-duplex echo, then AEC
- TaskGroup concurrency
- tracing and health
- GPU only in `llm` and `tts`
- Tamil fonts and shadcn
- v4.1 deferrals

---

## 3. Hardware budget

Measured host: RTX 4050 Laptop **6141 MiB** (sm_89), i7-13650HX **14C/20T**, **15 GiB RAM**, CachyOS. Per D-18 Medusa owns the GPU, and `make preflight` refuses to start if another process holds more than 300 MiB of VRAM (override: `FORCE=1`).

### 3.1 VRAM, Profile A (primary)
| Item | Est. | Notes |
|---|---|---|
| Gemma 4 E4B Q4_0 weights + mmproj Q8_0 | ~3.6 GB | GLaDOS measured a 4.1 GB total allocation at 4k ctx, 1 slot (RTX 3080) |
| KV cache, 2 slots × 6144, q8_0, `--swa-full` | ~0.5–0.8 GB | measure at G0. If over budget, drop to `-c 10240` |
| llama.cpp CUDA context | ~0.3 GB | |
| Indic-Mio LM (0.6B bf16) + MioCodec | ~1.0–1.4 GB | torchao int8 if needed, giving ~0.7 GB |
| PyTorch CUDA context (`tts`) | ~0.3 GB | |
| **Total** | **~5.4–5.8 GB** | **budget 5.6, hard cap 5.9** |

**Over-budget ladder** (applied in order until G0 passes):
1. Indic-Mio int8
2. `-c 10240`
3. `-c 8192`
4. glance image resolution down to the 256-token minimum
5. Profile B (§4.2)

### 3.2 RAM (15 GiB, desktop and browser ~5 GB)
| Process | Est. |
|---|---|
| backend (Silero, Smart Turn, emotion2vec+ base, EmbeddingGemma-300M, Kokoro + Piper fallback, app) | ~2.5–3 GB |
| neo4j (heap 1G + page cache 512M) | ~1.6 GB |
| llama.cpp host side (`--cache-ram 2048` prompt cache) | ~2.5 GB |
| tts host side | ~1 GB |
| Chrome tab (MediaPipe worker, UI) | ~0.8 GB |
| **Total** | **~8.5–9 GB**, leaving ~1–1.5 GB headroom; measured at G0 |

### 3.3 CPU thread plan (20 threads)
| Component | Threads |
|---|---|
| Silero VAD | 1 |
| Smart Turn | 4 (only during pauses) |
| emotion2vec+ | 4 (per utterance) |
| EmbeddingGemma | 4 (idle only) |
| Kokoro/Piper fallback | 4 (only when degraded) |
| llama.cpp CPU-side | default |

Set via ORT/torch `intra_op` settings.

---

## 4. Model bill of materials

### 4.1 Profile A (primary)
| Role | Artifact (exact) | Runtime | Device | Licence | Gate | Fallback if gate fails |
|---|---|---|---|---|---|---|
| Brain (hear + see + talk) | `ggml-org/gemma-4-E4B-it-GGUF`: `gemma-4-E4B-it-Q4_0.gguf`, `mmproj-gemma-4-E4B-it-Q8_0.gguf` | llama.cpp `server-cuda`, pinned to a build verified with Gemma 4 audio (GLaDOS tested `687e7789`) | GPU | Apache-2.0 (Gemma 4) | G1, G2 | Profile B |
| Voice | `SPRINGLab/Indic-Mio` (Qwen3-0.6B LM, `speech_offset 151669`, audio vocab 12800) + `Aratako/MioCodec-25Hz-24kHz` | PyTorch bf16 (torchao int8), new `tts` service | GPU | read the model card at P3 (personal use, D-15) | G3 | ① Svara-TTS-v1 Q4 GGUF via llama.cpp + SNAC; ② Indic-Speak (gated); ③ Kokoro EN + Piper TA (current) |
| Voice identity | one female Indian reference clip (10–30 s) → MioCodec global embedding, saved as `config/voice/medusa.pt` | — | — | must be a clip Lebi is allowed to use (Indic-Mio samples or one he provides) | G3 listening | another Indic-Mio sample |
| VAD | Silero v5 ONNX (`models/silero/silero_vad.onnx`) | onnxruntime | CPU | MIT | — | — |
| Turn end (EN/other) | `pipecat-ai/smart-turn-v3` v3.2 CPU int8 ONNX | onnxruntime | CPU | BSD-2 | G5 | silence timeout 0.9 s (v3 behaviour) |
| Turn end (TA/mix) | `santhosh-005/smart-turn-tamil` | onnxruntime | CPU | check card | G5 | own fine-tune with the smart-turn training script on our turn set |
| Voice emotion | `emotion2vec/emotion2vec_plus_base` | FunASR / torch | CPU | check card | G6 | keep v3 `superb/wav2vec2-base-superb-er` |
| Face + body | MediaPipe `face_landmarker.task` (blendshapes) + `pose_landmarker_lite.task`, `@mediapipe/tasks-vision` (pinned) | WASM + WebGL in a Web Worker | client GPU | Apache-2.0 | G9 | face only, at 10 fps |
| Scene / activity | the brain, on a keyframe (slot 1) | llama.cpp | GPU (shared) | — | G1 | SmolVLM2-256M captioner on CPU (Vocalis pattern) |
| Embeddings | `google/embeddinggemma-300m` | sentence-transformers | CPU | Gemma terms | G4 | `Qwen/Qwen3-Embedding-0.6B` |
| Degraded TTS | Kokoro-82M v1.0 ONNX `af_heart` + Piper `ta_IN-Valluvar-medium` (existing) | onnxruntime | CPU | Apache-2.0 / MIT | — | — |

### 4.2 Profile B (adopted only if G1 or G2 fails for E4B)
| Role | Artifact | Device |
|---|---|---|
| Brain | `Qwen3.5-4B` Q4_K_M + its mmproj | GPU |
| STT (EN + LID) | faster-whisper `large-v3-turbo` int8 | GPU (~1.3 GB) |
| STT (TA/mixed) | `ai4bharat/indic-conformer-600m-multilingual` int8 via sherpa-onnx (CTC) | CPU |
| Voice | Indic-Mio **int8** | GPU |

Routing in Profile B: Whisper LID decides, and if it says `ta` or the probability is < 0.7, IndicConformer runs. Everything else in the plan is identical. Only the hear stage swaps (`HearStage` interface, §6.3).

### 4.3 Removed from the stack in v4
- Server-side FER (`hsemotion-onnx`, `opencv-python-headless`) and the 5 Hz JPEG stream.
- faster-whisper (Profile A).
- The CUDA base image for `backend`: it becomes `python:3.12-slim`, CPU-only.
- `superb/wav2vec2` SER (after G6).

### 4.4 Downloads (`make models` v4)
`scripts/download_models.sh` gains these steps, all host-side `hf download` or `curl` calls, **never host Python** (guarded by `tests/test_scripts.py`):
- `models/llm/gemma-4-E4B-it-Q4_0.gguf` and `models/llm/mmproj-gemma-4-E4B-it-Q8_0.gguf`
- `models/tts/indic-mio/` and `models/tts/miocodec/`
- `models/turn/smart-turn-v3.2-cpu.onnx` and `models/turn/smart-turn-tamil.onnx`
- `models/mediapipe/{face_landmarker,pose_landmarker_lite}.task` (served by nginx)
- emotion2vec+ and EmbeddingGemma go into the HF cache volume (first backend start, like today)

Weights are never baked into images (D-15).

---

## 5. System architecture

### 5.1 Services (docker compose v4)
| Service | Image | GPU | Ports (host) | Depends on | Health |
|---|---|---|---|---|---|
| `llm` | `ghcr.io/ggml-org/llama.cpp:server-cuda-<pinned>` | yes | 127.0.0.1:2380 | — | `GET /health` |
| `tts` | `lyra-tts` (new, `nvidia/cuda:12.x-runtime` + torch) | yes | 127.0.0.1:2381 | `llm` healthy (so VRAM is measured after the brain loads) | `GET /health` → `{mode: gpu_bf16\|gpu_int8\|unavailable}` |
| `neo4j` | `neo4j:5-community` (heap 1G) | no | 127.0.0.1:7474/7687 | — | cypher-shell `RETURN 1` |
| `backend` | `lyra-backend` (`python:3.12-slim`) | **no** | 127.0.0.1:2324 | `llm` healthy; `tts` started; `neo4j` started (not required healthy) | `GET /api/health` |
| `frontend` | nginx + built SPA + MediaPipe assets | no | 2000 | backend | `GET /` |

- The network stays `clarity` and services address each other by name: `http://llm:8080`, `http://tts:8081`, `bolt://neo4j:7687`.
- Volumes: `clarity-data` (SQLite), `whisper-cache` (renamed in docs to "hf-cache", same volume), `neo4j-data`, `./logs`, `./models` (ro).

`llm` command:
```
-m /models/llm/gemma-4-E4B-it-Q4_0.gguf --mmproj /models/llm/mmproj-gemma-4-E4B-it-Q8_0.gguf
--host 0.0.0.0 --port 8080 -ngl 999 -c 12288 --parallel 2 --cont-batching
--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --swa-full
--cache-prompt --cache-ram 2048 --reasoning off --jinja -b 2048 -ub 512 --metrics
```

### 5.2 Backend module layout (new or changed)
```
backend/
  api/            rest.py (v4 endpoints), ws.py (protocol v4, takeover), protocol.py (Pydantic = source of truth)
  core/
    session.py        Session: TaskGroup per connection (replaces most of pipeline.py)
    turn.py           TurnController: state machine, turn_id, cancel token, trace
    hear.py           HearStage interface; NativeAudioHear (E4B) | WhisperIndicHear (Profile B)
    brain.py          BrainClient: llama.cpp chat (slot pinning, control-tag parser, deadlines)
    scheduler.py      InferenceScheduler: priority queues per slot, preemption
    voice.py          VoiceStage: clause segmenter, mood/lang tagging, TTS client, PCM validation, fallback
    tts_fallback.py   existing Kokoro/Piper TTSRouter (moved from tts.py)
    turn_detect.py    Silero + SmartTurn (lang-routed) + caps
    affect.py         emotion2vec+ wrapper + PAD mood state
    perception.py     PerceptState, windows, events, glance trigger policy
    initiative.py     slots, reviewer loop, ledger, quiet mode
    language.py       script ratios, lang decision, Tamil normalisation helpers
    resilience.py     CircuitBreaker, Deadline, retry/backoff utils
    trace.py          per-turn trace spans
  memory/
    interfaces.py (kept, extended) · store_sqlite.py · migrations/NNN_*.sql · migrate.py
    extractor_llm.py · retriever_hybrid.py · embedder.py · graph_projection.py (Neo4j outbox worker)
    profile.py · worker.py (MemoryWorker: idle jobs)
  events.py       EventWriter (batched, single writer)
tts_service/      FastAPI app for Indic-Mio (separate image)
```
The existing `ConversationPipeline` is decomposed rather than rewritten from scratch. Its echo-guard logic (`_busy`, `_plays_until`, `_echo_guard_until`) moves verbatim into `TurnController`, with its tests (`tests/test_echo_guard.py`) kept passing.

### 5.3 Concurrency model (D-36)
- **Per connection:** `Session` owns an `asyncio.TaskGroup`:
  - `audio_in`: mic frames → turn detector → `TurnController.on_utterance`
  - `turn`: at most one active `Turn` (`turn_id`, `CancelScope`); a new turn or barge-in cancels it
  - `tts_worker`: consumes `SentenceQueue(maxsize=8)` → PCM → `send_bytes`
  - `percept_agg`: consumes percept JSON → `PerceptState`
  - `initiative`: ticks every 10 s, see §12
- **Global singletons:**
  - `InferenceScheduler`: slot 0 is a single-flight queue; slot 1 is a priority queue (`transcript=0 > glance=1 > autonomy=2 > extraction=3`)
  - `EventWriter`: `asyncio.Queue` → batched SQLite inserts every 100 ms or 50 rows
  - `MemoryWorker`: runs jobs only when `Session.idle_for() ≥ 20 s` or there is no session
- **Takeover (D-34):** a global `ActiveSession` lock. A new `hello` → the old session gets `error{code:"session_taken_over"}`, is shut down, then the new session starts.
- **Blocking work** (ONNX, torch CPU) runs in `run_in_executor` with a dedicated `ThreadPoolExecutor(max_workers=6)`, never in the event loop.

---

## 6. Full flows

### 6.1 Boot
```
make preflight ─ nvidia-smi: other GPU procs? free VRAM ≥ 5.7 GB? ─ no → abort (FORCE=1 overrides)
docker compose up
  llm      load E4B + mmproj → /health ok                                   (~30–60 s)
  tts      wait llm healthy → torch.cuda.mem_get_info()
           free ≥ 1.6 GB → bf16 │ ≥ 1.0 GB → int8 │ else mode=unavailable
           load Indic-Mio + codec + voice embedding → warmup 2 phrases → /health ok
  neo4j    start (heap 1G)
  backend  run migrations (backup db first) → load CPU models (each optional, logged)
           → probe llm/tts/neo4j → pre-synthesise canned lines (§16.3) via tts (or fallback)
           → graph projection catch-up (outbox) in background → /api/health
  frontend nginx
```

### 6.2 Arrival
1. The UI arrival screen offers **talk** or **talk + see me**. The camera is off unless chosen (§18).
2. WS connects → client `hello{protocol:4, session_id?, camera:bool, lang_pin}`.
3. Server: version check (mismatch → close 4400), takeover, then resume or create the session.
4. **Freeze the prefix:** persona + current person profile v{n} rendered once. They don't change for the session.
5. `session{session_id, profile_version}` → `state{listening}`.
6. If fresh, the initiative "arrival" slot is published → reviewer → greeting (§12) in the last-used language (from the profile), using memory.

### 6.3 Voice turn (reflex)
```
mic 16k int16 (0x01 frames, ~64 ms)
  │  echo guard: drop while busy/tail (half-duplex, D-35)
  ▼
Silero (32 ms frames) ── speech_start → state{listening}, initiative.defer()
  │ pause ≥ 200 ms
  ▼
SmartTurn(lang = last user lang) ── P ≥ θ_lang → END
  │ else continue; END forced at silence ≥ 1.5 s or utterance ≥ 28 s
  ▼
utterance (float32 16 k) ── TurnController.start(turn_id)
  ├─(a) slot 0  BrainClient.reply(prefix + <now> + audio)        stream ─┐
  ├─(b) slot 1  BrainClient.transcribe(audio)  deadline 2.0 s            │
  └─(c) CPU     emotion2vec+(audio)            deadline 0.4 s            │
                                                                        ▼
first tokens → ControlTagParser: "[think]" | "[look]" | "[mood:x]" | text
  reflex: text deltas → assistant_delta → ClauseSegmenter
          → chunk(text, lang_by_script, emotion) → SentenceQueue → tts_worker
          → tts /synthesize (stream) → validate PCM → 0x02 frames → browser
  (b) done → user_transcript event; history entry = transcript (audio dropped)
  (c) done → affect → PAD update; recorded on the turn
assistant_done → EventWriter(trace) → end_busy() (echo tail) → state{listening}
```
- **Hear mode** (D-25): `HEAR_MODE=parallel` (default) or `transcript_first`. G7 picks the default. In `transcript_first`, (b) runs first, then (a) uses transcript text plus the audio.
- **History rule:** only the *current* user turn carries audio. Once (b) finishes, the stored history message is the transcript, so the prefix stays text and cacheable. If (b) fails, the history stores `"[voice message, transcript unavailable]"` plus the reply, and the memory extractor skips the turn.

### 6.4 Think and look turns (D-26)
- **`[think]`:**
  1. Cancel the current stream at the tag.
  2. Enqueue the pre-synthesised ack (`ack_think_{en,ta,mix}`, §16.3). Audio plays in ≤ 0.8 s.
  3. `state{thinking}`.
  4. Re-issue on slot 0 with thinking enabled (`chat_template_kwargs.enable_thinking=true`, the exact knob verified at P2), `max_tokens` = 384 reasoning + 160 answer, and a **deadline of 4.5 s** from turn start.
  5. On deadline: cancel and re-issue as reflex with an instruction to answer briefly ("short answer now") so an answer always arrives ≤ 5 s.
  6. Reasoning text is never spoken. It is stored on the turn event, and the UI shows it collapsed (off by default).
- **`[look]`:**
  1. Cancel at the tag. Send `request_keyframe{turn_id, reason}`.
  2. The client replies with a `0x03` JPEG (≤ 640 px long edge, q 0.8) within 600 ms.
  3. Re-issue with the image, then speak.
  4. If the camera is off or there is a timeout: re-issue with `<now>camera=off</now>`, and she says she can't see right now.
- A tag found anywhere other than the first 8 tokens is ignored and stripped. At most one re-issue per turn, so there are no loops.

### 6.5 Typed turn
`user_text` → same as §6.3 from step (a) with text in place of audio. (b) and (c) are skipped.

### 6.6 Perception loop (D-29)
```
worker (browser): camera 640x480 → FaceLandmarker @15 fps, PoseLandmarker lite @5 fps
   → features (§10.2) → percept @4 Hz (JSON, ~300 B) ─┐
   → scene_change score (64x48 grey diff)            ─┤
server PerceptState ← percept; windows 5 s / 60 s / session; derive attention, tired, mood_face
   → events (debounced): user_arrived, user_left, looks_tired, long_focus, stood_up, scene_changed
glance policy: trigger on user_arrived | scene_changed | [look] | idle refresh
   cadence 2–5 s while scene changes (max 1 / 2 s), 60–300 s otherwise; never during a user turn
   → request_keyframe → slot-1 glance (deadline 2.5 s) → SceneNote{scene, activity, objects[],
     expressions, changes, t} → scene event to UI; <now> uses latest (with age)
```
Perception **never triggers speech directly**. It only publishes to initiative slots (§12).

### 6.7 Idle and memory loop
```
Session idle ≥ 20 s or session closed → MemoryWorker picks memory_jobs (oldest first)
  extract(turn window) → slot 1, JSON schema (§7.6), deadline 15 s
     invalid JSON → 1 repair retry → fail → status=dead (retry at next idle, max 3, then parked)
  apply: upsert entities; facts (supersede by canonical key → close valid_to); episode per session
  embed new rows (EmbeddingGemma) → sqlite-vec; FTS5 index via triggers
  graph_outbox rows → GraphProjection worker → Neo4j MERGE (idempotent by row id)
session end → episode summary + profile regeneration job (person_profile v{n+1}, used next session)
nightly (first idle after 03:00) → patterns job over perception_minutes + episodes
```

### 6.8 Shutdown (fixes audit §3.10)
On WS close:
1. Cancel the active turn (partial assistant text saved).
2. Cancel the session TaskGroup.
3. **Enqueue** the consolidation and profile jobs instead of running them inline.
4. Release `ActiveSession`.

The MemoryWorker runs them while no one is talking.

### 6.9 Turn state machine
```
             ┌──────────── hello ─────────────┐
             ▼                                 │
 IDLE ──► LISTENING ──speech_start──► CAPTURING ──end──► HEARING ──first token──► SPEAKING
   ▲          ▲  ▲                         │                 │  ├─[think]─► THINKING ─► SPEAKING
   │          │  │                         │ (barge-in only  │  └─[look]──► LOOKING ──► SPEAKING
   │          │  └──── echo tail ◄── DONE ◄┴─ if AEC on) ◄───┘
   │          └──────── initiative line ◄── GREETING/INITIATIVE (only from LISTENING, idle ≥ 2 s)
   └─ close ─ any state (cancel + persist partial)
 errors in HEARING/THINKING/LOOKING/SPEAKING → ERROR_SPOKEN (canned line) → DONE
```
States sent to the client: `listening | capturing | hearing | thinking | looking | speaking`. v3's `transcribing`/`generating` are renamed.

---

## 7. Prompts and context

### 7.1 Layout per slot-0 request (D-28, fixes audit §3.2–3.3)
| # | Part | Changes when | Cached |
|---|---|---|---|
| 1 | persona system prompt (`config/personas/medusa.yaml` v2) | release | yes |
| 2 | person profile v{n} (≤ 300 tokens) | session start only | yes |
| 3 | history (windowed, text only) | append-only in session | yes, incrementally |
| 4 | `<now>` block (≤ 350 tokens) | every turn | no |
| 5 | current user turn (audio or text, optional image) | every turn | no |

- The window keeps the newest turns that fit `6144 − max_tokens − |1..2| − 350 − audio_tokens`. When old turns fall off, the cut is made at whole-turn boundaries. Dropped turns survive in memory, not in the prompt.
- The `{memory}` slot is replaced by the profile. Rolling summaries are **no longer** injected separately; they feed the profile job instead.

### 7.2 Persona v2 additions (to `medusa.yaml`)
Keeps the v3 human-touch rules (1–3 short sentences, casual, no emojis or markdown, no therapy clichés, crisis override). Adds:
- **Language:** reply in the language mix the user just used (`lang` in `<now>`). Write Tamil words in Tamil script and English words in Latin script. Never translate the user's words back at them.
- **Control:** start with `[think]` only if the question needs real reasoning (a decision, planning, multi-step). Start with `[look]` only if answering needs the camera. Otherwise answer directly. Optionally put `[mood:happy|sad|surprised|calm]` first.
- **Perception honesty:** use `<now>` only when it helps the moment. Never narrate it ("I can see you yawning"); weave it in like a friend would. Never claim to see or remember anything absent from `<now>` or the profile.

### 7.3 `<now>` block (example)
```
<now time="Tue 23:40" lang="mix" lang_pin="auto" camera="on" route_hint="">
 sees(40s ago): at desk, dim room, code on screen, mug in hand
 face: tired (yawns 3/5min, PERCLOS 0.31) · voice: low energy (e2v: sad 0.41)
 body: slouched ~70 min, no stand-up since 22:30
 medusa_mood: P0.2 A0.1 D0.1
 memory: exam Fri 15 Nov (said Sun) · usually sleeps ~01:00 · likes filter coffee
</now>
```

### 7.4 Transcript prompt (slot 1, `temperature 0`, `max_tokens 200`)
"Transcribe exactly what was said. Write Tamil words in Tamil script and English words in Latin script. Do not translate, correct or add anything. If there is no speech, output `<none>`. Output only the transcript."

### 7.5 Glance prompt (slot 1, JSON schema-constrained, `max_tokens 220`)
Output schema: `{scene:str, activity:str, objects:[str], person_present:bool, expressions:{face:str, gaze:str, posture:str}, changes:str}`.
- Rules: describe the person first. If a face is small or obscured, set `face:"unclear"`. Never infer feelings beyond the visible expression.
- The previous SceneNote is included so that `changes` is relative to it.

### 7.6 Memory extraction schema (slot 1, JSON schema-constrained)
```json
{"facts":[{"subject":"user|<entity>","predicate":"likes|works_at|has_exam|sister_is|…",
           "object":"…","valid_from":"ISO|null","valid_to":"ISO|null","confidence":0.0,
           "canonical_key":"predicate:subject[:object]","negates":false}],
 "entities":[{"name":"…","type":"person|place|org|thing|event","aliases":["…"]}],
 "episode_note":"one sentence, third person, in the language spoken",
 "mood":{"label":"…","evidence":"voice|face|words"}}
```
Input: the turn window, plus the active facts with the same `canonical_key` prefix (so the model can supersede or negate them), plus perception minutes for that window.

### 7.7 Autonomy reviewer schema (GLaDOS pattern)
`{"action":"null"}` or `{"action":"prompt","instruction":"…","slot_ids":["…"],"reason":"…"}`. A uniform object (no bare `null`). `max_tokens 256`, thinking off.

---

## 8. Language strategy (D-19)

- **Script ratio** of a text: `ta = count(U+0B80–U+0BFF letters)`, `la = count([A-Za-z])`, `r = ta / (ta + la)`.
  - `r ≥ 0.6` → `ta`, `r ≤ 0.1` → `en`, else `mix`.
- **User language** = the ratio on the transcript. If there's no transcript yet, the previous turn's language is used.
- **Reply hint:** `lang` in `<now>` = the user language of the current turn (or `lang_pin` if set).
- **TTS language per chunk:** `Tamil` if the chunk contains any Tamil-script letter, else `English`. Indic-Mio receives the whole Tanglish chunk under `Tamil`. G3 verifies English words inside it are read naturally. If G3 shows breakage, the fallback is to split the chunk at script boundaries and synthesise sub-chunks with the same voice embedding.
- **Normalisation before TTS:** strip markdown, emojis and emoticons (existing `clean_for_speech`, `strip_emojis_and_emoticons`). Expand numbers, dates, times and currency per language with a small rule set modelled on Maya3's normaliser (Apache-2.0, `reference/MayaResearch_maya2-native/maya3/text/`).
- **Fonts:** Noto Serif Tamil / Noto Sans Tamil, with `lang="ta"` spans (D-39).

---

## 9. Voice pipeline (D-11, D-27)

### 9.1 Segmentation
- The first chunk is cut at the first clause boundary (`, ; — : ?` or `!`) once it has ≥ 3 words, or at 9 words.
- Later chunks break at sentence boundaries, with a 220-character cap.
- The leading `[mood:x]` tag is parsed once per reply and applies to all chunks.

### 9.2 TTS service API (`tts_service/`, port 8081)
| Endpoint | Body | Returns |
|---|---|---|
| `POST /synthesize` (streaming) | `{text, language:"Tamil"\|"English", emotion?:str, voice:"medusa", turn_id, chunk_id}` | `application/octet-stream`: 24 kHz int16 mono, first bytes ASAP; `X-TTFA-ms`, `X-RTF` trailers in a final JSON line on a side channel |
| `GET /health` | — | `{status, mode, vram_mb, voice_loaded, warm}` |
| `GET /voices` | — | `["medusa", "indic_sample1..4"]` |

Internals follow the iNavLabs `mio_session.py` pattern: Qwen3 chat template, audio tokens `id − speech_offset`, `MioCodec.decode` re-decoding the full context every 16 tokens (`decode_every`) and emitting only the fresh tail. The voice is a fixed `global_embedding` (D-11). The emotion maps from mood: `happy, sad, angry, surprise` (Indic) or `happy, sad, confused, whisper, enunciated` (English).

### 9.3 PCM validation (backend, before sending)
A chunk is rejected, and resynthesised on the fallback engine, when any of these hold:
- NaN or Inf present
- RMS < −50 dBFS over the whole chunk
- duration outside `[0.04 s/char × 0.3, 0.12 s/char × 2]` of the text length
- first-chunk latency > 1.5 s

### 9.4 Fallback (D-38)
`VoiceStage` holds a `CircuitBreaker(tts)` (3 failures in 60 s → open 30 s → half-open probe). While open, chunks go to the CPU `TTSRouter` (Kokoro EN / Piper TA, existing code). The client receives `voice_degraded{reason}` once, and the UI shows a quiet "backup voice" note.

---

## 10. Perception (D-13, D-29)

### 10.1 Browser worker contract
Adapted from airi's `PerceptionState` (`reference/moeru-ai_airi/packages/model-driver-mediapipe/src/types.ts`):
```ts
type Percept = {
  t: number;                                   // performance.now() ms
  quality: { fps: number; latencyMs: number; dropped: number };
  face: null | { yaw: number; pitch: number; roll: number;
                 bs: { smile: number; frown: number; browUp: number; browDown: number;
                       eyeClose: number; jawOpen: number; squint: number; cheekPuff: number } };
  pose: null | { slouch: number; lean: number; standing: boolean };
  motion: number;          // 0..1 frame-diff energy
  sceneChange: number;     // 0..1 vs last keyframe
};
```
- Jobs: face at 15 fps, pose at 5 fps, with a dropped-frame policy (skip if busy).
- Upload at 4 Hz.
- On a crash, the worker restarts with backoff 1/2/4 s, up to 3 times, then perception is turned off with a notice.

### 10.2 Server-derived signals (`PerceptState`)
| Signal | Rule (initial thresholds; tuned on the vision set) |
|---|---|
| `present` | face or pose present in ≥ 60% of the last 5 s |
| `attention` | present ∧ \|yaw\| < 25° ∧ \|pitch\| < 20° |
| `yawn` | jawOpen > 0.6 for ≥ 1.2 s |
| `perclos` | fraction of the last 60 s with eyeClose > 0.7 |
| `tired` | yawns ≥ 2 in 5 min ∨ perclos > 0.25 |
| `smile_ratio` | mean(smile > 0.5) over the window |
| `slouch_long` | slouch > 0.5 for ≥ 30 min |
| `face_affect` | small rule map over blendshapes → {neutral, happy, sad, surprised, tense}; confidence = margin |

**Events** (debounced, minimum gap per type): `user_arrived` (absent ≥ 60 s → present), `user_left` (present → absent ≥ 60 s), `looks_tired`, `long_focus` (attention ≥ 45 min, no talk), `stood_up`, `scene_changed` (sceneChange > 0.35).

`perception_minutes` rows are written once per minute: presence, attention, tired, smile_ratio, face_affect histogram, slouch. These are numbers only, for the patterns job.

### 10.3 Glance
See §6.6. The SceneNote is kept in RAM for the session, and only text is ever persisted (as part of an episode or mood note). Keyframes are discarded after inference (S8).

---

## 11. Memory v4 (D-20, D-31, D-32)

### 11.1 Schema (migration `002_memory_v4.sql`; `001_baseline.sql` = current v3 schema)
```sql
schema_version(version INTEGER PRIMARY KEY, applied_at TEXT)
entities(id INTEGER PK, name TEXT, type TEXT, aliases_json TEXT, created_at, updated_at)
facts(id INTEGER PK, canonical_key TEXT, subject_id INT, predicate TEXT, object TEXT,
      confidence REAL, confirmations INT DEFAULT 1, status TEXT CHECK(status IN('active','superseded','deleted')),
      valid_from TEXT, valid_to TEXT, recorded_at TEXT, source_event_id INT, session_id TEXT, lang TEXT)
episodes(id INTEGER PK, session_id TEXT, started_at, ended_at, summary TEXT, mood TEXT, lang TEXT, people_json, topics_json)
patterns(id INTEGER PK, kind TEXT, description TEXT, evidence_json, confidence REAL, updated_at)
perception_minutes(minute TEXT PK, present REAL, attention REAL, tired INT, smile REAL, affect_json, slouch REAL)
person_profile(version INTEGER PK, text TEXT, created_at, source_fact_ids_json)
memory_jobs(id INTEGER PK, kind TEXT, payload_json, status TEXT, attempts INT, last_error TEXT, created_at, updated_at)
graph_outbox(id INTEGER PK, op TEXT, entity TEXT, row_id INT, payload_json, created_at, done_at)
initiative_ledger(id INTEGER PK, attention_key TEXT, revision INT, delivered_at TEXT, turn_id TEXT)
vec_memory USING vec0(embedding float[768])   -- rowid = memory_items.id
memory_items(id INTEGER PK, kind TEXT CHECK(kind IN('fact','episode','pattern')), ref_id INT, text TEXT, lang TEXT)
fts_memory USING fts5(text, tokenize='trigram', content='memory_items', content_rowid='id')
```
Indexes go on `facts(canonical_key, status)`, `facts(subject_id)`, `memory_jobs(status, created_at)` and `graph_outbox(done_at)`. Existing v3 tables (`sessions`, `messages`, `conversation_events`, `memory_artifacts`, `memories`) are kept. `001→002` migrates `memory_artifacts` to `facts` (one-off backfill job) and `memories` summaries to `episodes`.

### 11.2 Migration runner
- `backend/memory/migrate.py` applies `migrations/NNN_*.sql` in order, inside a transaction, and records `schema_version`.
- Before applying, it copies `medusa.db` to `data/backups/medusa-<ts>.db` (last 5 kept).
- Forward-only. A failure aborts startup with a clear log; the DB is untouched, because the migration is transactional.
- **This PR needs Lebi's approval** (CLAUDE.md: migrations).

### 11.3 Write path
§6.7. Supersede rule: a new fact with the same `canonical_key` and a different `object` closes the old fact (`valid_to = now`, `status = 'superseded'`) and inserts the new one. The same `object` again → `confirmations += 1`, `confidence = min(1, c + 0.1)`. A fact with `negates = true` closes the old one without inserting a new one.

### 11.4 Read path (per turn, deadline 150 ms, CPU)
1. `q` = transcript (or the previous turn's text if the transcript is still pending), plus entity names found in it.
2. In parallel:
   - vec top 20 (EmbeddingGemma `q`)
   - FTS5-trigram top 20
   - Neo4j: 1-hop neighbours of matched entities (deadline 80 ms, skipped if the breaker is open)
3. **RRF** with k = 60. Score × `decay`, where decay = 1 if `confirmations ≥ 2`, else `exp(−age_days / 60)`. Only active facts count.
4. Take the top-k that fit a 180-token memory budget inside `<now>`.

Because of the parallel-hear timing, retrieval for turn *n* uses the turn *n−1* transcript plus the running topic. The profile covers stable facts. **G4 and G7 measure** whether this lag hurts recall. The fallback is transcript-first hear mode.

### 11.5 Profile
At session end, a job (slot 1) writes a ≤ 300-token profile from active facts (confidence-weighted), top patterns and the last 5 episodes, as `person_profile v{n+1}`. Session start freezes the latest version (D-28).

### 11.6 Neo4j projection
- Nodes: `(:Person {id})` and `(:Entity {id, name, type})`.
- Edges: `[:FACT {fact_id, predicate, valid_from, valid_to, status}]`.
- `[:MENTIONED_IN]->(:Episode)`.
- Idempotent `MERGE` by SQLite id. The outbox gives at-least-once delivery.
- `make graph-rebuild` wipes and replays everything from SQLite. **Neo4j is never the source of truth.**

### 11.7 Notebook API (UI, §15) and "forget"
- "Forget that" (voice or UI) deletes the facts extracted from the last turn (`source_event_id`).
- Deleting a fact sets `status = 'deleted'`, removes its `memory_items`/vec/fts rows, and enqueues an outbox delete.
- "Forget everything" requires confirmation, then truncates all memory tables, vec, fts and Neo4j, keeping sessions and messages unless "also conversations" is ticked.

---

## 12. Initiative engine (D-12, D-30)

| Mind (publishes slot) | Slot content | Importance |
|---|---|---|
| Arrival (perception) | `user_arrived` + absence length + time of day | important if absent ≥ 2 h or it's the first sighting today |
| Follow-up (memory) | a due fact (`has_exam`, `valid_from` today/tomorrow), an open thread from the last episode | important |
| Wellbeing (perception + affect) | `long_focus` ∧ `tired`, `slouch_long`, low mood after a sad turn | regular → important if sustained 15 min |
| Silence (Vocalis tiers) | user went quiet ≥ 45 s after Medusa asked a question | regular, tier 0→2 |

**Loop:**
- Ticks every 10 s.
- Skips while the state ≠ LISTENING, during user speech + 2 s, during quiet mode (`quiet{minutes}` or "be quiet"), or within the **15-min cooldown** since the last unprompted line (D-12).
- Silent back-off 40→80→120 s.
- The reviewer (slot 1, §7.7) sees the slots plus the last 8 turns plus the profile.
- `prompt` → the instruction runs through the normal slot-0 reply path (state `GREETING/INITIATIVE`), and the delivery is written to `initiative_ledger(attention_key, revision)`, so the same condition is never announced twice.
- The **arrival greeting is exempt from the cooldown**, once per arrival.

**PAD mood (Medusa's own):**
- `P`, `A`, `D` ∈ [−1, 1], baseline (0.3, 0.1, 0.1), half-life 10 min toward the baseline.
- Each turn: `P += 0.3·user_valence + 0.2·reply_mood_valence`, `A += 0.3·user_arousal`, clamped.
- Maps to the default TTS emotion when the reply has no `[mood]`: P > 0.45 ∧ A > 0.35 → happy; P < −0.3 → sad; else none.

---

## 13. Protocol v4 (D-33)

- **Single source of truth:** `backend/api/protocol.py` (Pydantic v2, discriminated union on `type`).
- `make protocol` exports JSON Schema to `frontend/src/types/protocol.schema.json`, then runs `json-schema-to-zod` to produce `frontend/src/types/protocol.gen.ts`.
- `tests/test_protocol_contract.py` fails if the generated files are stale.

**Binary frames:**
- byte 0 = tag: `0x01` mic PCM16 16 kHz (client→server), `0x02` TTS PCM16 24 kHz (server→client), `0x03` keyframe JPEG (client→server)
- bytes 1–8 = `uint64` sequence number
- for `0x02`, also bytes 9–12 = `turn_id` hash, so the client can drop stale audio after an interrupt
- AEC (P9) adds a client capture timestamp to `0x01` (bytes 9–16, f64 ms) and a scheduled-play timestamp acknowledgement

**Client → server JSON:** `hello{protocol:4, session_id?, camera, lang_pin}` · `user_text{text}` · `mute{muted}` · `camera{on}` · `percept{…§10.1}` · `set_lang{pin:"auto"|"en"|"ta"}` · `quiet{minutes}` · `playback{turn_id, chunk_seq, started_at, ended_at}` (drives the echo-guard tail and AEC) · `ping{t}`

**Server → client JSON:** `session{session_id, profile_version}` · `state{state}` · `user_transcript{turn_id, text, lang, ratio}` · `assistant_delta{turn_id, text}` · `assistant_done{turn_id, text, route}` · `route{turn_id, mode:"reflex"|"think"|"look"}` · `interrupted{turn_id}` · `request_keyframe{turn_id?, reason}` · `scene{note}` · `perception{present, attention, tired, face_affect}` (≤ 1 Hz) · `memory_event{op, item}` · `initiative{reason}` · `voice_degraded{reason}` · `trace{turn_id, stages}` (dev only) · `error{code, message, retryable}` · `pong{t}`

**Error codes:** `protocol_mismatch` · `session_taken_over` · `llm_unavailable` · `llm_timeout` · `tts_degraded` · `hear_failed` · `camera_unavailable` · `keyframe_timeout` · `memory_unavailable` · `internal`

**Close codes:** 4400 protocol mismatch · 4409 taken over · 1011 internal

---

## 14. REST API v4

All responses are JSON and errors use `{error:{code, message}}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{status, components:{llm, tts, neo4j, vad, turn, ser, embedder, memory_worker}:{status, reason?, latency_ms?}, vram?, profile:"A"\|"B", hear_mode}` |
| GET | `/api/metrics` | Prometheus text: stage histograms, breaker states, queue depths, job counts |
| GET | `/api/sessions` · `/api/sessions/{id}/messages` · `/api/sessions/{id}/events` · DELETE `/api/sessions/{id}` | as in v3 |
| GET | `/api/memory/facts?status=active&q=` | list/search |
| PATCH | `/api/memory/facts/{id}` | edit `object`/`confidence`; records a user-edit event |
| DELETE | `/api/memory/facts/{id}` | delete (with outbox) |
| GET | `/api/memory/episodes?from&to` · `/api/memory/patterns` · `/api/memory/profile` | Notebook views |
| POST | `/api/memory/forget` | `{scope:"last_turn"\|"all", include_conversations?:bool}` |
| GET | `/api/memory/export` | JSON dump of all memory (portability) |
| GET | `/api/benchmarks/latest` | dev: latest gate summaries |

---

## 15. Configuration (new or changed env; `.env.example` updated in each phase PR)
| Var | Default | Meaning |
|---|---|---|
| `PROFILE` | `A` | `A` = E4B native audio, `B` = Qwen3.5 + Whisper/IndicConformer |
| `HEAR_MODE` | `parallel` | `parallel` \| `transcript_first` |
| `LLM_BASE_URL` | `http://llm:8080/v1` | |
| `LLM_SLOT_CONVO` / `LLM_SLOT_UTIL` | `0` / `1` | llama.cpp `id_slot` pinning |
| `LLM_REPLY_MAX_TOKENS` | `160` | reflex |
| `LLM_THINK_BUDGET_TOKENS` | `384` | |
| `TURN_DEADLINE_THINK_S` | `4.5` | |
| `LLM_TTFT_TIMEOUT_S` | `3.0` | → canned line |
| `TTS_BASE_URL` | `http://tts:8081` | |
| `TTS_VOICE` | `medusa` | cloned voice id |
| `TTS_FIRST_CHUNK_TIMEOUT_S` | `1.5` | → fallback |
| `TURN_DETECTOR` | `smart` | `smart` \| `silence` |
| `SMART_TURN_THRESHOLD_EN` / `_TA` | `0.5` / `0.5` | tuned at G5 |
| `UTTERANCE_MAX_S` | `28` | forced end of turn |
| `ALLOW_BARGE_IN` | `false` | true only after G8 |
| `AEC_ENABLED` | `false` | P9 |
| `CAMERA_DEFAULT` | `off` | |
| `GLANCE_MIN_INTERVAL_S` / `GLANCE_IDLE_INTERVAL_S` | `2` / `120` | |
| `INITIATIVE_LEVEL` | `balanced` | `quiet` \| `balanced` \| `chatty` |
| `INITIATIVE_COOLDOWN_MIN` | `15` | D-12 |
| `MEMORY_IDLE_S` | `20` | |
| `MEMORY_DECAY_TAU_DAYS` | `60` | |
| `EMBEDDER` | `google/embeddinggemma-300m` | |
| `NEO4J_ENABLED` | `true` | projection on/off |
| `PREFLIGHT_MAX_FOREIGN_VRAM_MB` | `300` | |

Removed: `STT_*` (Profile A), `EMOTION_FER_*`, `PIPER_TAMIL_ENABLED` (Piper is now always the fallback), `MEMORY_HYBRID_RETRIEVAL`.

---

## 16. Error handling and resilience

### 16.1 Primitives (`backend/core/resilience.py`)
- `Deadline(seconds)`: an async context manager that cancels the inner task and raises `DeadlineExceeded(stage)`.
- `CircuitBreaker(name, failures=3, window_s=60, open_s=30)`: closed → open → half-open (1 probe). The state is exported to health and metrics.
- `retry(fn, attempts, backoff=(0.2, 0.5, 1.0))`: only for idempotent calls (health probes, Neo4j MERGE, embeddings).
- **Bounded queues everywhere:**
  - `SentenceQueue(8)`
  - percept queue (4, drop oldest)
  - `EventWriter` (5000, on overflow drop `assistant_delta` events first; turn and trace events are never dropped)
  - WS send buffer (drop `perception`/`scene`/`trace` first, never `0x02` audio)

### 16.2 Failure matrix
| # | Component / failure | Detection | Response | User sees | Recovery |
|---|---|---|---|---|---|
| E1 | Mic permission denied | `getUserMedia` reject | text mode | "Mic blocked; type instead" | retry button |
| E2 | Camera denied or unavailable | reject or track ended | perception off, `camera{on:false}` | "camera unavailable" chip | toggle retries |
| E3 | WS drop | `onclose` | client backoff 0.5→1→2→4→8 s, resume `session_id`; server cancels the turn, persists partial text, enqueues jobs | "reconnecting…" | automatic |
| E4 | Protocol mismatch | `hello.protocol ≠ 4` | close 4400 | "app updated; reload" | reload |
| E5 | Second tab | new `hello` | old tab gets 4409 | "Medusa moved to another tab" | — |
| E6 | Silero/Smart Turn load fail | exception at startup | `TURN_DETECTOR=silence` (0.9 s) | health degraded | restart |
| E7 | Utterance > 28 s | duration cap | force end of turn, process what was said | — | — |
| E8 | Hear: E4B rejects audio or 5xx | HTTP error | `transcript_first` retry once → else canned "didn't catch that" line | spoken | breaker |
| E9 | Transcript empty or hallucinated | `<none>`, < 2 chars, repetition ratio > 0.5, known silence phrases | drop the turn silently (no reply) | nothing | — |
| E10 | LLM unreachable or TTFT > 3 s | Deadline | cancel; play `lag_{lang}` canned line; breaker++ | "give me a sec, my brain lagged" | breaker half-open probe; compose restart policy |
| E11 | LLM breaker open | breaker | each turn → canned `down_{lang}` line + text-mode hint | spoken + banner | auto when the probe passes |
| E12 | Think deadline 4.5 s | Deadline | cancel and re-issue as a short reflex answer | answer ≤ 5 s | — |
| E13 | Control-tag loop | > 1 re-issue | ignore the tag, answer reflex | — | — |
| E14 | Keyframe timeout 600 ms or camera off | Deadline | re-issue with `camera=off` | "can't see right now" | — |
| E15 | TTS down, OOM, slow or invalid PCM | HTTP error / Deadline / validation | that chunk → CPU fallback; breaker | "backup voice" note | half-open probe |
| E16 | TTS VRAM short at start | `mem_get_info` | int8 → else `mode=unavailable` (CPU fallback for all) | health degraded | `make restart-tts` after freeing VRAM |
| E17 | Glance fail | error / Deadline 2.5 s | keep the last SceneNote (with age) | — | next trigger |
| E18 | SER fail | exception | affect = face-only or none | — | — |
| E19 | Extraction invalid JSON | schema validation | 1 repair retry → dead-letter (`attempts`) | — | next idle, ≤ 3 attempts, then parked and shown in HUD |
| E20 | Embedder fail | exception | lexical + graph retrieval only | — | lazy reload next idle |
| E21 | Neo4j down | breaker / Deadline 80 ms | skip graph retrieval; outbox accumulates | — | outbox replay |
| E22 | SQLite busy or locked | `OperationalError` | WAL; single EventWriter; retry 3× for writes | — | — |
| E23 | Migration failure | exception at boot | abort startup; DB untouched (transaction) + backup exists | backend unhealthy | fix and redeploy |
| E24 | MediaPipe worker crash | worker `onerror` | restart 1/2/4 s ×3 → perception off | "camera paused" | toggle |
| E25 | Slow client / backpressure | send buffer > 1 MB | drop non-audio events | — | — |
| E26 | Echo loop despite the guard | > 2 self-similar transcripts in 30 s (text similarity to the last reply ≥ 0.8) | extend the echo tail ×2; log a warning | — | auto |
| E27 | VRAM creep | `llm` `/metrics` + tts health > 5.9 GB | log critical; refuse glance until it drops | HUD red | restart service |
| E28 | Unhandled exception in a turn | `except Exception` at the turn boundary | `logger.exception`; `error{internal}`; state → listening | "something went wrong, try again" (spoken canned) | — |

### 16.3 Canned lines
Pre-synthesised at boot with the Medusa voice and kept in RAM, so they work even while the LLM is down. Each has EN, TA and mix variants:
- `ack_think` ("hmm, wait, let me think" / "ம்ம், ஒரு நிமிஷம் யோசிக்கிறேன்" / "hmm, oru nimisham, think pannren")
- `lag` (brain lag)
- `down` (brain is down, type to me)
- `didnt_catch`
- `cant_see`

If the TTS is down at boot, they are synthesised with the fallback voice and regenerated when the TTS returns.

### 16.4 Health semantics
- `components.*.status` ∈ `ok | degraded | down`.
- Overall `healthy` requires `llm` ok and (`tts` ok or the fallback ok).
- The `degraded` state is shown in the UI rail. The compose healthcheck uses overall health only for `backend`.

---

## 17. Observability
- **Per-turn trace:** `turn_id` (ULID) with stage timestamps: `speech_start, eot_decided, hear_sent, transcript_done, first_token, route, first_chunk_text, tts_first_byte, first_audio_sent, done`, plus the derived durations. Written as one `turn_trace` event (EventWriter) and streamed as `trace` to the dev HUD.
- **Logs:** `medusa.log` (daily rotation), with structured `key=value` fields including `turn_id`. No transcripts at INFO level. DEBUG may include them, and is off by default.
- **Metrics:** Prometheus histograms per stage, plus breaker states, queue depths and memory job counts.
- **Benchmarks:** `docs/benchmarks/<gate>-<YYYY-MM-DD>.md` + `.json`. Generated report files are restored rather than committed when they are noise (CLAUDE.md rule).

---

## 18. Privacy and safety
- Camera is **off by default** (`CAMERA_DEFAULT=off`). There is an always-visible camera dot and a hard toggle. When off, the browser stops the track: no frames, percepts or keyframes.
- **No pixels or audio persisted.**
  - Audio lives in RAM for the turn only; history keeps the transcript.
  - Keyframes are discarded after the glance.
  - S8 test: scan `clarity-data`, `logs/` and `neo4j-data` for JPEG/RIFF/PCM signatures after a session.
- Memory is local and fully viewable, editable and exportable, with forget and forget-all (§11.7).
- The crisis override in the persona is kept, plus a combined signal (distress words plus a crying face or voice affect) that forces the non-casual, supportive path with a crisis-line mention.
- `reference/` code is never executed. Eval data stays in gitignored `eval/`.

---

## 19. Testing strategy
| Layer | What | Tools |
|---|---|---|
| Unit | turn state machine, echo guard (existing tests kept), control-tag parser, clause segmenter, script ratio and lang, PCM validator, breaker/deadline, PAD, RRF, supersede rules, perception rules | pytest, fakes in `tests/conftest.py` (extended: FakeBrain with slots and tags, FakeTTS streaming, FakePercepts) |
| Contract | protocol Pydantic ↔ generated Zod; TTS service API; llama.cpp request shape (`input_audio`, `id_slot`) | pytest + JSON Schema |
| Integration | backend against a **fake llama.cpp** (FastAPI SSE mock with configurable latency/errors/tags) and a **fake TTS** (streaming PCM, injectable failures); every E-row in §16.2 has a test | pytest-asyncio, httpx |
| Migration | `001→002` on a v3-shaped DB fixture; idempotent re-run; backup created | pytest |
| Frontend | hooks (`usePerception`, `useConversation` v4, playback stamps), Notebook | vitest + testing-library |
| E2E | Chrome with `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<eval wav>`: arrival → talk → reply audio → camera toggle → notebook edit → forget | Playwright |
| Gates | G0–G9 runners (§20) | `scripts/bench/` |
| Soak | 30-min scripted conversation (eval clips looped with pauses), with VRAM/RAM sampling every 5 s | `scripts/bench/soak.py` |

The rule from CLAUDE.md holds: each bug fix gets a failing-first regression test. Full coverage applies on memory mutations (facts, forget, migrations).

---

## 20. Eval kit and gates

### 20.1 Data (Phase 1; all under gitignored `eval/`)
- **Voice (D-22):** copy `~/Projects/voice-auth/data/raw/lebi/lebi/*/audio/*.wav` (41 files, ~56.5 min, 16 kHz mono, laptop mic, room) to `eval/audio/raw/` **read-only from the source**.
  - **Label rule:** for each file, take the `metadata.csv` row with the same filename **and** `|duration_sec − actual| ≤ 0.5 s`. If none matches, the clip is `unknown` and excluded.
  - Write `eval/audio/manifest.csv` (`file, lang, duration, session`).
- **Segmentation:** Silero (our `TurnDetector` settings) into 3–15 s utterances, giving `eval/audio/utts/` + `utts.csv`.
- **Reference transcripts:**
  1. Draft from 3 engines (Whisper large-v3 and IndicConformer-600M in a throwaway bench container; E4B via `llm`).
  2. Stratified 15-min subset (5 EN / 5 TA / 5 mix) → **Lebi corrects** in `scripts/bench/review_ui.py`, a local single-page tool: audio player, editable transcript, ok/skip.
  3. Output: `refs.csv`.
  - **Fallback:** silver references where ≥ 2 engines agree with normalised CER ≤ 5% (flagged lower-confidence in reports).
- **Turn-end set:** from utterances, pauses ≥ 300 ms inside speech = `incomplete`, final 1.5 s = `complete`. Balanced 100 EN+TA, spot-checked in the same review tool. Plus the public Smart Turn data for EN/HI.
- **Vision (open datasets, personal eval only):**
  - COCO val2017: 40 images with person + {cup, cell phone, laptop, book}
  - FER-2013 test: 40 faces across 5 classes
  - HMDB51: 30 frames of eat, drink, laugh, smile, talk

  `eval/vision/labels.csv` holds the expected activity/objects/affect.
- **Dialog set:** 40 multi-turn scripts (≈ 13 EN / 13 TA / 14 Tanglish), written in `eval/dialog/*.yaml`. Each has a rubric for naturalness, language match, brevity, honesty and no fake memory. 10 cross-session recall probes are seeded by scripted sessions. Scored by an LLM judge (E4B is not allowed to judge itself, so the judge is Qwen3.5-4B, run only during gates) plus Lebi spot-checking 10.

### 20.2 Gate definitions (pass → adopt; fail → pre-decided path)
| Gate | Phase | Method | Pass | On fail |
|---|---|---|---|---|
| G0 | P1/P2/P3 | `nvidia-smi` peak + `free` during scripted load, per component and per profile | Profile A ≤ 5.6 GB, RAM headroom ≥ 1 GB | over-budget ladder (§3.1) |
| G1 | P2 | dialog rubric E4B vs Qwen3.5-4B; vision set; glance timing | E4B ≥ Qwen on TA/mix rubric mean; vision ≥ 80%; glance ≤ 1.2 s | Profile B |
| G2 | P2 | refs vs E4B transcript (NFC, ZWJ/ZWNJ/danda strip, jiwer) | EN WER ≤ 10%, TA CER ≤ 15%, code-mix fidelity ≥ 85% (English words kept in Latin, no translation) | Profile B hear stage |
| G3 | P3 | 40 TTS sentences; TTFA/RTF from service trailers; blind A/B sheet vs Piper (TA) and Kokoro (EN) | TTFA ≤ 250 ms, RTF ≤ 0.5, ≥ 80% preferred over Piper, Tanglish with no voice break | Svara Q4 → Indic-Speak → Kokoro + Piper |
| G4 | P6 | 50 cross-lingual probes | recall@5 ≥ 0.85, embed ≤ 30 ms/sentence | Qwen3-Embedding-0.6B |
| G5 | P4 | turn set | premature cut-offs ≤ 5%, median decision ≤ 300 ms | fine-tune Smart Turn on our turn data |
| G6 | P7 | 50 self-labelled clips | e2v+ beats wav2vec2 by ≥ 10 pts | keep wav2vec2 |
| G7 | P9 | traces from the soak + 50 reflex/10 think/10 look turns; both hear modes | S1, S2, S6 | tune (§3.1 ladder, segmentation); hear mode switch |
| G8 | P9 | 10 min of speech over speakers with and without AEC | ≥ 95% echo suppressed, ≤ 1 false barge-in / 10 min | stay half-duplex |
| G9 | P5 | Chrome performance trace | face ≥ 15 fps, main thread < 8 ms/frame | pose off, face 10 fps |

---

## 21. Phases

Each phase is one or more issues → `fix/…`, `feat/…` or `refactor/…` branches → small PRs, each independently green, merged with `gh pr merge --merge`. Docs are kept in sync in every PR.

| Phase | Scope | Exit (DoD) |
|---|---|---|
| **P0 Hygiene fixes** | Unicode tokeniser (retriever/extractor/neo4j_store) + regression test with Tamil memory · remove duplicate summary injection · move emotion and memory after history · EventWriter off the token loop · producer/consumer TTS · TTS routing by reply script · greeting language | all tests green; TTFT before/after recorded |
| **P1 Eval kit + G0 baseline** | import voice (label rule), segment, draft transcripts, review tool, turn set, vision set, dialog set, bench harness, `make preflight` | G0 baseline report for v3 and the candidate components; refs.csv (or the silver fallback) |
| **P2 Brain** | `llm` → E4B + mmproj flags (§5.1); `HearStage` (Native/Whisper-Indic); `BrainClient` with slots, deadlines and the tag parser; `InferenceScheduler`; parallel/transcript-first hear; protocol v4 skeleton (`hello`, tagged binary, error codes, takeover) | G1 and G2 pass, or Profile B adopted; v3 UI still works through a compat shim until P8 |
| **P3 Voice** | `tts_service` (Indic-Mio), voice clone selection (`config/voice/medusa.pt`), mood/emotion mapping, PCM validation, breaker + CPU fallback, canned lines | G3 pass (or a fallback adopted); kill-tts test (S7) passes |
| **P4 Turn-taking** | `turn_detect.py` (Silero + Smart Turn EN/TA, routed by last language), 1.5 s silence cap, 28 s cap | G5 pass |
| **P5 Eyes** | browser perception worker + `percept`; `PerceptState`, events, `perception_minutes`; glance policy + SceneNote; `[look]` route; camera-off-by-default UX | G9 pass; vision part of G1 re-run end-to-end |
| **P6 Memory v4** | migration runner + `001`/`002` (**Lebi approval**); LLM extractor (idle); EmbeddingGemma + sqlite-vec + FTS5 trigram; RRF retrieval; Neo4j outbox projection + `graph-rebuild`; profile job; Notebook REST; forget/export | G4 pass; S4 probes ≥ 8/10; migration tests |
| **P7 Friend** | initiative engine (slots, reviewer, ledger, cooldown, quiet); `[think]` route with ack; PAD mood; emotion2vec+ | G6 pass; initiative never fires during speech (test); ≤ 1 line/15 min (test) |
| **P8 UI v4 "Marginalia"** | voice line canvas, synced phrase, margin notes (see/remember), status rail, Notebook drawer, dev HUD, Tamil fonts, arrival screen, shadcn base, protocol v4 client (Zod generated), playback stamps | Playwright e2e green; reduced-motion OK; mobile layout OK |
| **P9 Polish + release** | AEC (WebRTC APM, browser-stamped clocks) behind `AEC_ENABLED`; latency tuning; soak; docs; `v4.0.0` (backend, frontend, protocol 4) | G7 (S1–S8) pass; G8 pass or documented as half-duplex; VERSIONS/STATUS/HANDOVER updated |

**Order:** P0 → P1 → P2 → P3 → P4 → (P5 ∥ P6) → P7 → P8 → P9. P8's scaffold can start after P2 lands protocol v4.

---

## 22. Risk register
| Risk | L | I | Mitigation / trigger |
|---|---|---|---|
| E4B Tamil ASR or dialog weak | M | H | G1/G2 → Profile B (pre-built `HearStage`) |
| Indic-Mio Tanglish reads English badly | M | M | script-boundary split, same voice (§8); else Svara |
| Profile A exceeds 5.9 GB | M | H | over-budget ladder (§3.1), measured at G0 before building on it |
| llama.cpp Gemma 4 audio regressions across builds | M | M | pin the image build; contract test on the `input_audio` request |
| Parallel hear makes retrieval lag hurt recall | M | M | measure at G4/G7; `transcript_first` switch |
| Smart Turn Tamil fine-tune poor | M | M | fine-tune on our turn data (open training script) |
| RAM pressure with Neo4j | L | M | heap 1G; `NEO4J_ENABLED=false` keeps everything working (SQLite source of truth) |
| Perception feels creepy | M | H | camera off by default, never narrated, notes with "why" plus dismiss, no storage of pixels |
| Licence surprises (Indic-Mio, smart-turn-tamil, e2v+) | L | M | read the cards at the start of each phase; personal use (D-15); fallbacks listed |
| Scope creep (tools, screen) | M | M | D-16/D-13/D-40: v4.1 backlog only |

---

## 23. v4.1 backlog (explicitly deferred)
- Screen awareness via browser screen-share
- Light tools (reminders, timers) → MCP
- Speaker verification with the `voice-auth` ECAPA reference (`lebi_reference.npy`) to ignore TV and other voices
- Wake word and a desktop wrapper (Tauri), always-on mode
- Avatar option
- LoRA fine-tune of the hear path on Lebi's Tanglish
