.PHONY: models up down build logs test test-smoke lint dev clean

# One-time model download (~3 GB into ./models/). Whisper + emotion models auto-download on first backend start.
models:
	bash scripts/download_models.sh

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

# Unit + protocol tests (fake engines, fast). Source is bind-mounted so no rebuild is needed after edits.
test:
	docker compose run --rm --no-deps -v ./backend:/app/backend -v ./tests:/app/tests -v ./scripts:/app/scripts:ro backend pytest -q

# Smoke tests against real ONNX models (needs `make models` first)
test-smoke:
	docker compose run --rm --no-deps -v ./backend:/app/backend -v ./tests:/app/tests -v ./scripts:/app/scripts:ro backend pytest -q -m smoke

# Pyflakes (ruff) on backend + tests; TypeScript strict check on the frontend
lint:
	uvx ruff@0.14.0 check backend tests
	cd frontend && npx tsc --noEmit

# Frontend dev server (vite) against a running backend
dev:
	cd frontend && npm run dev

# Removes containers AND volumes (SQLite db, Whisper cache) — destructive
clean:
	docker compose down -v --remove-orphans
