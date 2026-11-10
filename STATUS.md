# STATUS

Activity log, newest first. One entry per feature, fix, refactor, config change, decision or blocker.

---

## 2026-11-11 — docs: v4 master plan + checklist (all decisions made)

**Type:** decision / plan
**What:** Lebi answered 12 product questions (D-11…D-22). I made and recorded the technical decisions (D-23…D-40).
- **Plan:** `docs/v4/plan.md` covers the model bill of materials (Gemma 4 E4B hears and sees, Indic-Mio voice, Smart Turn + Tamil, emotion2vec+, MediaPipe, EmbeddingGemma, SQLite + sqlite-vec + FTS5 + Neo4j projection), the full flow, the turn state machine, prompts, protocol v4, schema, a 28-row error matrix, tests, gates G0–G9 and phases P0–P9.
- **Checklist:** `docs/v4/checklist.md`.

**Next:** P0 hygiene fixes, then P1 eval kit (voice import from `~/Projects/voice-auth`).
**Blockers:** B-2 narrowed to ~15 min transcript correction + turn spot-check; see `BLOCKERS.md`.

---

## 2026-11-10 23:30 IST — chore: codebase cleanup + reference repos studied

**Type:** refactor (no behaviour change) + bug fix + research
**What:**
- **Cleanup:** unused imports (ruff pyflakes clean), `print` → `logger`, dead `app.state.db` alias, stale Clarity/Friend naming in tests, comments and docs, `.env.example` drift (`clarity.db` → `medusa.db`), and `make lint` / bind-mounted `make test`.
- **Docs:** old plans archived; README, API, docker and architecture synced with the code.
- **Bug fix:** `make models` crashed on a clean host because of a host-Python step. A regression test was added (`docs/FIXES.md`).
- **Research:** 18 repos shallow-cloned into gitignored `reference/` and read. **GLaDOS** (Gemma 4 E4B audio+vision, Autonomy Core) is the closest blueprint. HF speech-to-speech gives a reference **AEC** design. **Smart Turn has no Tamil.** **Indic-Mio 0.6B** is a VRAM-friendly Indic TTS. This changed D-1 (see D-8).

**Next:** Phase 0 bug fixes (Tamil-blind memory, duplicate summary injection, prompt order), then the eval kit.
**Blockers:** unchanged (`BLOCKERS.md`).

---

## 2026-11-10 22:36 IST — docs: v4 research and design set (no code changes)

**Type:** research / decision groundwork
**What:** Analysed the v3 codebase and UI, researched edge models (VLM, STT, TTS, turn-taking, SER, embeddings, memory) and similar open-source projects, and wrote the v4 "perceptive companion" proposal.
**Added:**
- `docs/research/2026-11-current-state-audit.md`: code and UI audit, 10 findings with `file:line`
- `docs/research/2026-11-model-landscape.md`: per-stage candidates with sources
- `docs/research/2026-11-similar-projects.md`: prior art (Open-LLM-VTuber, airi, Vocalis, openlive, Pipecat…)
- `docs/v4/architecture.md`, `docs/v4/ui-redesign.md`, `docs/v4/roadmap.md`
- Default project docs: `STATUS.md`, `HANDOVER.md`, `DECISIONS.md`, `BLOCKERS.md`, `VERSIONS.md`, `docs/README.md`, `CLAUDE.md`

**Key findings:**
- Memory retrieval and extraction are English-only: `[a-z0-9]+` tokeniser and English regexes, so Tamil memories score 0.
- Prompt layout defeats llama.cpp prefix caching.
- A 6 GB GPU can't host a 4B multimodal brain, a 3B LLM-TTS and GPU STT together. This is decision D-1.

**Next:** Phase 0 hygiene fixes (roadmap §2), then build the eval kit for gates G0/G2/G5.
**Blockers:** D-1 (VRAM profile) waits on G0–G3 measurements; see `BLOCKERS.md`.

---

## 2026-07-14 — Medusa single persona, human-touch prompt, rotating logs

Merged PR #7 (`feat/human-touch`). Details in `docs/FIXES.md`. *(Back-filled from git history.)*
