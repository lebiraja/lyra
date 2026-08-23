"""Periodic consolidation for memory artifacts."""

from __future__ import annotations

from backend.memory.interfaces import ConversationMemoryStore, SemanticGraphStore


class SessionMemoryConsolidator:
    def __init__(
        self,
        store: ConversationMemoryStore,
        graph_store: SemanticGraphStore | None = None,
    ) -> None:
        self.store = store
        self.graph_store = graph_store

    async def consolidate_session(self, session_id: str) -> None:
        artifacts = await self.store.list_memory_artifacts(session_id=session_id, limit=200)
        seen: dict[tuple[str, str], int] = {}
        for artifact in artifacts:
            key = (artifact["artifact_type"], artifact["content"])
            seen[key] = seen.get(key, 0) + 1

        for artifact in artifacts:
            frequency = seen[(artifact["artifact_type"], artifact["content"])]
            if frequency < 2 or self.graph_store is None:
                continue
            boosted = dict(artifact)
            boosted["confidence"] = min(0.99, artifact["confidence"] + 0.05 * (frequency - 1))
            await self.graph_store.upsert_artifact(boosted)
