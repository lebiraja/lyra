# Docs index

## Running system (v3: Medusa)
| Doc | What |
|---|---|
| [architecture.md](architecture.md) | Services, voice pipeline, echo guard, persona, logging, frontend |
| [API.md](API.md) | REST and WebSocket protocol (mirrored in `frontend/src/types/protocol.ts`) |
| [docker.md](docker.md) | Setup, ports, commands, e2e voice checks, troubleshooting |
| [FIXES.md](FIXES.md) | Log of significant bug fixes and their reasoning |

## v4 proposal: perceptive companion (not implemented)
| Doc | What |
|---|---|
| [v4/architecture.md](v4/architecture.md) | Target design: two-lane perception, multimodal brain, single voice, memory v4, latency and VRAM budgets |
| [v4/roadmap.md](v4/roadmap.md) | Phases 0–6 and benchmark gates G0–G7 |
| [v4/ui-redesign.md](v4/ui-redesign.md) | "Marginalia" UI direction, screens, tech plan |

## Research (Nov 2026)
| Doc | What |
|---|---|
| [research/2026-11-current-state-audit.md](research/2026-11-current-state-audit.md) | Code and UI audit with `file:line` findings |
| [research/2026-11-model-landscape.md](research/2026-11-model-landscape.md) | VLM / STT / TTS / turn / SER / embedding candidates with sources |
| [research/2026-11-similar-projects.md](research/2026-11-similar-projects.md) | Open-source prior art and what to borrow (web search) |
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
