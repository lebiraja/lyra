"""SQLite persistence."""

from backend.memory.interfaces import ConversationMemoryStore


async def test_session_lifecycle(db):
    sid = await db.create_session()
    assert await db.session_exists(sid)

    await db.add_message(sid, "user", "I keep procrastinating on everything")
    await db.add_message(sid, "assistant", "Let's look at that honestly.")

    sessions = await db.list_sessions()
    assert sessions[0]["id"] == sid
    assert sessions[0]["message_count"] == 2
    # First user message becomes the title
    assert sessions[0]["title"].startswith("I keep procrastinating")

    messages = await db.get_messages(sid)
    assert [m["role"] for m in messages] == ["user", "assistant"]

    events = await db.get_events(sid)
    assert [e["event_type"] for e in events] == ["message", "message"]
    assert [e["role"] for e in events] == ["user", "assistant"]

    assert await db.delete_session(sid)
    assert not await db.session_exists(sid)
    assert await db.get_messages(sid) == []
    assert await db.get_events(sid) == []


async def test_delete_missing_returns_false(db):
    assert not await db.delete_session("nope")


async def test_database_satisfies_phase_zero_storage_contract(db):
    assert isinstance(db, ConversationMemoryStore)
