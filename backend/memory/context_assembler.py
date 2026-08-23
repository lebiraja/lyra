"""Current-generation context assembly.

This preserves today's behavior: system prompt + optional emotion prompt +
recent chronological messages fitted into the token budget.
"""

from __future__ import annotations

from backend.core.emotion import EmotionState, emotion_context
from backend.memory.interfaces import (
    ContextAssembler,
    ConversationMemoryStore,
    MemoryRetriever,
)


class HistoryContextAssembler(ContextAssembler):
    def __init__(self, store: ConversationMemoryStore, llm_max_tokens: int) -> None:
        self.store = store
        self.llm_max_tokens = llm_max_tokens

    async def assemble(
        self,
        *,
        session_id: str,
        persona_id: str,
        system_prompt: str,
        query: str | None = None,
        budget_tokens: int,
        emotion_state: EmotionState | None = None,
        emotion_confidence_threshold: float = 0.3,
    ) -> list[dict[str, str]]:
        emotion_fragment = emotion_context(
            emotion_state or EmotionState(),
            emotion_confidence_threshold,
        )

        budget_chars = (budget_tokens - self.llm_max_tokens) * 4
        budget_chars -= len(system_prompt)
        budget_chars -= len(emotion_fragment)

        history = await self.store.get_messages(session_id)
        kept: list[dict[str, str]] = []
        used = 0
        for msg in reversed(history):
            cost = len(msg["content"])
            if used + cost > budget_chars and kept:
                break
            kept.append({"role": msg["role"], "content": msg["content"]})
            used += cost
        kept.reverse()

        messages = [{"role": "system", "content": system_prompt}]
        if emotion_fragment:
            messages.append({"role": "system", "content": emotion_fragment})
        messages.extend(kept)
        return messages


class HybridContextAssembler(ContextAssembler):
    """Prompt assembly with recent history plus structured semantic memory."""

    def __init__(
        self,
        store: ConversationMemoryStore,
        retriever: MemoryRetriever,
        llm_max_tokens: int,
        *,
        semantic_char_budget: int = 1200,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.llm_max_tokens = llm_max_tokens
        self.semantic_char_budget = semantic_char_budget

    async def assemble(
        self,
        *,
        session_id: str,
        persona_id: str,
        system_prompt: str,
        query: str | None = None,
        budget_tokens: int,
        emotion_state: EmotionState | None = None,
        emotion_confidence_threshold: float = 0.3,
    ) -> list[dict[str, str]]:
        emotion_fragment = emotion_context(
            emotion_state or EmotionState(),
            emotion_confidence_threshold,
        )
        retrieval = await self.retriever.retrieve(
            session_id=session_id,
            persona_id=persona_id,
            query=query or "",
        )

        memory_lines: list[str] = []
        if retrieval.facts:
            memory_lines.append("Active facts:")
            memory_lines.extend(f"- {fact}" for fact in retrieval.facts[:6])
        if retrieval.semantic_memories:
            memory_lines.append("Relevant long-term memory:")
            memory_lines.extend(f"- {item}" for item in retrieval.semantic_memories[:6])
        memory_block = "\n".join(memory_lines).strip()
        if len(memory_block) > self.semantic_char_budget:
            memory_block = memory_block[: self.semantic_char_budget].rsplit("\n", 1)[0]

        budget_chars = (budget_tokens - self.llm_max_tokens) * 4
        budget_chars -= len(system_prompt)
        budget_chars -= len(emotion_fragment)
        budget_chars -= len(memory_block)

        kept: list[dict[str, str]] = []
        used = 0
        for msg in reversed(retrieval.recent_messages):
            cost = len(msg["content"])
            if used + cost > budget_chars and kept:
                break
            kept.append({"role": msg["role"], "content": msg["content"]})
            used += cost
        kept.reverse()

        messages = [{"role": "system", "content": system_prompt}]
        if emotion_fragment:
            messages.append({"role": "system", "content": emotion_fragment})
        if memory_block:
            messages.append(
                {
                    "role": "system",
                    "content": "Relevant memory for continuity:\n" + memory_block,
                }
            )
        messages.extend(kept)
        return messages
