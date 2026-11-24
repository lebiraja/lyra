# HANDOVER

Read this first. Newest entry on top.

---

## 2026-11-24 IST

**State:** docs only. The product is now **Lyra** (D-41); the code still says `medusa`/`clarity` until the P0 rename PR. Plan revised with D-41…D-48: total-recall archive, five-layer user model, human-likeness, one voice, audio archive opt-in.

**Read in this order:** `docs/v4/plan.md` → `docs/v4/checklist.md` → `docs/v4/user-model.md` → `docs/v4/persona.md` → `docs/v4/rename-lyra.md`.

**Next step:** P0 task 0, the rename (`refactor/rename-lyra`), then the hygiene fixes.

### Rules that bite (new)
- **Never rename a compose volume key without pinning `name:`** to the existing volume. Otherwise compose creates an empty one and every conversation is orphaned.
- **The archive is the source of truth.** Facts, insights, the profile, vec/fts and Neo4j are projections. Never write user-visible knowledge that has no `source_turn_id`.
- **One voice (D-47).** Don't add a second TTS voice to any default path.

---

## 2026-11-10 22:36 IST

**State:** v3 (Medusa, single persona) runs: EN/TA voice loop, emotion (SER+FER), hybrid memory scaffolding. Tree clean on `main` at `75eace7`, plus the new docs from this session (uncommitted).

**This session:** research and docs, then a no-behaviour-change cleanup (backend 3.0.1) and a `make models` fix. 18 reference repos were cloned into `reference/` (gitignored). Lebi's goal for v4 is a companion that **sees** (camera: emotion, movement, activity), **hears**, **remembers** (graph memory) and replies **as fast as possible**, edge-only, natively EN + TA + Tanglish, with a fully new UI.

**Read in this order:**
0. **`docs/v4/plan.md` + `docs/v4/checklist.md`: the approved master plan (2026-11-11). Everything below is background.**
1. `docs/research/2026-11-current-state-audit.md`: what's broken or slow today
2. `docs/v4/architecture.md`: the proposed design (two-lane perception, one multimodal brain, single voice, idle-time memory)
3. `docs/v4/roadmap.md`: phases and benchmark gates G0–G7
4. `docs/v4/ui-redesign.md`: the "Marginalia" UI
5. `docs/research/2026-11-model-landscape.md` and `…-similar-projects.md`: evidence and sources
6. `docs/research/2026-11-reference-repos.md`: what reading 18 cloned repos in `reference/` changed. **GLaDOS is the closest blueprint.**

**Next step:** P0 in `docs/v4/checklist.md`. It contains two real bugs (Tamil-blind memory, duplicate summary injection) plus perf fixes. Use the issue → PR workflow. Bugs need a failing-first regression test.

### Rules that bite
- **6 GB VRAM is the hard limit.** A 4B multimodal brain, a 3B LLM-TTS and GPU Whisper together don't fit (architecture §4). Don't add a resident GPU model without a VRAM line item and a G0 measurement.
- **Host port 2323 is taken** (bedrock-proxy). The backend is published on `127.0.0.1:2324`.
- **Echo guard:** on laptop speakers the bot hears itself. Keep `ALLOW_BARGE_IN=false` unless AEC lands (architecture §3.4).
- **The protocol lives in three places:** `backend/api/ws.py`, `docs/API.md`, `frontend/src/types/protocol.ts`. Change all three together.
- **Model numbers in the docs are mostly unverified** (tagged [3p]/[vendor]/[est]). Don't quote them as facts. Run the gate.
- **Indic-Transcribe / Indic-Speak** are gated under the Indic Open Model License: fine for personal use, but don't bake the weights into public Docker Hub images (`lebiraja/clarity-*`).
- **Personal eval data** (voice, webcam stills) stays out of git.
- **Tests run in Docker:** `make test` (fake engines, no GPU needed, source bind-mounted). `make lint` runs ruff (pyflakes) and `tsc`.
- **`reference/` is third-party code:** read only, never run it, never copy without a licence check, never commit it (only its README is tracked).
- **Compose names `clarity-*` become `lyra-*` in the P0 rename**, with the data volume pinned by `name:` (see `docs/v4/rename-lyra.md`). Don't rename them any other way: renaming orphans the `clarity-data` volume on machines that have data.
- **A `.env` file must exist** for compose (`env_file: .env`). `cp .env.example .env`.
- **Run `make models` before any `docker compose run/up`.** Otherwise Docker creates the bind-mounted `models/kokoro`, `models/piper-tamil` and `logs/` as **root**, and the host-side download can't write into them. Fix: `docker run --rm -v "$PWD":/w alpine chown 1000:1000 /w/logs /w/models/*`.
