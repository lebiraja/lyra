"""Pipeline integration tests with emotion detection (parallel forks, fusion, prompt injection)."""

import asyncio
import numpy as np
import pytest

from backend.core.emotion import EmotionBuffer, EmotionState
from tests.conftest import FakeLLM, FakeSTT, FakeTurnDetector


class FakeSER:
    def __init__(self, label: str = "angry", confidence: float = 0.8):
        self.label = label
        self.confidence = confidence
        self.call_count = 0

    def predict(self, audio, sample_rate: int = 16000) -> EmotionState:
        self.call_count += 1
        return EmotionState(
            label=self.label,
            confidence=self.confidence,
            valence=-0.6,
            arousal=0.8,
            source="voice",
        )


async def test_pipeline_runs_ser_parallel_and_injects_prompt(make_pipeline, collector, db):
    # Setup SER returning angry.
    ser = FakeSER(label="angry", confidence=0.85)
    fer_buffer = EmotionBuffer()
    # Setup FER buffer with happy.
    fer_buffer.push(EmotionState("happy", 0.7, 0.8, 0.6, "face"))

    # When make_pipeline is called, it builds a ConversationPipeline without emotion params.
    # We will build it with customized args using make_pipeline's base components.
    pipeline = make_pipeline()
    pipeline.ser = ser
    pipeline.fer_buffer = fer_buffer
    # Set threshold low enough to trigger injection
    pipeline.ser_confidence_threshold = 0.3

    await pipeline.set_session(None)

    # Trigger a voice turn
    pipeline._start_turn(audio=np.zeros(16000, dtype=np.float32))
    assert pipeline._turn_task is not None
    await pipeline._turn_task

    # Verify SER was called
    assert ser.call_count == 1

    # Verify the fused emotion event was sent to the client
    emotion_events = collector.events("emotion")
    assert len(emotion_events) == 1
    assert emotion_events[0]["label"] == "angry"  # Ser confidence (0.85) > Fer confidence (0.7)
    assert emotion_events[0]["source"] == "fused"

    # Verify prompt injection
    # LLM should have seen the system prompt modified with emotion context.
    # Let's inspect the messages passed to the LLM client by spying on LLM stream_chat.
    # First let's check what was saved in the db (history shouldn't contain the system emotion context)
    messages = await db.get_messages(pipeline.session_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

    # Now verify the dynamic context compilation
    windowed = await pipeline._windowed_messages()
    assert len(windowed) == 4  # System prompt, Emotion Context system prompt, User, Assistant (greeting/none)
    assert windowed[0]["role"] == "system"
    assert "You are a test mentor" in windowed[0]["content"]

    assert windowed[1]["role"] == "system"
    assert "[Current User State]" in windowed[1]["content"]
    assert "angry" in windowed[1]["content"]
    assert "concise and direct" in windowed[1]["content"]


async def test_pipeline_skips_ser_on_short_utterance(make_pipeline, collector):
    ser = FakeSER()
    pipeline = make_pipeline()
    pipeline.ser = ser
    pipeline.ser_min_audio_s = 1.5  # require 1.5s
    await pipeline.set_session(None)

    # 1.0s of audio @ 16kHz
    short_audio = np.zeros(16000, dtype=np.float32)
    pipeline._start_turn(audio=short_audio)
    await pipeline._turn_task

    # SER should be skipped entirely
    assert ser.call_count == 0


async def test_pipeline_graceful_degradation_without_models(make_pipeline, collector):
    # Pipeline initialized with ser=None, fer_buffer=None should run normally without emotion events
    pipeline = make_pipeline()
    pipeline.ser = None
    pipeline.fer_buffer = None
    await pipeline.set_session(None)

    pipeline._start_turn(audio=np.zeros(16000, dtype=np.float32))
    await pipeline._turn_task

    assert len(collector.events("emotion")) == 0
    windowed = await pipeline._windowed_messages()
    # Should only have the normal system prompt plus persisted history, with no extra emotion prompt.
    assert len(windowed) == 3
    assert windowed[0]["role"] == "system"
    assert "Current User State" not in windowed[0]["content"]
