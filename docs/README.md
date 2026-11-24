# Docs index

## Running system (v3: Lyra, formerly Medusa; code identifiers renamed in P0)
| Doc | What |
|---|---|
| [architecture.md](architecture.md) | Services, voice pipeline, echo guard, persona, logging, frontend |
| [API.md](API.md) | REST and WebSocket protocol (mirrored in `frontend/src/types/protocol.ts`) |
| [docker.md](docker.md) | Setup, ports, commands, e2e voice checks, troubleshooting |
| [FIXES.md](FIXES.md) | Log of significant bug fixes and their reasoning |

## v4 proposal: perceptive companion (not implemented)
| Doc | What |
|---|---|
| **[v4/plan.md](v4/plan.md)** | **Master plan (approved): every model, decision, full flow, error matrix, protocol, schema, gates, phases. This one wins.** |
| **[v4/checklist.md](v4/checklist.md)** | **Executable checklist per phase (P0–P9), gates, Lebi tasks** |
| **[v4/user-model.md](v4/user-model.md)** | **Total-recall archive + five-layer user model: schema `003`, reflection, Notebook, archive API, forget/export/rebuild** |
| **[v4/persona.md](v4/persona.md)** | **Lyra's persona bible, relationship levels, human behaviours, healthy-companion rules, gate G10** |
| [v4/rename-lyra.md](v4/rename-lyra.md) | Medusa/Clarity → Lyra code rename (P0), with data-safety rules |
| [v4/architecture.md](v4/architecture.md) | Target design: two-lane perception, multimodal brain, single voice, memory v4, latency and VRAM budgets |
| [v4/roadmap.md](v4/roadmap.md) | Phases 0–6 and benchmark gates G0–G7 |
| [v4/ui-redesign.md](v4/ui-redesign.md) | "Marginalia" UI direction, screens, tech plan |

## Research (Nov 2026; documents dated before 2026-11-24 say "Medusa")
| Doc | What |
|---|---|
| [research/2026-11-current-state-audit.md](research/2026-11-current-state-audit.md) | Code and UI audit with `file:line` findings |
| [research/2026-11-model-landscape.md](research/2026-11-model-landscape.md) | VLM / STT / TTS / turn / SER / embedding candidates with sources |
| [research/2026-11-similar-projects.md](research/2026-11-similar-projects.md) | Open-source prior art and what to borrow (web search) |
| [research/2026-11-human-likeness.md](research/2026-11-human-likeness.md) | What makes a voice companion feel human: timing, backchannels, voice presence, gradual intimacy, healthy use (with sources) |
| [research/2026-11-user-modelling-memory.md](research/2026-11-user-modelling-memory.md) | Lifelong memory and user modelling: Generative Agents, Zep/Graphiti, Mem0, O-Mem, PERMA → our design |
| [research/2026-11-reference-repos.md](research/2026-11-reference-repos.md) | Findings from reading the cloned repos in `reference/` (GLaDOS, HF s2s AEC, Smart Turn, airi, Indic-Mio…) |

## Archive: earlier plans (implemented or superseded, `docs/archive/`)
| Doc | What |
|---|---|
| [archive/tamil_support_plan.md](archive/tamil_support_plan.md) | v2 → v3 bilingual design (implemented) |
| [archive/emotion-aware-conversation.md](archive/emotion-aware-conversation.md) | FER + SER research (implemented in v3) |
| [archive/implementation_plan.md](archive/implementation_plan.md) | Emotion implementation plan and validation checklist |
| [archive/human-like-memory-architecture-plan.md](archive/human-like-memory-architecture-plan.md) | Memory phases 0–7 (scaffolding implemented; v4 memory builds on it) |

## Root docs
`../reference/README.md` (third-party clones, gitignored) · `../HANDOVER.md` (read first) · `../STATUS.md` · `../DECISIONS.md` · `../BLOCKERS.md` · `../VERSIONS.md` · `../CLAUDE.md`
