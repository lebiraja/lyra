# Medusa

A fully local voice companion. Talk out loud in **English, Tamil or Tanglish** and get a voice back from **Medusa**, "the friend to share all the things". She greets you first, picks up your mood from voice and face, and remembers you across conversations. Nothing leaves the machine.

> Naming: the repo folder is `lyra`, the persona is **Medusa**, and the docker services, network, volumes and Docker Hub images still use the older `clarity-*` names.

- **Brain:** Qwen3-4B-Instruct-2507 (Q4 GGUF, llama.cpp, GPU)
- **Ears:** faster-whisper large-v3-turbo (CTranslate2, GPU int8), with automatic language detection
- **Voice (EN):** Kokoro-82M `af_heart` (ONNX, CPU) · **Voice (TA):** Piper `ta_IN-Valluvar-medium` (ONNX, CPU)
- **Turn-taking:** Silero VAD with a half-duplex echo guard (no self-listening on laptop speakers); barge-in is opt-in for headphones
- **Emotion:** speech emotion (wav2vec2) plus facial emotion from the camera (EmotiEffNet ONNX), fused and fed to the prompt (CPU only)
- **Memory:** SQLite event log, per-session summaries and hybrid retrieval; optional Neo4j graph (`--profile memory`)

## Quick start

Needs Docker with Compose v2, an NVIDIA GPU and `nvidia-container-toolkit`.

```bash
cp .env.example .env
make models   # one-time ~3 GB into ./models/ (Whisper + emotion models fetch on first start)
make up       # llm + backend + frontend
# open http://localhost:2000 and press begin
```

| Command | What |
|---|---|
| `make test` | unit + protocol tests in Docker (fake engines, no GPU or models needed) |
| `make test-smoke` | tests against the real ONNX models |
| `make lint` | ruff (pyflakes) on backend/tests, `tsc --noEmit` on the frontend |
| `make logs` / `make down` | follow logs / stop |
| `make dev` | Vite dev server against a running backend |

## Sizing (RTX 4050 Laptop, 6 GB)

| Component | VRAM |
|---|---|
| Qwen3-4B Q4_K_M (llama.cpp) | ~3.5 GB |
| Whisper large-v3-turbo int8 | ~1.3 GB |
| Kokoro, Piper, Silero, SER, FER (CPU) | 0 |
| **Total** | **~4.8 GB** |

About 1.5–3 s from the end of your speech to the first audio.

## Language

Speak in English, Tamil or Tanglish. The language is detected per utterance and Medusa replies in the same one. Below 0.7 detection confidence it falls back to English. Relevant settings: `STT_MODEL`, `STT_DEVICE`, `PIPER_TAMIL_ENABLED` (see `.env.example`).

## Docker Hub

Pre-built images: `lebiraja/clarity-backend` (~1.8 GB, CUDA runtime + FastAPI + STT/TTS/VAD) and `lebiraja/clarity-frontend` (~94 MB, nginx + Vite SPA).

## Docs

Start at **[docs/README.md](docs/README.md)** (index), then [HANDOVER.md](HANDOVER.md). The running system is described in [architecture](docs/architecture.md), [API](docs/API.md), [docker](docs/docker.md) and [fixes](docs/FIXES.md). The next version, a companion that also sees you, is proposed in [docs/v4/](docs/v4/architecture.md).

Old code (the v1 fine-tuning pipeline, multi-persona configs) lives only in git history.
