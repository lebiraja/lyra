"""Incremental sentence segmenter — cuts streaming LLM text into TTS-sized chunks."""

import re

_BOUNDARY = re.compile(r"([.!?…]+[\"')\]]?)(\s|$)")
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "st.", "e.g.", "i.e.", "vs.", "etc."}

MIN_CHUNK_CHARS = 12
MAX_CHUNK_CHARS = 300

# Markdown the LLM sometimes emits despite the prompt — TTS would read it literally.
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|`+)(.+?)\1", re.DOTALL)
_LEADING_MARKS = re.compile(r"^\s*(?:[-*+]|\d+\.|#{1,6})\s+", re.MULTILINE)
_STRAY_MARKS = re.compile(r"[*_`#]")

# Unicode emojis and symbols
_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27bf\u2b50\u2b06\u2190-\u21ff\u2900-\u297f]"
)

# Text-based emoticons/smileys
_EMOTICON_RE = re.compile(
    r"\b[xX][dD]\b|"                                     # XD, xD
    r"(?::|;|=)-?[)DdpPoO(\[\]\\/|{}<>*^]"               # :), :-), :D, :-D, :d, :p, :-p, :o, :-, :[, :], :\, :/, :|, :{}, :<>
    r"\bB-?[)]\b|"                                       # B), B-)
    r"(?:\^[-_]?\^)|"                                    # ^^, ^-^, ^_^
    r"(?:T[-_]?T)|"                                      # T_T, T-T
    r"\b[oO]_[oO]\b"                                     # o_o, O_O
)


def strip_emojis_and_emoticons(text: str) -> str:
    """Strip all unicode emojis, symbols, and text-based emoticons."""
    text = _EMOJI_RE.sub("", text)
    text = _EMOTICON_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clean_for_speech(text: str) -> str:
    """Strip markdown so TTS doesn't pronounce asterisks, backticks, hashes, etc.

    Unwraps *emph*/`code`, drops list bullets and heading marks, then removes any
    stray markup characters left behind. Leaves normal punctuation untouched.
    """
    text = strip_emojis_and_emoticons(text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _LEADING_MARKS.sub("", text)
    text = _STRAY_MARKS.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


class SentenceSegmenter:
    """Feed deltas, get back complete sentences as soon as they exist."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> list[str]:
        self._pending += delta
        out: list[str] = []

        while True:
            match = self._find_boundary(self._pending)
            if match is None:
                break
            sentence, rest = match
            out.append(sentence.strip())
            self._pending = rest

        # Safety valve: never let a chunk grow unbounded (TTS quality + latency)
        if len(self._pending) > MAX_CHUNK_CHARS:
            cut = self._pending.rfind(",", 0, MAX_CHUNK_CHARS)
            if cut == -1:
                cut = self._pending.rfind(" ", 0, MAX_CHUNK_CHARS)
            if cut > MIN_CHUNK_CHARS:
                out.append(self._pending[: cut + 1].strip())
                self._pending = self._pending[cut + 1 :]

        return [s for s in out if s]

    def flush(self) -> list[str]:
        rest = self._pending.strip()
        self._pending = ""
        return [rest] if rest else []

    def _find_boundary(self, text: str) -> tuple[str, str] | None:
        for m in _BOUNDARY.finditer(text):
            end = m.end(1)
            candidate = text[:end]
            if len(candidate.strip()) < MIN_CHUNK_CHARS:
                continue
            last_word = candidate.rsplit(None, 1)[-1].lower() if candidate.split() else ""
            if last_word in _ABBREVIATIONS:
                continue
            return candidate, text[end:].lstrip()
        return None
