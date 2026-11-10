"""Pipeline state machine: turns, streaming, barge-in, history windowing."""

import asyncio

import numpy as np

from tests.conftest import FakeLLM, FakeSTT


async def _wait_for_turn(pipeline):
    assert pipeline._turn_task is not None
    await pipeline._turn_task


async def test_text_turn_full_cycle(make_pipeline, collector, db):
    pipeline = make_pipeline()
    await pipeline.set_session(None)

    await pipeline.handle_text("I feel stuck lately.")
    await _wait_for_turn(pipeline)

    # Streaming deltas arrived, final text assembled, audio sent per sentence
    deltas = collector.events("assistant_delta")
    assert "".join(d["text"] for d in deltas) == "This is the answer. And a second sentence."
    assert collector.events("assistant_done")[0]["text"].endswith("second sentence.")
    assert len(collector.audio) == 2

    # Both sides persisted
    messages = await db.get_messages(pipeline.session_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]

    # Ends back in listening
    assert collector.events("state")[-1]["state"] == "listening"


async def test_voice_turn_transcribes_first(make_pipeline, collector, db):
    pipeline = make_pipeline(stt=FakeSTT("what should i do about my job"))
    await pipeline.set_session(None)

    pipeline._start_turn(audio=np.zeros(16000, dtype=np.float32))
    await _wait_for_turn(pipeline)

    assert collector.events("user_transcript")[0]["text"] == "what should i do about my job"
    messages = await db.get_messages(pipeline.session_id)
    assert messages[0]["content"] == "what should i do about my job"


async def test_detected_language_routes_to_tts(make_pipeline, collector, db):
    """Tamil STT result must reach the TTS router as language='ta'."""
    from tests.conftest import FakeTTS

    tts = FakeTTS()
    pipeline = make_pipeline(stt=FakeSTT("வணக்கம்", language="ta"), tts=tts)
    await pipeline.set_session(None)

    pipeline._start_turn(audio=np.zeros(16000, dtype=np.float32))
    await _wait_for_turn(pipeline)

    assert collector.events("user_transcript")[0]["language"] == "ta"
    assert tts.calls, "TTS should have been called"
    assert all(lang == "ta" for _, lang in tts.calls)


async def test_text_turn_defaults_to_english(make_pipeline, db):
    """Typed turns have no STT, so TTS should route to English."""
    from tests.conftest import FakeTTS

    tts = FakeTTS()
    pipeline = make_pipeline(tts=tts)
    await pipeline.set_session(None)

    await pipeline.handle_text("hello")
    await _wait_for_turn(pipeline)

    assert all(lang == "en" for _, lang in tts.calls)


async def test_empty_transcript_returns_to_listening(make_pipeline, collector, db):
    pipeline = make_pipeline(stt=FakeSTT(""))
    await pipeline.set_session(None)

    pipeline._start_turn(audio=np.zeros(16000, dtype=np.float32))
    await _wait_for_turn(pipeline)

    assert collector.events("user_transcript") == []
    assert await db.get_messages(pipeline.session_id) == []
    assert collector.events("state")[-1]["state"] == "listening"


async def test_barge_in_cancels_and_persists_partial(make_pipeline, collector, db):
    pipeline = make_pipeline(llm=FakeLLM(deltas=["Partial thought that never ends "], hang=True))
    await pipeline.set_session(None)

    await pipeline.handle_text("first message")
    # Let the LLM emit its delta, then interrupt
    for _ in range(50):
        await asyncio.sleep(0.01)
        if collector.events("assistant_delta"):
            break
    await pipeline._barge_in()

    assert collector.events("interrupted")
    messages = await db.get_messages(pipeline.session_id)
    assert messages[-1]["role"] == "assistant"
    assert "Partial thought" in messages[-1]["content"]


async def test_set_session_resumes_existing(make_pipeline, db):
    pipeline = make_pipeline()
    first = await pipeline.set_session(None)
    await db.add_message(first, "user", "earlier message")

    resumed = await pipeline.set_session(first)
    assert resumed == first

    fresh = await pipeline.set_session("nonexistent-id")
    assert fresh != first


async def test_history_windowing_keeps_recent(make_pipeline, db):
    pipeline = make_pipeline()
    await pipeline.set_session(None)
    pipeline.context_tokens = 500  # tiny budget: (500-400)*4 - prompt ≈ 380 chars

    for i in range(10):
        await db.add_message(pipeline.session_id, "user", f"message {i} " + "x" * 100)

    messages = await pipeline._windowed_messages()
    assert messages[0]["role"] == "system"
    history = messages[1:]
    assert 0 < len(history) < 10
    assert history[-1]["content"].startswith("message 9")  # newest kept


async def test_llm_failure_reports_error_and_recovers(make_pipeline, collector):
    class BrokenLLM(FakeLLM):
        async def stream_chat(self, messages):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

    pipeline = make_pipeline(llm=BrokenLLM())
    await pipeline.set_session(None)
    await pipeline.handle_text("hello")
    await _wait_for_turn(pipeline)

    errors = collector.events("error")
    assert errors and "wrong" in errors[0]["message"]
    assert collector.events("state")[-1]["state"] == "listening"


async def test_muted_drops_audio(make_pipeline):
    pipeline = make_pipeline()
    await pipeline.set_session(None)
    pipeline.muted = True
    await pipeline.handle_audio(b"\x00\x00" * 512)
    assert pipeline._turn_task is None
