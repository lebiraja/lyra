"""Shadow-mode memory extraction and promotion helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from backend.memory.interfaces import ConversationMemoryStore, SemanticGraphStore

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip())


def _slug(text: str) -> str:
    return "-".join(_TOKEN_RE.findall(text.lower()))[:80]


def _sentence_candidates(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]


@dataclass(slots=True)
class ExtractedArtifact:
    artifact_type: str
    content: str
    canonical_key: str | None
    confidence: float
    metadata: dict[str, Any]
    supersedes: bool = False


class ShadowMemoryExtractor:
    """Heuristic extractor used in shadow mode before full model-based extraction."""

    def __init__(
        self,
        store: ConversationMemoryStore,
        graph_store: SemanticGraphStore | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self.store = store
        self.graph_store = graph_store
        self.enabled = enabled

    async def extract_from_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return

        source_metadata = metadata or {}
        artifacts = self._extract_candidates(user_text)
        if not artifacts:
            return

        for artifact in artifacts:
            artifact_id = await self.store.save_memory_artifact(
                session_id=session_id,
                artifact_type=artifact.artifact_type,
                content=artifact.content,
                canonical_key=artifact.canonical_key,
                confidence=artifact.confidence,
                provenance_event_id=source_metadata.get("user_event_id"),
                metadata={
                    **artifact.metadata,
                    "assistant_text": assistant_text,
                },
            )
            if artifact.supersedes and artifact.canonical_key:
                await self.store.invalidate_memory_artifacts(
                    canonical_key=artifact.canonical_key,
                    replacement_artifact_id=artifact_id,
                    exclude_artifact_id=artifact_id,
                )

            if self.graph_store is not None:
                record = {
                    "id": artifact_id,
                    "session_id": session_id,
                    "artifact_type": artifact.artifact_type,
                    "content": artifact.content,
                    "canonical_key": artifact.canonical_key,
                    "confidence": artifact.confidence,
                    "valid_from": source_metadata.get("created_at"),
                    "metadata": artifact.metadata,
                }
                try:
                    await self.graph_store.upsert_artifact(record)
                except Exception:
                    logger.warning("graph upsert failed for artifact %s", artifact_id, exc_info=True)

    def _extract_candidates(self, user_text: str) -> list[ExtractedArtifact]:
        artifacts: list[ExtractedArtifact] = []
        for sentence in _sentence_candidates(user_text):
            lowered = sentence.lower()

            preference_match = re.search(
                r"\b(?:i like|i love|i enjoy|i prefer)\s+(.+)$", sentence, re.IGNORECASE
            )
            if preference_match:
                value = _normalize(preference_match.group(1))
                artifacts.append(
                    ExtractedArtifact(
                        artifact_type="preference",
                        content=value,
                        canonical_key=f"preference:{_slug(value)}",
                        confidence=0.72,
                        metadata={"source_pattern": "preference"},
                    )
                )

            goal_match = re.search(
                r"\b(?:i want to|i need to|i plan to|i am trying to|i'm trying to)\s+(.+)$",
                sentence,
                re.IGNORECASE,
            )
            if goal_match:
                value = _normalize(goal_match.group(1))
                artifacts.append(
                    ExtractedArtifact(
                        artifact_type="goal",
                        content=value,
                        canonical_key=f"goal:{_slug(value)}",
                        confidence=0.78,
                        metadata={"source_pattern": "goal"},
                    )
                )

            employment_match = re.search(
                r"\b(?:i work at|i work for)\s+(.+)$", sentence, re.IGNORECASE
            )
            if employment_match:
                value = _normalize(employment_match.group(1))
                artifacts.append(
                    ExtractedArtifact(
                        artifact_type="fact",
                        content=f"works at {value}",
                        canonical_key="fact:employment",
                        confidence=0.82,
                        metadata={"source_pattern": "employment", "value": value},
                        supersedes=True,
                    )
                )

            location_match = re.search(
                r"\b(?:i live in|i'm from|i am from)\s+(.+)$", sentence, re.IGNORECASE
            )
            if location_match:
                value = _normalize(location_match.group(1))
                artifacts.append(
                    ExtractedArtifact(
                        artifact_type="fact",
                        content=f"location {value}",
                        canonical_key="fact:location",
                        confidence=0.8,
                        metadata={"source_pattern": "location", "value": value},
                        supersedes=True,
                    )
                )

            if "because" in lowered or "struggling" in lowered or "stuck" in lowered:
                artifacts.append(
                    ExtractedArtifact(
                        artifact_type="reflection",
                        content=_normalize(sentence),
                        canonical_key=None,
                        confidence=0.58,
                        metadata={"source_pattern": "reflection"},
                    )
                )

        return artifacts
