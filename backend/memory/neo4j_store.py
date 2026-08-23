"""Optional Neo4j-backed semantic memory store."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any

from neo4j import AsyncGraphDatabase

from backend.config import settings
from backend.memory.interfaces import RetrievedContext

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _embedding(text: str, *, dims: int = 64) -> list[float]:
    values = [0.0] * dims
    for token in _tokenize(text):
        values[hash(token) % dims] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 6) for value in values]


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


class Neo4jSemanticMemoryStore:
    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str,
        connect_timeout_s: float,
    ) -> None:
        self.uri = uri
        self.database = database
        self.driver = AsyncGraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=connect_timeout_s,
        )

    async def connect(self) -> None:
        await self.driver.verify_connectivity()
        async with self.driver.session(database=self.database) as session:
            await session.run(
                """
                CREATE CONSTRAINT semantic_memory_artifact_id IF NOT EXISTS
                FOR (m:MemoryArtifact) REQUIRE m.id IS UNIQUE
                """
            )

    async def close(self) -> None:
        await self.driver.close()

    async def healthy(self) -> bool:
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    async def upsert_artifact(self, artifact: dict[str, Any]) -> None:
        async with self.driver.session(database=self.database) as session:
            await session.execute_write(
                self._upsert_artifact_tx,
                artifact,
                _embedding(artifact["content"]),
            )

    async def invalidate_fact(
        self, canonical_key: str, replacement_artifact_id: int | None = None
    ) -> None:
        async with self.driver.session(database=self.database) as session:
            await session.run(
                """
                MATCH (m:MemoryArtifact {canonical_key: $canonical_key})
                WHERE m.valid_to IS NULL
                SET m.valid_to = datetime(),
                    m.status = 'superseded',
                    m.replacement_artifact_id = $replacement_artifact_id
                """,
                canonical_key=canonical_key,
                replacement_artifact_id=replacement_artifact_id,
            )

    async def retrieve(
        self,
        *,
        session_id: str,
        persona_id: str,
        query: str,
        limit: int = 8,
    ) -> RetrievedContext:
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (m:MemoryArtifact)
                WHERE m.valid_to IS NULL OR m.valid_to = ''
                RETURN m.content AS content,
                       m.artifact_type AS artifact_type,
                       m.confidence AS confidence,
                       m.session_id AS session_id
                LIMIT 200
                """
            )
            records = [record async for record in result]
        ranked = sorted(
            (
                {
                    "content": record["content"],
                    "artifact_type": record["artifact_type"],
                    "confidence": float(record["confidence"] or 0.0),
                    "score": _score(query, record["content"] or ""),
                }
                for record in records
                if record["content"]
            ),
            key=lambda item: (item["score"], item["confidence"]),
            reverse=True,
        )
        semantic_memories = [item["content"] for item in ranked[:limit]]
        facts = [item["content"] for item in ranked if item["artifact_type"] == "fact"][:limit]
        return RetrievedContext(
            semantic_memories=semantic_memories,
            facts=facts,
            metadata={
                "source": "neo4j",
                "persona_id": persona_id,
                "session_id": session_id,
            },
        )

    @staticmethod
    async def _upsert_artifact_tx(tx, artifact: dict[str, Any], embedding: list[float]) -> None:
        await tx.run(
            """
            MERGE (m:MemoryArtifact {id: $id})
            SET m.session_id = $session_id,
                m.artifact_type = $artifact_type,
                m.content = $content,
                m.canonical_key = $canonical_key,
                m.confidence = $confidence,
                m.valid_from = $valid_from,
                m.valid_to = $valid_to,
                m.embedding = $embedding,
                m.updated_at = datetime()
            WITH m
            FOREACH (_ IN CASE WHEN $session_id IS NULL THEN [] ELSE [1] END |
                MERGE (s:Session {id: $session_id})
                MERGE (m)-[:MENTIONED_IN]->(s)
            )
            """,
            id=artifact["id"],
            session_id=artifact.get("session_id"),
            artifact_type=artifact["artifact_type"],
            content=artifact["content"],
            canonical_key=artifact.get("canonical_key"),
            confidence=float(artifact.get("confidence", 0.5)),
            valid_from=artifact.get("valid_from"),
            valid_to=artifact.get("valid_to"),
            embedding=embedding,
        )


async def create_semantic_memory_store() -> Neo4jSemanticMemoryStore | None:
    if not settings.SEMANTIC_MEMORY_ENABLED:
        return None

    store = Neo4jSemanticMemoryStore(
        uri=settings.NEO4J_URI,
        username=settings.NEO4J_USERNAME,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
        connect_timeout_s=settings.NEO4J_CONNECT_TIMEOUT_S,
    )
    try:
        await store.connect()
    except Exception:
        logger.warning("neo4j semantic memory unavailable; continuing without it", exc_info=True)
        await store.close()
        return None
    return store
