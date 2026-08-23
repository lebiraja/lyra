"""Contracts for conversation storage and future memory services.

Phase 0 goal: separate the pipeline from concrete storage implementation
details without changing runtime behavior yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConversationStore(Protocol):
    async def create_session(self, persona: str = "medusa") -> str: ...
    async def session_exists(self, session_id: str) -> bool: ...
    async def get_session_persona(self, session_id: str) -> str | None: ...
    async def list_sessions(self) -> list[dict[str, Any]]: ...
    async def delete_session(self, session_id: str) -> bool: ...
    async def record_event(
        self,
        session_id: str,
        event_type: str,
        *,
        role: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int: ...
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
    async def get_messages(self, session_id: str) -> list[dict[str, Any]]: ...
    async def get_events(self, session_id: str) -> list[dict[str, Any]]: ...
    async def save_memory_artifact(
        self,
        *,
        session_id: str,
        artifact_type: str,
        content: str,
        canonical_key: str | None = None,
        confidence: float = 0.5,
        provenance_event_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        status: str = "active",
    ) -> int: ...
    async def list_memory_artifacts(
        self,
        *,
        session_id: str | None = None,
        artifact_type: str | None = None,
        only_active: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...
    async def invalidate_memory_artifacts(
        self,
        *,
        canonical_key: str,
        replacement_artifact_id: int | None = None,
        invalidated_at: str | None = None,
        exclude_artifact_id: int | None = None,
    ) -> None: ...


@runtime_checkable
class MemoryStore(Protocol):
    async def save_memory(
        self, persona: str, session_id: str | None, summary: str
    ) -> None: ...
    async def get_memories(self, persona: str, limit: int = 12) -> list[str]: ...
    async def has_memory_for_session(self, session_id: str) -> bool: ...


@runtime_checkable
class ConversationMemoryStore(ConversationStore, MemoryStore, Protocol):
    """Current combined storage contract used by the pipeline."""


@runtime_checkable
class SemanticGraphStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def healthy(self) -> bool: ...
    async def upsert_artifact(self, artifact: dict[str, Any]) -> None: ...
    async def invalidate_fact(
        self, canonical_key: str, replacement_artifact_id: int | None = None
    ) -> None: ...
    async def retrieve(
        self,
        *,
        session_id: str,
        persona_id: str,
        query: str,
        limit: int = 8,
    ) -> RetrievedContext: ...


@dataclass(slots=True)
class RetrievedContext:
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    semantic_memories: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryExtractor(Protocol):
    async def extract_from_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class MemoryRetriever(Protocol):
    async def retrieve(
        self,
        *,
        session_id: str,
        persona_id: str,
        query: str,
        limit: int = 12,
    ) -> RetrievedContext: ...


class MemoryConsolidator(Protocol):
    async def consolidate_session(self, session_id: str) -> None: ...


class ContextAssembler(Protocol):
    async def assemble(
        self,
        *,
        session_id: str,
        persona_id: str,
        system_prompt: str,
        query: str | None = None,
        budget_tokens: int,
        emotion_state: Any | None = None,
        emotion_confidence_threshold: float = 0.3,
    ) -> list[dict[str, str]]: ...
