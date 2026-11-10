# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Fully local bilingual (English + Tamil) voice companion. The product name is inconsistent: the repo dir is `lyra`, the code/docker names say `clarity-*` / "ClarityMentor", and the single live persona is **Medusa**. Treat them as the same project. Nothing leaves the machine after the one-time model download.

## Commands

Everything runs in Docker (needs NVIDIA GPU + `nvidia-container-toolkit`); see `Makefile`.

```bash
cp .env.example .env && make models   # one-time, ~4 GB into ./models/ (gitignored)
make up / down / logs                 # build + run llm, backend, frontend
make test                             # docker compose run --rm --no-deps backend pytest -q
make test-smoke                       # real ONNX models, needs `make models`
make dev                              # vite dev server (:5173) against a running backend
```

Single test: `docker compose run --rm --no-deps backend pytest -q tests/test_pipeline.py::test_name`

Default pytest run excludes `smoke` (`addopts = "-m 'not smoke'"`). Unit/protocol tests use fake STT/TTS/LLM/VAD from `tests/conftest.py`, so no models or GPU are needed. Live-stack end-to-end checks (synthesized speech, no mic): `docker compose exec -e PYTHONPATH=/app backend python tests/e2e_voice_client.py` (also `e2e_tamil_client.py`, `e2e_personas_client.py`). No linter is configured. Frontend build: `cd frontend && npm run build` (runs `tsc` first).

Ports: frontend (nginx) `:2000`, backend `127.0.0.1:2324` (host 2323 is taken by another service), llm `127.0.0.1:2380`. Containers talk by service name (`http://llm:8080/v1`).

## Architecture

Three compose services: `llm` (llama.cpp serving Qwen3-4B GGUF, GPU), `backend` (FastAPI: VAD + STT + TTS + pipeline + SQLite), `frontend` (nginx + Vite/React SPA, proxies `/api` and `/ws`). An optional `neo4j` service lives behind `--profile memory`. GPU budget is ~4.8 GB of 6 GB, so don't add resident GPU models casually.

**Wiring:** `backend/main.py` `lifespan` constructs everything once and hangs it on `app.state` (store, llm, stt, tts router, `make_vad` factory, memory extractor/retriever/consolidator, context assembler, optional SER/FER emotion models). `backend/api/ws.py` makes one `ConversationPipeline` per WebSocket connection, each with its own stateful VAD. Settings are all env-driven in `backend/config.py`.

**Turn pipeline** (`backend/core/pipeline.py`, the central file): mic PCM (16 kHz int16) → Silero turn detector → faster-whisper STT (sets language) → llama.cpp stream → `SentenceSegmenter` → `clean_for_speech()` (strips markdown, emojis, emoticons) → `TTSRouter` (en → Kokoro, ta → Piper, 24 kHz out) → binary WS frames. State machine: `listening → transcribing → generating → speaking`. STT/TTS run in thread executors; never block the event loop.

**Easy to break:**
- *Echo guard:* by default the mic is ignored while the assistant is busy plus `ECHO_TAIL_S` after playback ends, otherwise it hears itself and loops. `ALLOW_BARGE_IN=true` (headphones only) switches to full-duplex interruption, which cancels the LLM and TTS tasks and sends `interrupted`.
- *Language routing:* STT language probability < 0.7 falls back to `en`; Tamil falls back to Kokoro if the Piper model is missing.
- *Protocol is duplicated:* WS message shapes live in `docs/API.md` and `frontend/src/types/protocol.ts` (Zod). Change both together with `backend/api/ws.py`.
- *History windowing:* `pipeline._windowed_messages` fits the 8k context using a ~4 chars/token heuristic.

**Memory (layered, behind interfaces):** `backend/memory/interfaces.py` defines the Protocol contracts. SQLite (`backend/db.py`, `medusa.db`) holds sessions, messages, events, `memories` (per-session summaries), and memory artifacts. `ShadowMemoryExtractor` writes artifacts per turn; `HybridMemoryRetriever` + `HybridContextAssembler` build prompt context when `MEMORY_ENABLED` and `MEMORY_HYBRID_RETRIEVAL` are on, else `HistoryContextAssembler` (plain recent history). `SessionMemoryConsolidator` summarizes on disconnect or session switch, and the summaries fill the `{memory}` slot of the persona prompt. The Neo4j semantic graph is off by default (`SEMANTIC_MEMORY_ENABLED=false`); `create_semantic_memory_store()` presumably returns `None` then [?].

**Persona:** only `config/personas/medusa.yaml` exists (`proactive` greets first, `cross_session_memory`). Persona is locked per session in `sessions.persona`. The prompt forbids invented shared history and bans emojis, markdown and long replies because the output is spoken.

**Emotion (opt-in, CPU):** `backend/core/emotion.py` fuses voice SER (wav2vec2) and face FER (EmotiEffNet ONNX) into a behavior hint injected into the prompt via `emotion_context()`. Weights and thresholds are in `config.py`.

## Repo notes

- Logs go to `./logs/medusa.log` (daily rotation, 30 days), mounted into the container.
- `docs/` holds `architecture.md`, `API.md`, `docker.md`, `FIXES.md`, plus planning docs. Some are stale: `docker.md` and `README.md` still describe the old 5-persona (Clarity/Engineer/Friend…) setup, `tests/conftest.py` `FakePersonaRegistry` still mocks a Clarity persona, and `docs/API.md` calls the greeting a "Friend persona" feature.
- Read `HANDOVER.md` first (its "rules that bite" list matters). Activity goes in `STATUS.md`, decisions in `DECISIONS.md` (append-only), people-blocked items in `BLOCKERS.md`, versions in `VERSIONS.md`, and bug fixes in `docs/FIXES.md`. `docs/README.md` indexes every doc.
- v4 (camera perception, multimodal brain, native Tamil voice, memory v4) is a **proposal** in `docs/v4/` backed by `docs/research/`. Model numbers there are mostly unverified, so run the benchmark gates in `docs/v4/roadmap.md` before adopting a model.
- Do not commit `.env` or anything under `models/`, `data/`, `logs/`.
