"""Tests for the human-like memory architecture seams."""

from backend.memory.context_assembler import HybridContextAssembler
from backend.memory.extractor import ShadowMemoryExtractor
from backend.memory.retriever import HybridMemoryRetriever


async def test_shadow_extractor_promotes_and_invalidates_temporal_facts(db):
    session_id = await db.create_session()
    extractor = ShadowMemoryExtractor(db)

    await extractor.extract_from_turn(
        session_id=session_id,
        user_text="I work at Acme. I want to sleep earlier. I love jazz.",
        assistant_text="Noted.",
    )
    await extractor.extract_from_turn(
        session_id=session_id,
        user_text="I work at Beta Labs now.",
        assistant_text="Understood.",
    )

    artifacts = await db.list_memory_artifacts(limit=20)
    active = await db.list_memory_artifacts(only_active=True, limit=20)

    employment = [item for item in artifacts if item["canonical_key"] == "fact:employment"]
    assert len(employment) == 2
    assert any(item["status"] == "superseded" for item in employment)
    assert any(item["content"] == "works at Beta Labs now" for item in active)


async def test_hybrid_context_assembler_injects_semantic_memory(db):
    session_id = await db.create_session()
    await db.add_message(session_id, "user", "Earlier message")
    await db.add_message(session_id, "assistant", "Earlier reply")
    await db.save_memory_artifact(
        session_id=session_id,
        artifact_type="fact",
        content="works at Beta Labs",
        canonical_key="fact:employment",
        confidence=0.9,
    )

    retriever = HybridMemoryRetriever(db, recent_message_limit=4, semantic_limit=4)
    assembler = HybridContextAssembler(db, retriever, llm_max_tokens=400)
    messages = await assembler.assemble(
        session_id=session_id,
        persona_id="medusa",
        system_prompt="You are a mentor.",
        query="Where do I work?",
        budget_tokens=8192,
    )

    memory_messages = [msg for msg in messages if "Relevant memory for continuity" in msg["content"]]
    assert memory_messages
    assert "works at Beta Labs" in memory_messages[0]["content"]


async def test_pipeline_records_structured_events(make_pipeline, db):
    pipeline = make_pipeline(memory_extractor=ShadowMemoryExtractor(db))
    await pipeline.set_session(None)

    await pipeline.handle_text("I work at Acme and I want to get better at focus.")
    assert pipeline._turn_task is not None
    await pipeline._turn_task

    events = await db.get_events(pipeline.session_id)
    event_types = [event["event_type"] for event in events]

    assert "session_created" in event_types
    assert "persona_selected" in event_types
    assert "turn_started" in event_types
    assert "user_transcript" in event_types
    assert "assistant_done" in event_types
    assert "state_transition" in event_types

    artifacts = await db.list_memory_artifacts(session_id=pipeline.session_id, limit=20)
    assert artifacts
