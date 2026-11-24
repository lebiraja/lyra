# Research: user modelling and lifelong memory for a local companion (Nov 2026)

**Question:** How should Lyra store **everything** (all transcripts, conversations and signals) fully locally, and turn it into a model of the user that is accurate, editable and fast enough for a voice turn?
**Feeds:** [v4/user-model.md](../v4/user-model.md) and plan D-42/D-43.
**Builds on:** plan §11 (memory v4: SQLite source of truth, sqlite-vec, FTS5 trigram, Neo4j projection) and [model-landscape](2026-11-model-landscape.md) (EmbeddingGemma).
Figures marked [abs] are from abstracts or excerpts and unverified.

---

## 1. Systems compared

| System | Core idea | Temporal handling | What we take | What we skip |
|---|---|---|---|---|
| **Generative Agents** (Park et al. 2023, arXiv 2304.03442) | Memory stream of observations; retrieval = recency × importance × relevance; **reflection** writes higher-level inferences back into the stream | Recency decay only | Importance score (1–10) per archived turn; nightly **reflection → insights**; reflections are memories too | Planning module (not needed for a companion) |
| **Zep / Graphiti** (arXiv 2501.13956, Jan 2025) | Temporal knowledge graph in 3 tiers: **episode** subgraph → **semantic entity** subgraph → **community** subgraph | **Bi-temporal**: event time T and ingestion time T′; every edge has a `t_valid`/`t_invalid` window | Our `facts` already have `valid_from/valid_to/recorded_at` (D-31), which confirms the design. Add **communities** as `topics` (clusters of entities and episodes) | Graphiti itself (Python service, an OpenAI-style LLM per ingest; too heavy next to E4B on 6 GB). Reported: 94.8% vs MemGPT 93.4% on DMR; up to +18.5% accuracy and −90% latency on LongMemEval [abs] |
| **Mem0 / Mem0g** (arXiv 2504.19413, Apr 2025) | Extract → **consolidate** (ADD / UPDATE / DELETE / NOOP against similar memories) → retrieve; the graph variant adds entity relations | Updates overwrite; the graph keeps relations | Our supersede/confirm/negate rules are the same consolidation idea, with stricter bi-temporal history. Reported: +26% LLM-judge over OpenAI memory on LoCoMo, 91% lower p95 latency, > 90% token savings [abs] | The library itself (cloud-first defaults, extra LLM calls per message) |
| **O-Mem** (arXiv 2511.13593) | Builds and updates **user profiles** (persona attributes plus topic/event memory) actively from every interaction, not only retrieval | Profile updated incrementally | A **two-level user model**: stable profile attributes and episodic topics. Reported 51.76% LoCoMo, 62.99% PERSONAMEM [abs] | — |
| **Mem-PAL / PAL-Bench** (arXiv 2511.13410) | Argues LoCoMo-style benchmarks miss the **subjective** side (preferences, style) | — | Eval idea: probes about preferences and style, not only facts (G4 / G10 probes) | Chinese-only benchmark |
| **PERMA** (arXiv 2603.23231) | Preferences drift; static snapshots are wrong | Preference change over time | Preferences are facts with validity windows; "used to like X" is answerable | — |
| **ZifaMem** (arXiv 2607.17564) | Structured persona, preference and **emotional continuity** memory for companions | Emotional timeline | A **mood timeline** (daily affect) as a first-class store | — |

**Conclusion:** no off-the-shelf memory library fits the 6 GB, offline, Tamil-first constraint. The plan's own design (SQLite source of truth + vec + FTS5 trigram + Neo4j projection) already matches the field's best ideas: bi-temporal facts (Zep), consolidation (Mem0) and retrieval scoring (Generative Agents). Three things are missing and are added in [user-model.md](../v4/user-model.md):
1. **A verbatim archive** of every turn: what was said, how it was said and what Lyra perceived. The other layers are derived from it and can be **rebuilt** from it.
2. **A reflection layer** (insights, routines, mood timeline, communication style) on top of facts.
3. **Open loops**: unresolved things he mentioned, which drive follow-ups.

---

## 2. Design principles derived

1. **Archive first, derive later.** Store the raw conversation losslessly. Facts, episodes, insights, the profile, vec, fts and Neo4j are all **projections** that a job can rebuild (`make memory-rebuild`). A better extractor next year can then re-mine two years of history. This is the strongest argument for "store everything".
2. **Bi-temporal everything that can change.** Facts, preferences, routines and relationships carry `valid_from/valid_to` (world time) and `recorded_at` (when Lyra learnt it). "Where did I work last year?" needs world time. "When did I tell you?" needs record time.
3. **Consolidate, don't append.** Each new extraction is checked against existing memories with the same `canonical_key`, giving ADD / CONFIRM / SUPERSEDE / NEGATE (plan §11.3). This prevents 40 near-duplicate "likes coffee" rows.
4. **Importance at write time, reflection at idle time.** Rating importance is cheap (one field in the extraction JSON). Reflection is expensive and runs nightly, or when ≥ 50 new importance points accumulate (the Generative Agents trigger).
5. **The user model is text the LLM can read.** The profile (≤ 300 tokens, frozen per session for the prefix cache) is the compressed view. Structured tables back it for the UI and for editing.
6. **Everything is editable and traceable.** Each derived item keeps `source_turn_ids`. Editing or deleting a source propagates (a deleted turn deletes the facts extracted only from it).
7. **Pixels never; audio opt-in.** Camera frames are never stored (S8). Raw voice is stored **only** if `ARCHIVE_AUDIO=true` (default **off**). The value is future re-transcription and a personal LoRA for the hear path (v4.1). The cost is disk use (~1 MB/min Opus 24 kbps ≈ 60 MB per hour of talk) and a more sensitive dataset. See user-model.md §2.3.

---

## 3. Fit with the hardware budget
| Job | Where | Cost | When |
|---|---|---|---|
| Archive write (turn, signals) | `EventWriter` batch, SQLite WAL | < 1 ms per turn off the hot path | every turn |
| Importance + facts extraction | E4B slot 1 | ~0.5–1.5 s per turn window | idle ≥ 20 s (existing D-31) |
| Embedding archive turns | EmbeddingGemma-300M, CPU | ~20–30 ms per sentence [est] | idle |
| Reflection (insights, routines, style, open loops) | E4B slot 1, thinking budget 512 | ~10–30 s per run [est] | nightly at 04:00 if the app is open, else at next session start; or the importance trigger |
| Mood timeline roll-up | pure SQL over `turn_signals` + `perception_minutes` | ms | session end + nightly |

Nothing here touches VRAM beyond the existing E4B slot 1. **No new GPU model.**

---

## Sources
- [Generative Agents (arXiv 2304.03442)](https://arxiv.org/pdf/2304.03442v2) · [Memory for autonomous LLM agents survey (arXiv 2603.07670)](https://arxiv.org/pdf/2603.07670)
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv 2501.13956)](https://arxiv.org/html/2501.13956) · [Graphiti on GitHub](https://github.com/getzep/graphiti) · [Zep blog](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory)
- [Mem0 (arXiv 2504.19413)](https://arxiv.org/abs/2504.19413)
- [O-Mem (arXiv 2511.13593)](https://arxiv.org/html/2511.13593v2) · [Mem-PAL (arXiv 2511.13410)](https://arxiv.org/html/2511.13410v2) · [PERMA (arXiv 2603.23231)](https://arxiv.org/html/2603.23231v1) · [ZifaMem (arXiv 2607.17564)](https://arxiv.org/abs/2607.17564) · [ARPM (arXiv 2605.14802)](https://arxiv.org/pdf/2605.14802)
