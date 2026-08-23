# Human-Like Memory Architecture Plan

## Purpose

This document is the architecture plan for evolving Clarity from a turn-replay chatbot into a memory-backed conversational system with a more human-like internal model.

It is based on:

- the current codebase in this repository
- the current runtime constraints of this app (local-first, low-latency, GPU budget already tight)
- recent graph-memory and GraphRAG patterns from Neo4j, Microsoft GraphRAG, Mem0, Zep/Graphiti, and recent agent-memory papers

This plan is intentionally limited to `docs/` and does not interfere with the active antigravity implementation work.

## Execution Status

This plan is now partially executed in the codebase as a safe transitional architecture.

Implemented in the current repository:

- storage contracts for conversation, artifacts, retrieval, consolidation, and semantic graph memory
- append-only `conversation_events` widened into a real lifecycle/event log
- `memory_artifacts` table for extracted facts, goals, preferences, and reflections
- shadow-mode memory extraction after completed turns
- hybrid context assembly with retrieval fallback to recent-history-only mode
- temporal invalidation for superseded facts such as employment and location
- optional Neo4j semantic memory adapter behind feature flags
- diagnostic REST endpoints for events and memory artifacts

This means phases 0-7 now exist in prototype form. The remaining work is quality, extraction precision, richer graph semantics, and performance tuning rather than architectural absence.

## Current State

The current architecture is clean, but its memory model is shallow.

### What exists now

- Voice pipeline: VAD -> STT -> LLM streaming -> sentence TTS -> WebSocket audio
- Persistence: SQLite with `sessions`, `messages`, and `memories`
- Cross-session memory: only the `Friend` persona stores a single summary per session
- Prompt construction: system prompt + recent chronological messages + optional emotion fragment

### Relevant code

- Current DB schema is flat and minimal in [backend/db.py](/home/lebi/projects/mentor_fine-tune/backend/db.py#L10)
- Conversation history is replayed chronologically from [backend/core/pipeline.py](/home/lebi/projects/mentor_fine-tune/backend/core/pipeline.py#L400)
- Memory writing is a single session summary in [backend/core/pipeline.py](/home/lebi/projects/mentor_fine-tune/backend/core/pipeline.py#L369)
- Session transport and turn orchestration live in [backend/api/ws.py](/home/lebi/projects/mentor_fine-tune/backend/api/ws.py#L65)

### Core limitations

1. Memory is append-only text, not structured knowledge.
2. Retrieval is recency-based, not relevance-based.
3. The system cannot track fact changes over time.
4. The system cannot connect entities, preferences, goals, people, and events across sessions.
5. Summarization destroys detail and chronology.
6. There is no explicit separation between working memory, episodic memory, and semantic memory.

## Design Position

Do not replace the whole persistence layer with a graph database.

That would be the wrong abstraction. Human-like memory is not "everything is a graph." It is multiple memory systems working together:

- working memory for the active turn
- episodic memory for what happened
- semantic memory for distilled facts and relationships
- procedural memory for persona and system behavior

The right architecture for this repository is a hybrid:

- immutable event log for raw turns
- graph database for long-term semantic memory
- vector retrieval for semantic similarity
- summarization/consolidation workers between them

## Recommended Target Architecture

### Recommendation

Use **Neo4j** as the long-term semantic memory store and keep a separate event store for raw conversation history.

### Why Neo4j

1. Mature graph model for entities and relationships
2. Native vector indexing and hybrid retrieval support
3. Good Python support
4. Local Docker deployment fits this repo
5. Strong fit for GraphRAG-style retrieval and multi-hop memory traversal

### Why not graph-only

Graph memory is good at facts and relationships. It is weaker at preserving exact sequence, raw evidence, and full-fidelity conversational replay. Recent agent-memory evaluations also show that no single memory architecture dominates all workloads; hybrid systems are stronger for conversational QA, while graph-heavy systems are better for factual recall than temporal replay.

## Human-Like Memory Model

Model the system as four layers.

### 1. Sensory / Working Memory

Short-lived in-process state for the active turn.

Contents:

- current VAD segment
- transcript candidate
- detected language
- current emotion state
- interrupted assistant partials
- temporary retrieval set for the current answer

Storage:

- in process only

### 2. Episodic Memory

Immutable record of what happened in the conversation.

Contents:

- user utterance
- assistant response
- timestamps
- language
- emotion state
- interruption events
- session boundaries
- tool events later, if tools are added

Storage:

- PostgreSQL recommended
- SQLite acceptable only for prototype phase

Reason:

Episodic memory needs durable sequencing, filtering, replay, and auditability. A relational event log is better than graph storage for this.

### 3. Semantic Memory

Long-lived extracted knowledge about the user, people, goals, routines, projects, preferences, and stable facts.

Contents:

- entities: `User`, `Person`, `Project`, `Goal`, `Habit`, `Topic`, `EmotionPattern`, `Preference`, `Value`, `Event`, `Session`
- relationships: `CARES_ABOUT`, `WORKS_ON`, `STRUGGLES_WITH`, `PREFERS`, `MENTIONED_IN`, `RELATED_TO`, `FOLLOW_UP_FOR`, `CHANGED_TO`
- fact validity: when a fact became true, when it stopped being true, confidence, provenance
- embeddings on memory nodes for similarity search

Storage:

- Neo4j

### 4. Procedural Memory

Behavioral rules and identity constraints.

Contents:

- persona definitions
- safety/system policies
- response style
- future task policies such as coaching loops or check-in cadence

Storage:

- config + code, not graph

## Target Data Model

### Event Store

Recommended tables:

- `users`
- `sessions`
- `conversation_events`
- `utterances`
- `assistant_messages`
- `emotion_events`
- `memory_jobs`
- `memory_artifacts`

Important rule:

`conversation_events` becomes the source of truth for chronology.

### Graph Store

Recommended node labels:

- `User`
- `Session`
- `Episode`
- `Utterance`
- `Entity`
- `Person`
- `Goal`
- `Preference`
- `Project`
- `Habit`
- `Topic`
- `Fact`
- `EmotionState`
- `Summary`

Recommended relationship types:

- `PART_OF`
- `MENTIONED`
- `ABOUT`
- `RELATES_TO`
- `PREFERS`
- `AVOIDS`
- `WORKING_ON`
- `WANTS`
- `FEELS`
- `FOLLOW_UP_ON`
- `KNOWS`
- `CHANGED_FROM`
- `CHANGED_TO`
- `VALID_DURING`
- `SUPPORTED_BY`

Important node/edge properties:

- `valid_from`
- `valid_to`
- `observed_at`
- `confidence`
- `source_session_id`
- `source_event_id`
- `embedding`
- `canonical_name`
- `aliases`

## Read Path

Replace the current "recent messages only" context build with a memory orchestrator.

### New answer flow

1. Capture turn input
2. Write raw event to event store
3. Build retrieval query from the current user utterance
4. Retrieve:
   - recent local thread context from episodic store
   - semantically similar memories from graph/vector search
   - directly connected graph neighbors for multi-hop context
   - active facts only (`valid_to IS NULL` or equivalent)
   - optional unresolved goals/follow-ups
5. Rank and compress retrieved context
6. Build prompt from:
   - persona/procedural memory
   - working memory
   - episodic recent context
   - semantic graph memory
7. Generate response
8. Write assistant output to event store

### Retrieval policy

Use hybrid retrieval, not pure vector retrieval and not pure graph traversal.

Recommended order:

1. thread-local recency
2. entity extraction from the current query
3. graph neighborhood expansion around matched entities
4. vector similarity over memory nodes
5. rerank by recency, confidence, validity, and source diversity

## Write Path

Memory writing should be asynchronous and conservative.

### After each turn

- store raw turn events synchronously
- enqueue memory extraction job asynchronously

### Memory extraction job

For each completed turn or turn pair:

1. extract entities
2. extract candidate facts
3. classify memory type:
   - ephemeral
   - episodic
   - semantic
   - preference
   - goal
   - follow-up
4. resolve entity identity against existing graph nodes
5. write or update graph
6. invalidate stale facts when contradicted
7. attach provenance back to raw events
8. generate compact summary nodes only when useful

### Consolidation jobs

Run periodic consolidation:

- session -> episode summaries
- repeated facts -> stronger confidence
- stale or contradicted facts -> invalidation
- cluster related episodes into higher-order topics
- promote recurring patterns into semantic memory

This is closer to human memory than storing every message equally.

## Migration Strategy

### Phase 0. Freeze the Contract

Status: implemented

Before replacing storage, stabilize interfaces.

Add repository-level abstractions:

- `ConversationStore`
- `MemoryExtractor`
- `MemoryRetriever`
- `MemoryConsolidator`
- `ContextAssembler`

Goal:

`ConversationPipeline` should depend on interfaces, not on SQLite directly.

### Phase 1. Split Raw History From Memory

Status: implemented in transitional SQLite form

Keep current behavior, but stop treating `messages` as both transcript and memory system.

Actions:

- introduce an append-only conversation event model
- keep current prompt behavior unchanged
- keep SQLite temporarily if needed
- add structured metadata columns for language, emotion, interruption, and message type

Exit criteria:

- pipeline behavior unchanged
- full turn replay possible from event log

### Phase 2. Add Memory Services

Status: implemented in shadow mode

Introduce memory extraction and retrieval behind feature flags.

Actions:

- add `MemoryExtractor` worker
- extract entities/facts from finished turns
- continue storing `Friend`-style summaries as fallback
- add retrieval diagnostics

Exit criteria:

- graph memory populated in shadow mode
- no prompt dependency on graph yet

### Phase 3. Introduce Neo4j Semantic Memory

Status: implemented behind feature flags and Docker profile

Actions:

- add Neo4j service to `docker-compose.yml`
- define graph schema and indexes
- write graph ingestion pipeline
- attach embeddings to selected nodes
- add hybrid search API for memory retrieval

Exit criteria:

- graph can answer memory queries with provenance
- active facts and changed facts are distinguishable

### Phase 4. Switch Prompt Assembly to Hybrid Memory

Status: implemented with fallback to history-only assembly

Actions:

- replace `_windowed_messages()` with a context assembly pipeline
- pull recent episodic context from event store
- pull semantic context from Neo4j
- cap memory payload by token budget
- add per-persona retrieval policies

Exit criteria:

- answers use relevant long-term memory without blowing latency
- no regression in turn-taking or TTS start time

### Phase 5. Add Temporal Memory and Fact Invalidation

Status: implemented for canonical superseding facts

Actions:

- support fact validity windows
- handle contradictions explicitly
- preserve historical truth without letting stale facts leak into current answers

Example:

- "I work at X" valid until March 2026
- "I now work at Y" becomes the active fact

Exit criteria:

- system distinguishes past facts from current facts

### Phase 6. Add Reflective / Goal-Centric Memory

Status: implemented at scaffold level via artifact extraction

Actions:

- track recurring goals and blockers
- create follow-up nodes and reminder edges
- infer stable patterns only after repeated evidence

This is where the assistant starts to feel more continuous and less stateless.

### Phase 7. Optimize

Status: partially implemented via bounded retrieval and payload caps

Actions:

- cache hot subgraphs
- precompute user summary blocks
- bound graph traversal depth
- batch extraction jobs
- profile retrieval and assembly latency

Exit criteria:

- memory retrieval target under 150-250 ms
- no noticeable impact on perceived voice responsiveness

## Recommended Concrete Stack

### Minimum viable target

- `PostgreSQL` for conversation event log
- `Neo4j` for semantic memory graph
- local embedding model for memory node embeddings
- background worker for extraction and consolidation

### Keep as-is

- FastAPI
- WebSocket protocol
- VAD/STT/TTS pipeline
- persona config model

### Optional later

- Redis for queues/caching
- graph analytics for importance scoring
- small local model for low-cost memory extraction

## Changes Needed In This Repo

### Backend

Refactor [backend/core/pipeline.py](/home/lebi/projects/mentor_fine-tune/backend/core/pipeline.py#L41):

- remove direct dependence on `db.get_messages()` for context building
- introduce a `ContextAssembler`
- write conversation events immediately
- query memory services for prompt context

Refactor [backend/db.py](/home/lebi/projects/mentor_fine-tune/backend/db.py#L42):

- split into storage interfaces and implementations
- deprecate `memories` as the main long-term memory mechanism
- keep migration adapters during transition

Add new modules:

- `backend/memory/interfaces.py`
- `backend/memory/event_store.py`
- `backend/memory/graph_store.py`
- `backend/memory/extractor.py`
- `backend/memory/retriever.py`
- `backend/memory/consolidator.py`
- `backend/memory/context_assembler.py`

### API

The external API can remain mostly stable.

Add optional diagnostics endpoints later:

- memory retrieval trace
- current active facts
- session memory summary

### Frontend

No major contract changes are required for the first migration.

Possible later additions:

- user memory inspector
- correction UI: "that is outdated" / "remember this"
- explainability surface for why the assistant remembered something

## Risks

### Risk 1. Graph-only overengineering

If raw logs, retrieval, and temporal validity are all forced into one graph layer, the system will get slower and harder to debug.

Mitigation:

- keep event log separate

### Risk 2. Wrong fact extraction

LLM extraction can create false memories.

Mitigation:

- attach provenance
- store confidence
- require repeated evidence before promoting weak facts
- allow explicit invalidation

### Risk 3. Temporal confusion

Many memory systems retrieve outdated facts.

Mitigation:

- temporal properties on edges
- active-fact filtering at retrieval time

### Risk 4. Latency regression

Voice UX will fail if memory retrieval stalls answer generation.

Mitigation:

- async write path
- bounded retrieval
- precomputed memory blocks
- fallback to recent-thread-only mode

### Risk 5. Costly rewrite

Big-bang migration will break the working product.

Mitigation:

- shadow mode
- interface-first refactor
- feature flags

## Success Metrics

You should not judge the new architecture by "it uses a graph DB."

Judge it by these metrics:

1. factual continuity across sessions
2. correct handling of changed facts
3. fewer irrelevant recalls
4. lower prompt token waste
5. stable voice latency
6. explainable provenance for remembered facts
7. easy rollback when extraction is wrong

Recommended measurable targets:

- memory retrieval p95 < 250 ms
- prompt context tokens reduced by at least 40% versus naive history replay for long sessions
- fact conflict resolution precision > 90% on evaluation set
- long-session answer quality materially better than current recency-only baseline

## Implementation Order

Recommended execution order:

1. storage abstraction
2. append-only event model
3. extraction worker in shadow mode
4. Neo4j graph schema and ingestion
5. hybrid retrieval
6. prompt/context assembler
7. temporal invalidation
8. optimization and evaluation

## Final Recommendation

The correct move is not "replace SQLite with a graph DB."

The correct move is:

- keep exact conversation history as an event log
- add a graph database for semantic long-term memory
- add extraction, retrieval, and consolidation services
- make prompt assembly memory-aware and time-aware

That architecture will feel more human because it separates what just happened, what happened before, what is generally true, and what is no longer true.

## Research Notes

The plan above is aligned with the following external references:

- Neo4j documentation says vector indexes support similarity search and hybrid retrieval patterns: https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
- Neo4j GraphRAG Python is a maintained first-party package with Python 3.10-3.14 support and Neo4j 5.18+/2026.01+ support: https://neo4j.com/docs/neo4j-graphrag-python/current/
- Microsoft GraphRAG describes a structured approach where raw text is turned into a knowledge graph plus community summaries for retrieval-time augmentation: https://microsoft.github.io/graphrag/
- Mem0 documents layered memory types: conversation, session, user, and organizational memory: https://docs.mem0.ai/core-concepts/memory-types
- Zep/Graphiti documents temporal context graphs where facts carry validity windows and outdated facts are invalidated while history is preserved: https://help.getzep.com/graph-overview and https://www.getzep.com/platform/graphiti/
- Recent graph-memory survey literature frames memory as a lifecycle of extraction, storage, retrieval, and evolution: https://arxiv.org/html/2602.05665v1
- Recent agent-memory evaluation literature reports that no single architecture dominates and that composite hybrids are strongest for conversational QA, while graph methods are strong for factual recall but have temporal tradeoffs: https://arxiv.org/html/2606.24775v1
- Recent conversational-memory work also supports event-centric memory representations with graph-augmented retrieval as a strong design pattern: https://arxiv.org/html/2511.17208v2
