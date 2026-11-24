# Rename: Medusa / Clarity → Lyra

**Status:** APPROVED (D-41, 2026-11-24). Docs are renamed now. **The code rename is P0 task 0** (one `refactor/rename-lyra` PR, no behaviour change).
**Why:** the product had three names: the repo was `lyra`, the containers were `clarity-*` / "ClarityMentor", and the persona was Medusa. Lebi chose **Lyra** for all of them.

## 1. Rule for the docs
- **Lyra** is the product, the persona and the voice.
- Dated logs (`STATUS.md`, `docs/FIXES.md`, `DECISIONS.md` D-1…D-40, `docs/archive/`, `docs/research/` from before 2026-11-24) keep "Medusa" as history. They are not rewritten.
- Docs that describe the **running v3 code** say "Lyra (formerly Medusa)" and keep the real identifiers (`medusa.yaml`, `medusa.db`, `medusa.log`) until the code PR lands. That PR then updates those identifiers in the docs too.

## 2. Code rename (P0, one PR)

| Where | Now | After | Data safety |
|---|---|---|---|
| Persona file | `config/personas/medusa.yaml` (`id: medusa`, `name: Medusa`) | `config/personas/lyra.yaml` (`id: lyra`, `name: Lyra`) | `PersonaRegistry` keeps **`medusa` as an alias of `lyra`**, so existing `sessions.persona='medusa'` rows resolve without a data change. The row update (`UPDATE sessions SET persona='lyra'…`) goes into migration `002` (P6, Lebi's approval) |
| Persona default | `DEFAULT_PERSONA = "medusa"` (`backend/core/personas.py:14`), `DEFAULT 'medusa'` (`backend/db.py:15,101`), `create_session(persona="medusa")` (`backend/db.py:171`, `backend/memory/interfaces.py:15`) | `"lyra"` | the DDL default only affects new rows |
| Summary branch | `if persona_id == "medusa"` (`backend/memory/retriever.py:96`) | removed in P0 anyway (duplicate summary injection fix); otherwise `in {"lyra","medusa"}` | — |
| DB file | `data/medusa.db` (`backend/config.py:76`, `.env.example`) | `data/lyra.db` | at startup: if `lyra.db` is missing and `medusa.db` exists → **copy** (not move) it with its `-wal`/`-shm` files after a WAL checkpoint, and log it. `medusa.db` is left in place as a backup. Test: fixture with only `medusa.db` → `lyra.db` exists with the same rows |
| Log file | `logs/medusa.log` (`backend/main.py:15`) | `logs/lyra.log` | old rotated logs stay |
| App title | `FastAPI(title="Medusa")`, module docstrings, comments | "Lyra" | — |
| Frontend | `index.html` title, `App.tsx`, `PersonaPicker.tsx`, `package.json` `name` | Lyra | — |
| Browser storage | `localStorage["medusa.session"]` (`useConversation.ts`) | `lyra.session` | read the new key, fall back to the old one once, then write the new key and delete the old one |
| Compose containers | `clarity-llm`, `clarity-backend`, `clarity-frontend`, `clarity-neo4j` | `lyra-llm`, `lyra-backend`, `lyra-frontend`, `lyra-neo4j` (+ `lyra-tts` in P3) | container names hold no data |
| Compose network | `clarity` | `lyra` | no data |
| Compose volumes | `clarity-data`, `whisper-cache`, `neo4j-data`, `neo4j-logs` | key `lyra-data` **with `name:` pinned to the existing volume** (e.g. `name: lyra_clarity-data`; check the real name with `docker volume ls` first) | **never let compose create a fresh empty volume**: that orphans every conversation. Test: `docker compose config` shows the old volume name |
| Neo4j password default | `clarity-memory-dev` | **unchanged** | changing it locks out the existing `neo4j-data` store. Rotate later through `.env` only |
| Tests | `tests/test_personas.py` (`test_medusa_*`), `conftest.py`, `e2e_personas_client.py` | `lyra` names + one alias test (`medusa` resolves to `lyra`) | — |
| Scripts | `scripts/download_models.sh` header | Lyra | — |
| Docs | `CLAUDE.md`, `README.md`, `docs/architecture.md`, `API.md`, `docker.md` | identifiers updated | — |
| HANDOVER rule | "Don't rename `clarity-*` casually" | replaced with: "Volumes are pinned by `name:`; never rename a volume key without `name:`" | — |

**Out of scope:** the GitHub repo (already `lyra`) and any Docker Hub tags (`lebiraja/clarity-*`). Those are outward-facing and need a separate yes from Lebi.

## 3. Verification (PR checklist)
- `make test` and `make lint` green. New tests: alias, DB copy, localStorage fallback (vitest).
- `grep -rni medusa backend frontend/src config tests scripts` returns only the alias line and its test.
- On Lebi's machine: `make down && make up`. The old sessions are still listed in the session drawer, and memory summaries still load.
- `docker volume ls` shows no new empty `*_lyra-data` volume.
