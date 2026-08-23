"""Hybrid retrieval across recent events, artifacts, fallback summaries, and graph memory."""

from __future__ import annotations

import math
import re
from collections import Counter

from backend.memory.interfaces import ConversationMemoryStore, RetrievedContext, SemanticGraphStore

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _score(query: str, candidate: str) -> float:
    q = Counter(_tokenize(query))
    c = Counter(_tokenize(candidate))
    if not q or not c:
        return 0.0
    dot = sum(q[token] * c[token] for token in q)
    q_norm = math.sqrt(sum(value * value for value in q.values()))
    c_norm = math.sqrt(sum(value * value for value in c.values()))
    if q_norm == 0 or c_norm == 0:
        return 0.0
    return dot / (q_norm * c_norm)


class HybridMemoryRetriever:
    def __init__(
        self,
        store: ConversationMemoryStore,
        graph_store: SemanticGraphStore | None = None,
        *,
        recent_message_limit: int = 8,
        semantic_limit: int = 8,
    ) -> None:
        self.store = store
        self.graph_store = graph_store
        self.recent_message_limit = recent_message_limit
        self.semantic_limit = semantic_limit

    async def retrieve(
        self,
        *,
        session_id: str,
        persona_id: str,
        query: str,
        limit: int = 12,
    ) -> RetrievedContext:
        history = await self.store.get_messages(session_id)
        recent_messages = history[-self.recent_message_limit :]

        artifacts = await self.store.list_memory_artifacts(
            session_id=None,
            only_active=True,
            limit=max(limit * 3, self.semantic_limit),
        )
        ranked_artifacts = sorted(
            artifacts,
            key=lambda item: (
                _score(query, item["content"]),
                item["confidence"],
                item["id"],
            ),
            reverse=True,
        )

        semantic_memories = [item["content"] for item in ranked_artifacts[: self.semantic_limit]]
        facts = [
            item["content"]
            for item in ranked_artifacts
            if item["artifact_type"] == "fact"
        ][: self.semantic_limit]

        metadata = {
            "artifact_hits": len(ranked_artifacts[: self.semantic_limit]),
            "recent_messages": len(recent_messages),
            "retrieval_mode": "hybrid-local",
        }

        if self.graph_store is not None:
            graph_context = await self.graph_store.retrieve(
                session_id=session_id,
                persona_id=persona_id,
                query=query,
                limit=self.semantic_limit,
            )
            semantic_memories.extend(graph_context.semantic_memories)
            facts.extend(graph_context.facts)
            metadata["graph"] = graph_context.metadata
            metadata["retrieval_mode"] = "hybrid-graph"

        if persona_id == "medusa":
            summaries = await self.store.get_memories(persona_id, limit=4)
            semantic_memories.extend(summaries)

        deduped_semantic = list(dict.fromkeys(semantic_memories))[: self.semantic_limit]
        deduped_facts = list(dict.fromkeys(facts))[: self.semantic_limit]
        return RetrievedContext(
            recent_messages=recent_messages,
            semantic_memories=deduped_semantic,
            facts=deduped_facts,
            metadata=metadata,
        )
