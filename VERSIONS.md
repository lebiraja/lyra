# VERSIONS

SemVer per part. Bump every part you change. Unreleased changes are logged under **Unreleased** until a release is cut.

| Part | Current | Source of truth |
|---|---|---|
| backend | 3.0.1 | `backend/main.py` (`FastAPI(version=...)`) |
| frontend | 2.0.0 | `frontend/package.json` |
| WS protocol | 3 (implicit) | `docs/API.md`, `frontend/src/types/protocol.ts` |
| persona (medusa) | 1.1.0 | `config/personas/medusa.yaml` (human-touch prompt, July 2026) |
| docs | 1.3.0 | this file |

## Unreleased

### docs 1.2.0 → 1.3.0 (2026-11-11)
- Added `docs/v4/plan.md` (master plan) and `docs/v4/checklist.md`. Appended D-11…D-40 to DECISIONS. Updated BLOCKERS. Marked the v4 architecture and roadmap docs as superseded for decisions.

### backend 3.0.0 → 3.0.1 (2026-11-10) — cleanup, no behaviour change
- `print()` → `logger` in the pipeline failure paths and startup (`backend/main.py`, `backend/core/pipeline.py`), so they reach `medusa.log`.
- Removed the unused `app.state.db` alias and unused imports. Fixed stale "Friend persona" comments.
- Tests: the fake persona is renamed `clarity` → `plain`; unused imports and variables removed; new `tests/test_scripts.py`.
- Tooling: `make lint` (ruff pyflakes + `tsc`); `make test` bind-mounts the source, so no rebuild is needed after edits; `[tool.ruff]` in `pyproject.toml`.
- `.env.example`: Medusa header, `DB_PATH=/app/data/medusa.db` (it said `clarity.db`, which didn't match the code default), the emotion settings and `LOGS_DIR`.
- Fix: `make models` no longer runs host Python (see `docs/FIXES.md`).

### docs 1.1.0 → 1.2.0 (2026-11-10)
- Added `docs/research/2026-11-reference-repos.md` and `reference/README.md` (18 cloned repos, gitignored).
- Folded the findings into v4: new D-1 options (Gemma 4 E4B native audio, Indic-Mio 0.6B), Smart Turn has no Tamil, AEC reference, GLaDOS-style initiative engine.
- Archived the old plans to `docs/archive/`. Rewrote `README.md` for Medusa. Synced `API.md` (events, memory artifacts, `video_frame`, `emotion`), `docker.md` and v3 `architecture.md` (emotion and memory sections).

### docs 1.0.0 → 1.1.0 (2026-11-10)
- Added the v4 research and design set: `docs/research/*`, `docs/v4/*`.
- Added the default project docs: `STATUS.md`, `HANDOVER.md`, `DECISIONS.md`, `BLOCKERS.md`, `VERSIONS.md`, `docs/README.md`, `CLAUDE.md`.
- No code changes, so the backend, frontend, protocol and persona versions are unchanged.

## Planned
- **v4.0.0** (backend, frontend, protocol 4): perceptive companion, per `docs/v4/roadmap.md`. Protocol 4 is a breaking change (typed binary frames, percept messages).
