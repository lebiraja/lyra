# Docker

## Prerequisites
- Docker + Compose v2
- NVIDIA driver + `nvidia-container-toolkit` (the `llm` service reserves the GPU)
- ~5 GB disk for model weights

## First run
```bash
cp .env.example .env          # set HF_TOKEN (only used for downloads)
make models                   # one-time, ~3 GB into ./models/ (Whisper + emotion models fetch on first start)
make up                       # build + start all three services
```
Open http://localhost:2000. The first backend start still downloads Whisper and the emotion models; after that no network is needed.

## Services & ports
| Service | Container | Host port | Notes |
|---|---|---|---|
| llm | clarity-llm | 127.0.0.1:2380 | llama.cpp server, GPU, loads the GGUF in ~30–60 s |
| backend | clarity-backend |  127.0.0.1:2324 | waits for llm healthcheck; ONNX engines load in ~30 s |
| frontend | clarity-frontend | 2000 | nginx; the only port meant for the browser |

Volumes: `./models/*` mounted read-only; `clarity-data` holds the SQLite db (`medusa.db`); `whisper-cache` holds Hugging Face downloads (Whisper, SER); `./logs` holds `medusa.log` (daily rotation, 30 days).

## Commands
```bash
make up / make down / make logs
make test          # unit + protocol tests (no models needed; source bind-mounted)
make lint          # ruff on backend/tests + tsc on frontend
make test-smoke    # real-model smoke tests (after make models)
make dev           # vite dev server on :5173, proxies to a running backend
make clean         # down + remove volumes
```

## End-to-end voice check (no microphone needed)
Speaks a synthesized question at the live stack and asserts on transcript, reply, and audio:
```bash
docker compose exec -e PYTHONPATH=/app backend python tests/e2e_voice_client.py     # English
docker compose exec -e PYTHONPATH=/app backend python tests/e2e_tamil_client.py     # Tamil
docker compose exec -e PYTHONPATH=/app backend python tests/e2e_personas_client.py  # Medusa: typed turn, greeting, cross-session memory
```

## Troubleshooting
- **llm unhealthy** — check `docker compose logs llm`; usually a missing/incomplete GGUF (`make models` resumes).
- **GPU not found** — `nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.
- **VRAM pressure** (other apps using the GPU): lower `--ctx-size` in `docker-compose.yml`.
- **Backend can't load ONNX models** — paths under `./models/` must match `scripts/download_models.sh` layout.
