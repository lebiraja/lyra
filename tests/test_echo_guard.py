"""Half-duplex echo guard — the fix for the bot hearing itself and looping."""

import time

import numpy as np

from tests.conftest import FakeLLM, FakeTurnDetector


def _frames(n: int = 1024) -> bytes:
    return (np.zeros(n, dtype=np.int16)).tobytes()


async def _drain(pipeline):
    if pipeline._turn_task:
        await pipeline._turn_task


async def test_mic_ignored_while_busy(make_pipeline):
    """Audio arriving while the assistant is busy must not start a new turn."""
    td = FakeTurnDetector()
    pipeline = make_pipeline(turn_detector=td)
    await pipeline.set_session(None)

    pipeline._busy = True  # pretend the assistant is speaking
    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())

    # The queued "utterance" (echo) must be discarded, not transcribed.
    assert pipeline._turn_task is None
    assert td.resets > 0  # detector was reset to drop echo frames


async def test_mic_ignored_during_echo_tail(make_pipeline):
    td = FakeTurnDetector()
    pipeline = make_pipeline(turn_detector=td)
    await pipeline.set_session(None)

    pipeline._busy = False
    pipeline._echo_guard_until = time.monotonic() + 5  # tail still open
    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())

    assert pipeline._turn_task is None


async def test_mic_accepted_after_guard_clears(make_pipeline):
    td = FakeTurnDetector()
    pipeline = make_pipeline(turn_detector=td)
    await pipeline.set_session(None)

    pipeline._busy = False
    pipeline._echo_guard_until = time.monotonic() - 1  # guard already expired
    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())

    # Now a real turn starts.
    assert pipeline._turn_task is not None
    await _drain(pipeline)


async def test_turn_sets_busy_then_opens_guard(make_pipeline):
    td = FakeTurnDetector()
    pipeline = make_pipeline(llm=FakeLLM(deltas=["Hello there."]), turn_detector=td)
    await pipeline.set_session(None)

    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())
    assert pipeline._busy is True  # set synchronously when the turn starts

    await _drain(pipeline)
    assert pipeline._busy is False
    assert pipeline._echo_guard_until > time.monotonic()  # tail opened


async def test_guard_extends_past_audio_playback(make_pipeline):
    """The guard must outlast the queued TTS audio, not just when it was sent."""
    from tests.conftest import FakeTTS

    class LongTTS(FakeTTS):
        def synthesize(self, text, language="en"):
            return b"\x00\x00" * 24000  # 1 second of 24kHz audio

    td = FakeTurnDetector()
    pipeline = make_pipeline(
        llm=FakeLLM(deltas=["One sentence here. Another one too."]),
        tts=LongTTS(),
        turn_detector=td,
    )
    await pipeline.set_session(None)

    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())
    await _drain(pipeline)

    # Two 1s chunks were "sent" instantly; the guard should reach ~2s into the future.
    remaining = pipeline._echo_guard_until - time.monotonic()
    assert remaining > 1.5


async def test_barge_in_mode_listens_during_speech(make_pipeline):
    """With barge-in enabled (headphones), the mic is NOT gated while busy."""
    td = FakeTurnDetector()
    pipeline = make_pipeline(turn_detector=td)
    pipeline.allow_barge_in = True
    await pipeline.set_session(None)

    pipeline._busy = True
    td.queue_utterance(np.zeros(16000, dtype=np.float32))
    await pipeline.handle_audio(_frames())

    assert pipeline._turn_task is not None  # a new turn was allowed to start
    await _drain(pipeline)
