"""Shared fixtures — fake engines so protocol/pipeline tests run without models."""

import asyncio
from pathlib import Path

import numpy as np
import pytest

from backend.core.pipeline import ConversationPipeline, LatencyStats
from backend.core.stt import STTResult
from backend.db import Database


class FakeSTT:
    def __init__(self, text: str = "hello there", language: str = "en"):
        self.text = text
        self.language = language

    def transcribe(self, audio, sample_rate: int = 16000) -> STTResult:
        return STTResult(
            text=self.text, language=self.language, language_probability=0.99
        )


class FakeTTS:
    """Mimics TTSRouter.synthesize(text, language) -> bytes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, text: str, language: str = "en") -> bytes:
        self.calls.append((text, language))
        # 10 ms of silence per sentence — enough to assert on
        return b"\x00\x00" * 240


class FakeLLM:
    """Streams a canned reply, optionally hanging forever (for barge-in tests)."""

    def __init__(self, deltas=None, hang: bool = False):
        self.deltas = deltas or ["This is the answer. ", "And a second sentence."]
        self.hang = hang
        self.max_tokens = 400

    async def stream_chat(self, messages):
        for d in self.deltas:
            yield d
        if self.hang:
            await asyncio.Event().wait()

    async def healthy(self) -> bool:
        return True


class FakeTurnDetector:
    """Emits a queued utterance whenever process() is called; counts resets."""

    def __init__(self):
        from backend.core.vad import TurnEvent

        self._TurnEvent = TurnEvent
        self.pending: list = []  # list of utterance audio arrays to emit
        self.resets = 0

    def queue_utterance(self, audio):
        self.pending.append(audio)

    def process(self, pcm):
        if self.pending:
            audio = self.pending.pop(0)
            return [self._TurnEvent("utterance", audio=audio)]
        return []

    def reset(self):
        self.resets += 1
        self.pending.clear()


# A tiny in-memory persona registry so pipeline tests don't depend on config files.
from backend.core.personas import Persona  # noqa: E402


class FakePersonaRegistry:
    def __init__(self, personas: dict[str, Persona] | None = None):
        self._personas = personas or {
            "clarity": Persona(
                id="clarity", name="Clarity", tagline="mentor", voice="af_heart",
                proactive=False, cross_session_memory=False,
                system_prompt="You are a test mentor.",
            ),
            "medusa": Persona(
                id="medusa", name="Medusa", tagline="the friend to share all the things", voice="af_heart",
                proactive=True, cross_session_memory=True,
                system_prompt="You are Medusa, the friend to share all the things. What you remember:\n{memory}",
            ),
        }

    def get(self, persona_id):
        return self._personas.get(persona_id or "", self._personas["clarity"])

    def exists(self, persona_id):
        return persona_id in self._personas

    def list(self):
        return [{"id": p.id, "name": p.name, "tagline": p.tagline} for p in self._personas.values()]


class Collector:
    """Captures everything the pipeline sends to the 'client'."""

    def __init__(self):
        self.json: list[dict] = []
        self.audio: list[bytes] = []

    async def send_json(self, msg):
        self.json.append(msg)

    async def send_bytes(self, data):
        self.audio.append(data)

    def events(self, type_: str) -> list[dict]:
        return [m for m in self.json if m["type"] == type_]


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def collector():
    return Collector()


@pytest.fixture
def personas():
    return FakePersonaRegistry()


@pytest.fixture
def make_pipeline(db, collector, personas):
    def _make(
        llm=None,
        stt=None,
        tts=None,
        registry=None,
        turn_detector=None,
        **kwargs,
    ) -> ConversationPipeline:
        return ConversationPipeline(
            stt=stt or FakeSTT(),
            tts=tts or FakeTTS(),
            llm=llm or FakeLLM(),
            turn_detector=turn_detector or FakeTurnDetector(),
            db=db,
            personas=registry or personas,
            context_tokens=8192,
            send_json=collector.send_json,
            send_bytes=collector.send_bytes,
            stats=LatencyStats(),
            **kwargs,
        )

    return _make
