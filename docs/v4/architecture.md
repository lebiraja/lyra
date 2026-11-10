# Medusa v4: Perceptive Companion Architecture (proposal)

> **Superseded for decisions by [plan.md](plan.md) (2026-11-11).** Kept as design rationale. Where they differ, plan.md wins (e.g. the brain is Gemma 4 E4B with native audio, the voice is Indic-Mio, and Neo4j is on by default as a projection).

**Status:** PROPOSAL, nothing implemented · **Date:** 2026-11-10 · **Supersedes nothing yet:** `docs/architecture.md` still describes the running v3
**Inputs:** [current-state audit](../research/2026-11-current-state-audit.md) · [model landscape](../research/2026-11-model-landscape.md) · [similar projects](../research/2026-11-similar-projects.md) · **Phasing:** [roadmap](roadmap.md) · **UI:** [ui-redesign](ui-redesign.md)

## 1. Goal

A friend that lives on the laptop. It **hears** you (words, tone), **sees** you (face, posture, what you're doing), **remembers** you (facts, events, routines, how you've been), and **talks back fast** in English, Tamil or Tanglish, whichever you're using. It runs entirely on the edge: one RTX 4050 6 GB, no cloud calls at runtime.

### Design principles
1. **Fast by default, deep on demand.** The reflex path answers in under a second. Thinking, vision analysis and memory work happen only when they're worth the time, and never block the reflex path unless the question needs them.
2. **Cheap perception runs continuously, expensive perception runs on events.** Landmarks run every frame in the browser. The VLM looks only when something changed or was asked about.
3. **One brain, one voice.** One multimodal LLM resident on the GPU (no separate VLM), and ideally one TTS voice for both languages.
4. **The GPU is the budget.** Every component has a VRAM line item (§4). CPU-capable models go on the CPU.
5. **Memory belongs to the user.** Everything it knows is inspectable, editable and deletable from the UI.
6. **Benchmarks decide models.** Every model choice is a hypothesis until it passes a gate in the [roadmap](roadmap.md), measured on Lebi's voice, face and room.

### Non-goals (v4)
- End-to-end speech-to-speech models (Qwen-Omni/Moshi class). They don't fit, the licences are wrong, and there's no Tamil support (see the landscape doc §1).
- Multi-user households, phone apps, cloud sync.
- Continuous video recording. Frames are processed and dropped, and only derived text and features persist.

## 2. System overview

```
 BROWSER (client = sensors + face)                         BACKEND (FastAPI, per-connection Session)
 ┌──────────────────────────────────┐                      ┌───────────────────────────────────────────────────┐
 │ mic 16k PCM ─────────────────────┼── binary: AUDIO ────▶│ AUDIO LANE                                        │
 │                                  │                      │  Silero VAD ─▶ Smart Turn v3 ─▶ utterance          │
 │ camera ─▶ MediaPipe (WebGL)      │                      │                 │                                 │
 │   Face Landmarker: blendshapes,  │                      │                 ├─▶ STT (Indic-Transcribe/Whisper)│
 │     head pose, presence          │── json: PERCEPT ────▶│                 └─▶ SER emotion2vec+ (CPU, ‖)     │
 │   Pose Landmarker: posture       │   (~4 Hz, ~300 B)    │                                                   │
 │   derived: attention, blink,     │                      │ PERCEPTION LANE                                   │
 │     yawn, smile, away/at desk    │                      │  PerceptState (rolling): face affect, posture,    │
 │   change detector ───────────────┼── binary: KEYFRAME ─▶│   presence, attention ─ events ─▶ Initiative       │
 │     (only on request/change)     │   (JPEG, rare)       │  Glance: keyframe ─▶ BRAIN(vision) ─▶ SceneNote     │
 │                                  │                      │                                                   │
 │ playback 24k PCM ◀───────────────┼── binary: AUDIO ─────│ SITUATION MODEL (working memory, one object)       │
 │ UI: presence orb, transcript,    │◀── json: events ─────│  {transcript, affect, scene, activity, time,      │
 │   "what I see", memory drawer    │                      │   language mix, recent memories}                  │
 └──────────────────────────────────┘                      │            │                                      │
                                                           │            ▼                                      │
                                                           │ BRAIN (llama.cpp, multimodal 4B, GPU)             │
                                                           │  Router: reflex │ think │ look                    │
                                                           │  cache-friendly prompt (§5.1) ─▶ token stream     │
                                                           │            │                                      │
                                                           │ VOICE LANE  ▼                                     │
                                                           │  clause segmenter ─▶ script/lang tagger ─▶ TTS    │
                                                           │  (Indic-Speak/Svara GPU │ Kokoro CPU fallback)    │
                                                           │                                                   │
                                                           │ MEMORY (async, idle-time)                         │
                                                           │  event log ─▶ LLM extractor ─▶ facts/episodes/    │
                                                           │  routines ─▶ SQLite + sqlite-vec (+ Neo4j opt.)   │
                                                           └───────────────────────────────────────────────────┘
```

**Lanes are independent asyncio tasks** that talk through queues and the shared `SituationModel`. A slow lane (a glance, memory consolidation) can never stall the audio→voice path.

## 3. The lanes in detail

### 3.1 Audio lane (ears)
1. **Silero VAD v5** (CPU) gates frames, unchanged from v3.
2. **Smart Turn v3.2** (8 MB int8 ONNX, CPU) is evaluated at every short pause of ≥200 ms. If P(turn complete) ≥ θ, the turn ends. Otherwise listening continues, with a hard cap at ~1.5 s of silence. This replaces the fixed 900 ms timeout (audit §3.7). Start from the Tamil community fine-tune if the base model under-performs on Tamil prosody.
3. **STT** on the utterance. The engine is chosen at gate G2 (landscape §2). Expected shape: **Indic-Transcribe** for TA/Tanglish and **Whisper turbo** for EN, *or* a single engine if one wins on all three. The output keeps English words in Latin script inside Tamil text, which matters for TTS and memory.
4. **SER** (emotion2vec+, CPU) runs in parallel on the same audio, as v3 already does for wav2vec2.
5. **Early start (stretch):** when Smart Turn is confident but not yet past θ, run STT speculatively and pre-warm the LLM prefix. Discard the work if the user keeps talking. This is the RealtimeVoiceChat trick.

### 3.2 Perception lane (eyes)

**Fast lane, in the browser, every frame (~15–30 fps compute, ~4 Hz upload):**
- MediaPipe **Face Landmarker** gives 52 blendshapes, a head-pose matrix and face presence.
- MediaPipe **Pose Landmarker (lite)** gives shoulder and torso angles, standing or sitting, and leaning in or away.
- Client-side feature extraction:
  - `smile`, `frown`, `brow_raise`, `eye_closure`, `yawn`
  - `gaze_on_screen` (approx. from head yaw/pitch plus eye blendshapes)
  - `slouch`, `present`, `motion_energy`
  - a scene-change score (downscaled frame difference)
- Upload is a **compact JSON percept**, about 300 bytes at 4 Hz, instead of 5 JPEGs/s (audit §3.8). No pixels leave the browser by default.

**Server `PerceptState`:** rolling windows (5 s / 60 s / session) over the percepts, with debounced **events**:
- `user_arrived`, `user_left`
- `looks_tired` (yawn and blink rate up)
- `smiling_while_talking`
- `long_focus` (on screen and still for >45 min)
- `stood_up`, `scene_changed`

The SER and face affect fusion moves here, keeping today's `EmotionFusion` weights as a starting point.

**Slow lane, the "glance":** the brain VLM looks at one keyframe and writes a short **SceneNote** ("at desk, dim room, laptop open with code, holding a mug, wearing headphones"). Triggers:
- The user refers to something visual ("what do you think of this?", "can you see this?"). The router detects this (§5.3), the client is asked for a keyframe, and it arrives as the binary `KEYFRAME`.
- A `scene_changed` or `user_arrived` event fires (rate-limited to at most 1 per 30 s).
- An idle refresh every ~2–5 min while the camera is on and nobody is speaking.

A glance runs on the **same llama.cpp brain**, at idle priority. If a user turn arrives mid-glance, the glance is cancelled, because the voice path always wins.

### 3.3 Voice lane (mouth)
1. A **producer/consumer** split (fixes audit §3.5): the token reader pushes into a segmenter, and a TTS worker drains a sentence queue. LLM and TTS overlap.
2. **First-chunk-early segmentation:** the first chunk is cut at the first clause boundary (`,` `;` `—` or ~8 words), and later chunks at sentence boundaries. This trades a little prosody on the first phrase for ~200–400 ms less latency.
3. **Script/language tagger per chunk:** the voice is chosen from the *reply text* (Tamil-script ratio, Latin ratio), not from the user's STT language (fixes audit §3.6).
4. **TTS engine** chosen at gate G3:
   - Preferred: a **single Indic-Speak (or Svara) voice** for TA, Tanglish *and* EN, so the friend has one voice.
   - Fallback: Kokoro for pure-EN chunks and Indic-Speak for anything with Tamil.
5. **Prosody hints (stretch):** the emotion and situation (`user sad`, `excited`) map to TTS speed/style or voice choice, where the engine supports it.

### 3.4 Echo and barge-in
- v3's half-duplex guard stays as the **default**. It is proven.
- **Reference implementation:** `reference/huggingface_speech-to-speech/.../echo_canceller.py` uses WebRTC APM (`pywebrtc_audio`), 10 ms frames, and speaker chunks queued by playback time and matched to mic capture time on one clock. We need the browser to timestamp both streams on the same clock.
- **v4 upgrade path, server-side AEC with a known reference:** the backend knows exactly which PCM it sent and roughly when it plays, because the guard already tracks `_plays_until`. A WebRTC-APM/speex AEC fed with that reference can cancel the echo, which **enables barge-in on laptop speakers**.
- **Alternative:** move the transport to WebRTC (Pipecat's SmallWebRTC or aiortc). TTS then plays through a WebRTC track the browser's AEC *does* reference, and Opus cuts bandwidth. Recorded as open decision D-4 in `DECISIONS.md`.

## 4. VRAM and RAM budget profiles

All figures are **estimates** to be replaced by measurements at gate G0. CUDA context overhead is ~250–350 MB per GPU process.

| Component | P0 v3 today | **P1 "See"** | **P2 "Native voice"** | P2-alt "Small brain" |
|---|---|---|---|---|
| Brain | Qwen3-4B Q4_K_M ~2.5 GB + KV 8k ~1 GB | Qwen3.5-4B / Gemma 4 E4B Q4 ~2.7 GB + mmproj ~0.5 GB + KV 6k (q8_0) ~0.5 GB | same as P1 ≈ 3.7 GB | Gemma 4 E2B / Qwen3.5-2B Q4 ~1.4 GB + mmproj ~0.4 + KV ~0.3 ≈ 2.1 GB |
| STT | Whisper turbo int8 GPU ~1.3 GB | Whisper turbo GPU ~1.3 GB | **CPU** (IndicConformer int8 or Indic-Transcribe on CPU, *if fast enough*) 0 GB | Indic-Transcribe / Whisper GPU ~1.3–1.5 GB |
| TTS | Kokoro + Piper CPU 0 | Kokoro + Piper CPU 0 | Indic-Speak/Svara Q4 ~2.2 GB + SNAC/Vocos ~0.1 | Indic-Speak/Svara Q4 ~2.3 GB |
| CUDA ctx ×N | ~0.6 | ~0.6 | ~0.9 (3 procs) | ~0.9 |
| **Total GPU** | **~4.8 GB** | **~5.6 GB** ⚠ tight | **~6.4 GB ✗ over** unless the brain KV shrinks to ~4k or the TTS is IQ4_XS | **~5.9 GB** ⚠ tight |
| CPU RAM | ~3 GB | ~3.5 GB | ~5–6 GB (CPU STT) | ~4 GB |

**What the table says:**
- **P1 is the safe first step.** It adds vision by swapping the brain for a multimodal one with the same footprint class. Voice stays on the CPU.
- **A 4B multimodal brain, a 3B LLM-TTS and GPU STT do not all fit in 6 GB.** Native Tamil voice (P2) forces one of:
  1. STT moves to the CPU (P2, needs a fast CPU ASR; the 14-core i7 makes this plausible for IndicConformer CTC).
  2. The brain shrinks to ~2B (P2-alt, costs "friend quality").
  3. Aggressive quantisation (KV q4, IQ4_XS TTS, 4k context), which costs quality and needs measuring.
- This is **decision D-1** (in `BLOCKERS.md`), Lebi's call after the G0–G3 numbers are in.
- **Update (2026-11-10, from reading `reference/`):** two options may make native Tamil voice fit without shrinking the brain (see [reference-repos](../research/2026-11-reference-repos.md) §8):
  - **P3 "one model hears and sees":** Gemma 4 E4B takes audio directly and also transcribes (GLaDOS measured ~4.1 GB with vision on a 3080), so Whisper leaves the GPU.
  - **Indic-Mio 0.6B** as the TTS (~0.5 GB [est]) instead of a 3B LLM-TTS.
  - Estimated P3 total: ~4.1 + 0.5 + ctx ~0.6 ≈ **5.2 GB**. This depends on E4B's Tamil ASR (G2) and Indic-Mio's quality (G3).
- **Neo4j** costs 1–2 GB of RAM. On 15 GB with the desktop, the browser (MediaPipe) and CPU models, keep it **off by default** and use SQLite + sqlite-vec (§7).

## 5. Brain

### 5.1 Cache-friendly prompt layout (fixes audit §3.2)
```
[1] persona system prompt                         ← static  (cached across all sessions)
[2] "Who they are": stable person profile         ← changes only after consolidation (cached per session)
[3] conversation history (windowed)               ← append-only within a session (cached incrementally)
[4] <now> block: perception + affect + retrieved   ← volatile, rebuilt every turn, small (~200–400 tokens)
     memories + time of day + language hint
[5] user turn
```
- With llama.cpp `cache_prompt`, only [4] and [5] are re-processed each turn. TTFT stays flat as the conversation grows.
- [4] goes in as part of the final user message (or a final system message) so the prefix [1–3] stays byte-identical.
- The `{memory}` slot in the persona YAML becomes the **person profile** [2], so summaries are no longer injected twice (audit §3.3).

### 5.2 The `<now>` block (what the brain "senses")
```
<now time="Tue 23:40" lang="tanglish" camera="on">
  you see: at desk, dim room, code on screen, mug in hand (glance 40s ago)
  face: tired (yawning, slow blinks) · voice: flat, low energy (emotion2vec: sad 0.41)
  body: slouched for ~70 min, hasn't stood up since 22:30
  relevant memory: exam on Friday (stated Sun) · usually sleeps ~01:00 · likes filter coffee
</now>
```
The prompt rule: use perception **only when it helps the moment**, never narrate it robotically ("I can see you are yawning"), and never claim to see something absent from `<now>`.

### 5.3 Router: reflex / think / look
A cheap classifier decides per turn. It starts as rules plus keywords, can later become a logit probe or a tiny classifier.

| Route | When | Behaviour | Latency target |
|---|---|---|---|
| **reflex** (default) | chit-chat, reactions, short replies | thinking off, `max_tokens≈120`, stream immediately | first audio ≤ 0.8 s |
| **think** | "should I…", planning, multi-step, explicit "think about it" | speak a short **acknowledgement** first ("hmm, wait, let me think" in the user's language), then run with thinking on and a budget (~256–512 thinking tokens), then speak the answer | ack ≤ 0.8 s, answer ≤ 4 s |
| **look** | deictic or visual references ("see this", "what am I holding", "how do I look") | request a keyframe, run the brain with the image, answer | first audio ≤ 1.5 s |

### 5.4 Initiative engine (being a friend, not a chatbot)
Modelled on GLaDOS's Autonomy Core (`reference/dnhkng_GLaDOS/docs/autonomy.md`): minds publish to slots (`importance`, `confidence`, `revision`, `attention_key`). A reviewer returns uniform JSON `{"action":"null"}` / `{"action":"prompt",…}`. Review is deferred during any user activity plus 2 s, with a cooldown, silent back-off (40→80→120 s) and a delivered-event ledger, so each condition is spoken once.

Perception and memory events can trigger **proactive** lines, within strict limits:
- **Triggers:** `user_arrived` (greeting using memory), `long_focus` + `looks_tired` ("dei, it's been an hour and a half, take a break?"), a remembered follow-up ("how did the exam go?"), and silence after a sad turn.
- **Rate limits:** at most 1 unprompted line per ~15 min. Never while the user is talking or on a call (detect headphones plus speech to someone else). The user can say "be quiet for a while", which mutes initiative for N hours.
- Every initiative line is logged with its trigger, so the user can see why Medusa spoke up.

## 6. Latency budget (end of speech → first audio)

| Stage | v3 today | v4 target | Lever |
|---|---|---|---|
| End-of-turn decision | 900 ms | **150–300 ms** | Smart Turn on short pauses (§3.1) |
| STT | 250–300 ms | 150–250 ms | shorter utterances after Smart Turn, int8, beam 1; speculative STT (stretch) |
| Prompt prefill | grows with history | **~50–100 ms** | prefix cache (§5.1), small `<now>` block |
| LLM to first clause | 200–600 ms | **100–200 ms** | first-chunk-early segmentation (§3.3), reflex `max_tokens` |
| TTS first chunk | 100–300 ms | **80–200 ms** | LLM-TTS streaming SNAC frames / Kokoro CPU; producer/consumer |
| Transport + playback start | ~30 ms | ~30 ms | — |
| **Total** | **~1.5–3 s** | **≈ 0.6–1.0 s** | |

Every stage is instrumented. `LatencyStats` becomes a per-turn trace (`turn_id`, stage timestamps) written to the event log and shown in the UI dev HUD.

## 7. Memory v4: "knows me"

It builds on the existing interfaces (`backend/memory/interfaces.py`) and the plan in `docs/archive/human-like-memory-architecture-plan.md`, with three changes: **language-agnostic**, **perception-aware** and **idle-time**.

| Layer | What | Store | Written by |
|---|---|---|---|
| Working | the `SituationModel`: current turn, `<now>`, last N turns | RAM | the lanes |
| Episodic | "Sun 10 Nov, 23:40: stressed about the exam, tired, coding late" (who/what/when/feeling/scene) | `episodes` table + embedding | consolidation after a session or idle |
| Semantic | facts and preferences with **validity time** ("exam on 15 Nov", "likes filter coffee", "sister = Priya") | `facts` (bi-temporal: `valid_from/valid_to/recorded_at`) + `entities`/`edges` + embeddings | LLM extractor (JSON schema) |
| Routines / procedural | "usually sleeps ~01:00", "codes late on weekdays", "gets quiet when stressed" | `patterns` table derived from episodes + perception stats | nightly or idle job |
| Person profile | compact 150–300-token summary of who they are | regenerated from facts and patterns | consolidation; goes in prompt slot [2] |

**Key changes from v3:**
- **Extraction:** the brain LLM with a strict JSON schema, run **asynchronously when the user is idle** (no speech for ≥20 s, or after the session ends). It handles Tamil and Tanglish natively and replaces the English regexes (audit §3.1).
- **Retrieval:** multilingual embeddings (EmbeddingGemma-300M or Qwen3-Embedding-0.6B, chosen at gate G4) in **sqlite-vec**, plus an entity/keyword match. **Unicode-aware tokenisation** for the lexical part (no `[a-z0-9]`).
- **Perception becomes memory only as derived text** ("looked tired", "was at desk until 2am"). Images are never stored.
- **Contradiction and decay:** a new fact supersedes an old one by closing `valid_to`, never by deleting it. Low-confidence facts that are never re-confirmed fade out of retrieval.
- **User control:** every fact and episode can be listed, edited, deleted and traced to its source event in the UI. Saying "forget that" deletes the last extracted facts.
- **Neo4j stays optional** behind `SemanticGraphStore`. Edges in SQLite are enough at single-user scale. Graphiti's bi-temporal model is the reference schema.

## 8. Language strategy (EN / TA / Tanglish, natively)

| Concern | Approach |
|---|---|
| Detection | Per-utterance mix ratio from STT output: Tamil-script share, Latin share, and Tamil words romanised in Latin (a small lexicon). Gives `en` / `ta` / `mix`. Replaces the `prob<0.7→en` rule. |
| Reply language | **Mirror the user** by default: the prompt gets `lang="tanglish"` etc. in `<now>`. A UI toggle can pin EN or TA. |
| Script of the reply | Tamil words in **Tamil script**, English words in **Latin**, which is the natural Tanglish written form and what Indic-Speak/Svara read best. Romanised Tamil from the LLM is normalised to Tamil script (Aksharamukha-class transliteration) before TTS. |
| Voice | One voice for all (gate G3). Fallback is per-chunk engine routing by script. |
| Memory | Stored in the language spoken. Embeddings are multilingual, so an EN query finds a TA memory. |
| Eval | All gates use Lebi's real EN, TA and Tanglish recordings, not FLEURS. |

## 9. Protocol v4 (WS, versioned)

Changes to `docs/API.md` and `frontend/src/types/protocol.ts` together:
- **Binary frames get a 1-byte type tag:** `0x01` mic audio, `0x02` TTS audio, `0x03` keyframe JPEG. This removes base64 JPEG in JSON.
- New client→server messages:
  - `{"type":"percept", ...features}` at ~4 Hz
  - `{"type":"camera","on":bool}`
  - `{"type":"set_lang","pin":"auto"|"en"|"ta"}`
  - `{"type":"quiet","minutes":n}`
- New server→client messages:
  - `{"type":"request_keyframe","reason"}`
  - `{"type":"scene","note"}`
  - `{"type":"perception","state":{...}}` (what Medusa currently believes)
  - `{"type":"memory_event","op":"added|updated|forgotten","item"}`
  - `{"type":"route","mode":"reflex|think|look"}`
  - `{"type":"trace","turn_id","stages":{...}}`
- The protocol is versioned (`"protocol":4` in `set_session`), so a v3 client fails loudly instead of misbehaving.

## 10. Privacy and safety
- Camera is **off until the user turns it on**, with a visible always-on indicator and a hard off switch. When it's off, no frames or percepts are sent.
- Pixels stay in the browser except keyframes for a glance. Keyframes are processed in memory and never written to disk or the DB.
- All memory is local SQLite under the `clarity-data` volume. "Forget everything" wipes facts, episodes and embeddings.
- The crisis rule in the persona prompt stays and is extended: perception cues (crying, distress) combined with language cues trigger the "drop the casual act" path.
- Identity recognition (face or speaker embedding) is **optional and off**. Revisit only if multiple people use the device.

## 11. Service topology (docker compose, proposed)

| Service | Change from v3 |
|---|---|
| `llm` (brain) | Model swaps to a multimodal 4B GGUF plus `--mmproj`, KV cache quantisation and `cache_prompt`. Still llama.cpp server CUDA. |
| `tts-llm` (new, P2) | A second llama.cpp CUDA instance serving Indic-Speak/Svara GGUF (SNAC tokens), plus a SNAC/Vocos decoder inside the backend or as a sidecar. |
| `backend` | New lanes, router, initiative engine, memory jobs. `torch` is dropped if SER moves to ONNX. |
| `frontend` | Redesigned UI plus MediaPipe tasks-vision (WASM/WebGL assets served locally, no CDN at runtime). |
| `neo4j` | Stays behind `--profile memory`, off by default. |

## 12. Open questions (also tracked in `BLOCKERS.md` / `DECISIONS.md`)
1. **D-1 VRAM profile:** P2 (CPU STT) vs P2-alt (2B brain) vs aggressive quantisation, decided after gates G0–G3.
2. **D-2 Single voice:** is Indic-Speak's Indian-accented English acceptable, or does English stay on Kokoro?
3. **D-3 Licences:** Indic-Transcribe and Indic-Speak use the Indic Open Model License (fine for personal use). Revisit before any public distribution of images that bundle the weights.
4. **D-4 Transport:** stay on WS with server-side AEC, or move to WebRTC (Pipecat transport)?
5. **D-5 Framework:** keep our pipeline and borrow components, or port to Pipecat? Recommendation: keep ours (tested, small) and borrow Smart Turn and the transport.
