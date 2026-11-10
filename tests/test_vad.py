"""TurnDetector endpoint logic, driven by a scripted VAD (no model needed)."""

import numpy as np

from backend.core.vad import FRAME_SAMPLES, TurnDetector


class ScriptedVAD:
    """Returns a queued list of probabilities, then silence."""

    def __init__(self, probs):
        self.probs = list(probs)

    def reset(self):
        pass

    def prob(self, frame):
        return self.probs.pop(0) if self.probs else 0.0


def frames(n: int) -> np.ndarray:
    return np.zeros(FRAME_SAMPLES * n, dtype=np.float32)


def make_detector(probs, **kw) -> TurnDetector:
    defaults = dict(threshold=0.5, min_speech_s=0.064, end_silence_s=0.096, pre_roll_s=0.064)
    defaults.update(kw)
    return TurnDetector(vad=ScriptedVAD(probs), **defaults)


def test_silence_emits_nothing():
    det = make_detector([0.0] * 20)
    assert det.process(frames(20)) == []


def test_speech_start_then_utterance():
    # 2 speech frames to start (min_speech 0.064s = 2 frames),
    # then speech, then 3 silence frames to end (0.096s = 3 frames)
    probs = [0.9] * 6 + [0.0] * 4
    det = make_detector(probs)
    events = det.process(frames(10))

    kinds = [e.kind for e in events]
    assert kinds == ["speech_start", "utterance"]
    utterance = events[1].audio
    assert utterance is not None and len(utterance) > 0


def test_brief_noise_below_min_speech_ignored():
    # Single hot frame, then silence — never reaches min_speech_frames
    probs = [0.9] + [0.0] * 10
    det = make_detector(probs)
    assert det.process(frames(11)) == []


def test_pre_roll_included_in_utterance():
    # 2 silence, then speech — pre-roll should prepend ~2 frames
    probs = [0.0, 0.0] + [0.9] * 4 + [0.0] * 4
    det = make_detector(probs)
    events = det.process(frames(10))
    utterance = next(e for e in events if e.kind == "utterance").audio
    # speech started at frame 2; utterance = pre-roll(2) + speech frames
    assert len(utterance) >= FRAME_SAMPLES * 4


def test_max_utterance_forces_cut():
    det = make_detector([0.9] * 50, max_utterance_s=FRAME_SAMPLES * 10 / 16000)
    events = det.process(frames(50))
    assert any(e.kind == "utterance" for e in events)


def test_detector_reusable_after_utterance():
    probs = [0.9] * 4 + [0.0] * 4 + [0.9] * 4 + [0.0] * 4
    det = make_detector(probs)
    events = det.process(frames(16))
    assert [e.kind for e in events].count("utterance") == 2
