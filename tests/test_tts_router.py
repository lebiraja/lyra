"""Unit tests for TTSRouter — language routing + resampling. No GPU needed."""

import numpy as np
import pytest

from backend.core.tts import TTSRouter, _resample


class FakeTTS:
    """Minimal TTS stand-in that produces a known sine wave."""

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.last_text: str | None = None

    def synthesize(self, text: str) -> tuple[bytes, int]:
        self.last_text = text
        if not text.strip():
            return b"", self.sample_rate
        t = np.linspace(0, 0.1, int(self.sample_rate * 0.1), endpoint=False)
        samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        return samples.tobytes(), self.sample_rate


@pytest.fixture
def fake_en():
    return FakeTTS(sample_rate=24000)


@pytest.fixture
def fake_ta():
    return FakeTTS(sample_rate=22050)


@pytest.fixture
def router(fake_en, fake_ta):
    return TTSRouter(kokoro=fake_en, piper_tamil=fake_ta)


def test_routes_english_to_kokoro(router, fake_en):
    pcm = router.synthesize("Hello world", language="en")
    assert fake_en.last_text == "Hello world"
    assert len(pcm) > 0


def test_routes_tamil_to_piper(router, fake_ta):
    pcm = router.synthesize("வணக்கம்", language="ta")
    assert fake_ta.last_text == "வணக்கம்"
    assert len(pcm) > 0


def test_unknown_language_falls_back_to_english(router, fake_en):
    router.synthesize("Bonjour", language="fr")
    assert fake_en.last_text == "Bonjour"


def test_tamil_without_piper_falls_back_to_english(fake_en):
    router = TTSRouter(kokoro=fake_en, piper_tamil=None)
    router.synthesize("வணக்கம்", language="ta")
    assert fake_en.last_text == "வணக்கம்"


def test_resample_changes_length():
    sr_from, sr_to = 22050, 24000
    duration_s = 0.5
    n_in = int(sr_from * duration_s)
    samples_in = (np.sin(np.linspace(0, 10, n_in)) * 16000).astype(np.int16)
    pcm_out = _resample(samples_in.tobytes(), sr_from, sr_to)
    n_out = len(pcm_out) // 2
    expected = int(n_in * sr_to / sr_from)
    assert abs(n_out - expected) <= 1


def test_empty_text_returns_empty(router):
    pcm = router.synthesize("", language="en")
    assert pcm == b""

    pcm = router.synthesize("  ", language="ta")
    assert pcm == b""


def test_resample_empty_and_tiny_input_no_crash():
    assert _resample(b"", 22050, 24000) == b""
    one = (np.int16(123)).tobytes()
    assert _resample(one, 22050, 24000) == one  # <2 samples: returned as-is


def test_resample_same_rate_is_noop():
    pcm = (np.arange(100, dtype=np.int16)).tobytes()
    assert _resample(pcm, 24000, 24000) == pcm
