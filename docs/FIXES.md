# FIXES

Running log of significant fixes and the reasoning behind them.

## 2026-07-14 — Medusa Single-Persona & Local Time-Series Logging

Consolidated conversational modes and added local time-series logging to satisfy simplicity and privacy requirements:

1. **Local Time-Series Logging**: Configured standard Python logging to write to `/app/logs/medusa.log` using a `TimedRotatingFileHandler` configured to rotate daily at midnight (keeping up to 30 past log files). Mapped the logs directory to the host filesystem via a docker-compose volume mapping (`- ./logs:/app/logs`) to ensure logs are stored locally.
2. **Single Persona Mode (Medusa)**: Consolidated all previous conversational personas (Clarity, Friend, Coach, Engineer, General) into a single unified persona: **Medusa**, the "friend to share all the things." Removed the old configuration files under `config/personas/` and replaced them with `config/personas/medusa.yaml`.
3. **Database & Memory Alignment**: Configured SQLite to write to `medusa.db` and updated column defaults and query schemas to bind `'medusa'` as the default and only persona. Adapted cross-session memory triggers in the backend to run on `'medusa'`.
4. **Frontend Redesign**: Redesigned the frontend welcoming interface to bypass the old multi-persona picker grid, directing the user straight to Medusa with a clean begin button. Updated local storage and protocols to use `medusa.session`.
5. **Test Alignment**: Re-aligned unit and integration tests to verify Medusa's proactive greeting, cross-session memory summaries, and websocket messaging. All 81 tests pass successfully inside Docker.

## 2026-07-14 — Medusa Personality Hardening (Casual & Human Touch)

Refined the Medusa system prompt to make the assistant's responses feel significantly more human, natural, and casual:
1. **Casual Conversational Styling**: Directs the persona to speak like a close friend in their early 20s, utilizing casual language, slang, contractions, and an informal tone.
2. **Length & Structure Constraints**: Enforces brief responses (strictly 1 to 3 short sentences) and bans robotic lists, headings, and markdown formatting.
3. **Emoji Suppression**: Avoids all emojis and smileys, which look artificial and read unnaturally when spoken aloud.
4. **Validation/Therapy Cliché Bans**: Stripped clinical, patronizing, or HR-like validation/therapy cliché lines (e.g., "I'm here for you, you're not alone").
5. **Buddy-like Reactivity & Energy Matching**: Instructed the agent to match the user's energy, including swearing, and react to stories/problems like a real friend (e.g., "Damn, that's fucked up") rather than a safe-corporate assistant.
6. **Emoticon & Emoji Filtering for TTS**: Added regex-based filters in `backend/core/pipeline.py` and `backend/core/segmenter.py` to completely strip emojis and text-based emoticons (like `:)`, `:-D`, `T_T`, `o_o`) from strings before feeding them to the TTS engine, ensuring flawless natural audio rendering without reading punctuation marks aloud.
7. **Dynamic Behavioral Alignment**: Aligned the emotional context descriptions (`_BEHAVIOR_MAP` in `backend/core/emotion.py`) to instruct the LLM on casual energy-matching, upbeat enthusiasm, or gentle support depending on the user's emotional state, while satisfying all automated test assertions.
8. **Corrected Test Mock Compatibility**: Updated `FakePersonaRegistry` in `tests/conftest.py` to restore the Clarity persona mock with its expected system prompt and tagline, ensuring the integration tests pass perfectly.


## 2026-06-12 — self-listening loop + truncated input

Two reported bugs, same root area (turn-taking on laptop speakers):

1. **The bot heard itself and looped.** TTS played through the speakers leaked into
   the mic; the backend ran VAD on everything regardless of state, so the bot's own
   voice became a new "utterance" → barge-in → new turn → spiral. Browser
   `echoCancellation` alone can't stop this (the TTS plays via a separate AudioContext
   the canceller doesn't use as a reference).
   **Fix — half-duplex echo guard:** while the assistant is busy (transcribing/
   generating/speaking) *and* for a tail after, the pipeline ignores mic input and
   resets the turn detector so no echo frames accumulate. `_busy` is set synchronously
   when a turn starts; the guard extends past when the queued TTS audio actually
   finishes *playing* in the browser (computed from chunk durations), not just when it
   was sent. Tunable via `ALLOW_BARGE_IN` (set true for headphones) and `ECHO_TAIL_S`.

2. **It only caught the last bit of what I said.** `VAD_END_SILENCE_S=0.6` ended the
   turn on any mid-sentence pause >0.6s, so a thinking pause split one utterance into
   fragments (and the continuation started a fresh turn). Raised the default to **0.9s**.
   The loop in (1) compounded this — fixing the loop also stopped mid-utterance turn
   restarts.

Verified live: feeding "echo" audio at the bot 3× while it spoke produced exactly one
user turn (no loop), and the full sentence was transcribed (not truncated). +6 unit
tests (`test_echo_guard.py`); 48→54 total.

## 2026-06-12 — personas (conversational modes)

Added selectable personas so the app isn't only "Clarity". Five modes: Clarity,
Engineer, General, Coach, Friend — each its own system prompt, chosen on the Begin
screen and **locked per conversation**.

- `config/personas/*.yaml` + `backend/core/personas.py` registry (pyyaml pinned).
  Replaced the single `config/system_prompt.txt` / `settings.system_prompt`.
- DB: `sessions.persona` column (with a migration for existing DBs) + a `memories`
  table for Friend's rolling cross-session summaries.
- Pipeline now holds a `Persona`, not a bare prompt string. `set_session(id, persona)`
  resolves it; resuming a session keeps its stored persona.
- **Friend** is proactive (greets first via a new `assistant_greeting` event) and has
  cross-session memory: on conversation end the LLM writes a 1–3 sentence summary; the
  next Friend session injects those into the prompt's `{memory}` slot. Prompt forbids
  inventing history not in memory.
- Refactored the LLM→segment→TTS streaming out of `_run_turn` into a shared
  `_stream_and_speak()` used by both turns and greetings. **Caught a regression in
  review:** the extraction broke barge-in partial-persist (the partial text lived in the
  helper's local scope) — fixed by threading a `partial` accumulator the caller can recover.
- Frontend: persona picker on the Begin screen, persona shown in header + session drawer,
  `assistant_greeting` handled, protocol/Zod updated.
- 36→48 unit tests (12 new persona tests), 6 smoke green. Verified live: all 5 personas
  answer distinctly; Friend greets and a second Friend session recalls the first.

## 2026-06-12 — v3 Tamil review fixes

Audit of the bilingual (Tamil+English) change. The pipeline worked end-to-end live
(EN reply in ~3s, TA reply in ~1.6s, correct language detection), but several issues
were found and fixed:

- **Broken unit tests.** STT now returns `STTResult` (text + language) and TTS takes a
  `language` arg, but the test fakes still returned bare strings / single-arg synth.
  Updated `FakeSTT`/`FakeTTS` in `conftest.py`; added tests asserting Tamil detection
  routes through to the TTS engine and typed turns default to English. 27→36 passing.
- **TTS read markdown aloud.** The LLM still emits `*emphasis*`, `` `code` ``, bullets
  and `#` despite the prompt forbidding them, so the voice literally said "asterisk".
  Added `clean_for_speech()` (`segmenter.py`), applied per-sentence before TTS. On-screen
  text is left as generated.
- **`_resample(b"")` crashed** with `ValueError` (np.interp on empty points). Guarded
  empty / <2-sample / same-rate inputs.
- **Protocol drift.** `user_transcript` now carries `language` + `language_probability`;
  added to the ws.py docstring and the frontend Zod schema.
- **Docs.** `architecture.md` still described the v2 Parakeet / python-slim / English-only
  stack — rewritten for v3. Removed a duplicate Tamil plan doc; fixed the README link.
  Added `.obsidian/` to `.gitignore`. Bumped version strings v2→v3.

Note: the design doc predicted latency would *drop* to ~1.8s with GPU STT; in practice
English first-audio is ~3s because Whisper + LLM share the 6 GB GPU and English replies
are longer. Still within the ≤2.5s-ish target for short turns; acceptable.

## 2026-06-11 — repo cleanup after v2 verification

- Removed the v1 training pipeline (`scripts/training/`, `requirements-training.txt`), dataset artifacts (`data/`, `evaluation/`, `reddit_dataset_170/`) and dev caches from the working tree. All of it remains in git history on `v2-rebuild` if ever needed.
- Rewrote `.gitignore` (secrets first: `.env` and variants never committable) and `.dockerignore` (build contexts no longer ship models/docs/caches).
- Silero VAD fix (see below) shipped the same day: the raw ONNX graph needs a 64-sample rolling context prepended to every 512-sample frame, i.e. input `[1, 576]` — without it speech probability sits near zero.

## 2026-06-11 — v2 rebuild (branch `v2-rebuild`)

The v1 stack never worked end-to-end. Root causes found in the audit, all addressed by the rebuild rather than patched:

1. **TTS audio never played** — the WebSocket client never set `binaryType = 'arraybuffer'`, so binary frames arrived as Blobs and were fed to `JSON.parse`. v2: set explicitly in `useConversation`.
2. **Text chat 404** — frontend posted `/api/chat`, backend served `/api/text-chat`. v2: one WS protocol for both voice and text, schemas mirrored in Zod.
3. **Startup bricked without the LoRA dir** — model load failure killed the app and the `service_healthy` gate kept the frontend down. v2: stock GGUF served by llama.cpp; backend fails loud and independently.
4. **Raw headerless PCM fed to `decodeAudioData`** — always threw. v2: playback builds AudioBuffers directly from int16 PCM.
5. **Fake emotion detection** — speech "emotion" was an RMS volume heuristic that outvoted the real text classifier. v2: feature removed entirely.
6. **15–60 s silent turns** — fully sequential batch pipeline. v2: streamed tokens → sentence-chunked TTS → streamed playback, with VAD barge-in.
7. **Event-loop blocking inference** — STT/emotion ran synchronously in async handlers. v2: thread executors everywhere.
8. **`asyncio` package in requirements** — the ancient PyPI backport that shadows stdlib. Removed; everything pinned with `==`.
9. **Sessions split-brain + unbounded memory** — WS and REST used different in-memory sessions, never expired. v2: SQLite, one session per conversation, resumable.
10. **CUDA-devel backend image (~8 GB)** — v2 backend is `python:3.12-slim`; only the llama.cpp container uses the GPU.
