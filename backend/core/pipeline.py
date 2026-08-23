"""Conversation pipeline — per-connection state machine with barge-in.

States: LISTENING -> TRANSCRIBING -> GENERATING/SPEAKING -> LISTENING
Audio frames keep flowing through VAD in every state; speech during
GENERATING/SPEAKING cancels the in-flight turn (barge-in).
"""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

import numpy as np

from backend.config import settings
from backend.memory.context_assembler import HistoryContextAssembler
from backend.memory.interfaces import (
    ContextAssembler,
    ConversationMemoryStore,
    MemoryConsolidator,
    MemoryExtractor,
)
from backend.core.emotion import (
    EMPTY_EMOTION,
    EmotionBuffer,
    EmotionFusion,
    EmotionState,
    SpeechEmotionRecognizer,
)
from backend.core.segmenter import SentenceSegmenter, clean_for_speech, strip_emojis_and_emoticons

logger = logging.getLogger(__name__)

SendJSON = Callable[[dict[str, Any]], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class LatencyStats:
    """Rolling per-stage latency, surfaced via /api/health."""

    def __init__(self) -> None:
        self.last: dict[str, float] = {}

    def record(self, stage: str, ms: float) -> None:
        self.last[stage] = round(ms, 1)


class ConversationPipeline:
    def __init__(
        self,
        *,
        stt,
        tts,
        llm,
        turn_detector,
        db: ConversationMemoryStore,
        personas,
        context_tokens: int,
        send_json: SendJSON,
        send_bytes: SendBytes,
        stats: LatencyStats,
        ser: SpeechEmotionRecognizer | None = None,
        fer_buffer: EmotionBuffer | None = None,
        emotion_fusion: EmotionFusion | None = None,
        ser_min_audio_s: float = 1.0,
        ser_confidence_threshold: float = 0.3,
        context_assembler: ContextAssembler | None = None,
        memory_extractor: MemoryExtractor | None = None,
        memory_consolidator: MemoryConsolidator | None = None,
    ):
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.turns = turn_detector
        self.db = db
        self.personas = personas
        self.context_tokens = context_tokens
        self.send_json = send_json
        self.send_bytes = send_bytes
        self.stats = stats

        # Emotion detection (all optional — graceful degradation)
        self.ser = ser
        self.fer_buffer = fer_buffer
        self.emotion_fusion = emotion_fusion or EmotionFusion()
        self.ser_min_audio_s = ser_min_audio_s
        self.ser_confidence_threshold = ser_confidence_threshold
        self._current_emotion: EmotionState = EMPTY_EMOTION
        self.context_assembler = context_assembler or HistoryContextAssembler(
            db, llm.max_tokens
        )
        self.memory_extractor = memory_extractor
        self.memory_consolidator = memory_consolidator

        self.session_id: str | None = None
        self.persona = personas.get(None)  # default until set_session
        self.system_prompt = self.persona.render_prompt()
        self.has_memories = False
        self.muted = False
        self._turn_task: asyncio.Task | None = None

        # Half-duplex echo guard: while the assistant is producing audio (and for a
        # short tail afterward), ignore the mic so the bot doesn't hear itself and
        # loop. Set allow_barge_in=True (e.g. for headphone users) to disable this.
        self.allow_barge_in = False
        self._busy = False  # transcribing/generating/speaking
        self._echo_guard_until = 0.0  # monotonic deadline after last audio sent
        self._plays_until = 0.0  # monotonic estimate of when queued audio finishes
        self.echo_tail_s = 0.8

    async def _emit_state(self, state: str) -> None:
        await self.send_json({"type": "state", "state": state})
        if self.session_id is not None:
            try:
                await self.db.record_event(
                    self.session_id,
                    "state_transition",
                    metadata={"state": state},
                )
            except Exception:
                logger.debug(
                    "dropping state transition %s during shutdown or storage failure",
                    state,
                    exc_info=True,
                )

    async def _record_event(
        self,
        event_type: str,
        *,
        role: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int | None:
        if self.session_id is None:
            return None
        try:
            return await self.db.record_event(
                self.session_id,
                event_type,
                role=role,
                content=content,
                metadata=metadata,
            )
        except Exception:
            logger.debug("dropping event %s during shutdown or storage failure", event_type, exc_info=True)
            return None

    async def _store_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.session_id is None:
            return
        try:
            await self.db.add_message(
                self.session_id,
                role,
                content,
                metadata=metadata,
            )
        except Exception:
            logger.debug(
                "dropping %s message during shutdown or storage failure",
                role,
                exc_info=True,
            )

    # ------------------------------------------------------------------ input

    async def set_session(self, session_id: str | None, persona_id: str | None = None) -> str:
        """Resume or start a conversation under a chosen persona.

        Resuming an existing session keeps its stored persona (locked per
        conversation). A new session adopts `persona_id`. Friend-style personas
        load their cross-session memory and open with a spoken greeting.
        """
        # Summarize the conversation we're leaving (memory personas only).
        await self._cancel_turn()
        await self._remember()
        if (
            settings.MEMORY_ENABLED
            and settings.MEMORY_CONSOLIDATE_ON_SWITCH
            and self.memory_consolidator is not None
            and self.session_id is not None
        ):
            await self.memory_consolidator.consolidate_session(self.session_id)

        resuming = bool(session_id and await self.db.session_exists(session_id))
        if resuming:
            self.session_id = session_id
            stored = await self.db.get_session_persona(session_id)
            self.persona = self.personas.get(stored)
            await self._record_event(
                "session_resumed",
                metadata={"persona_id": self.persona.id},
            )
        else:
            self.persona = self.personas.get(persona_id)
            self.session_id = await self.db.create_session(persona=self.persona.id)
            await self._record_event(
                "session_created",
                metadata={"persona_id": self.persona.id},
            )

        await self._record_event(
            "persona_selected",
            metadata={"persona_id": self.persona.id},
        )

        await self._load_prompt()

        # Proactive personas (Friend) greet on entering a fresh conversation.
        is_empty = not await self.db.get_messages(self.session_id)
        if self.persona.proactive and is_empty:
            self._start_greeting()

        return self.session_id

    async def _load_prompt(self) -> None:
        """Build the system prompt, injecting cross-session memory if the persona uses it."""
        memory = None
        if self.persona.cross_session_memory:
            summaries = await self.db.get_memories(self.persona.id)
            self.has_memories = bool(summaries)
            if summaries:
                memory = "\n".join(f"- {s}" for s in summaries)
        else:
            self.has_memories = False
        self.system_prompt = self.persona.render_prompt(memory)

    async def handle_audio(self, pcm_bytes: bytes) -> None:
        """Continuous 16 kHz int16 mono frames from the client mic."""
        if self.muted:
            return

        # Half-duplex echo guard: drop mic input while the assistant is busy
        # producing audio, plus a short tail, so it never transcribes its own
        # voice leaking from the speakers. (Disabled when barge-in is allowed.)
        if not self.allow_barge_in and (self._busy or time.monotonic() < self._echo_guard_until):
            self.turns.reset()  # discard any partial/echo frames
            return

        pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        for event in self.turns.process(pcm):
            if event.kind == "speech_start":
                if self.allow_barge_in:
                    await self._barge_in()
                await self._record_event("speech_start_detected")
                await self._emit_state("listening")
            elif event.kind == "utterance":
                self._start_turn(audio=event.audio)

    async def handle_text(self, text: str) -> None:
        """Typed message — same pipeline, skips STT."""
        text = text.strip()
        if not text:
            return
        await self._barge_in()
        self._start_turn(text=text)

    async def shutdown(self) -> None:
        await self._cancel_turn()
        await self._remember()
        if self.memory_consolidator is not None and self.session_id is not None:
            await self.memory_consolidator.consolidate_session(self.session_id)
        await self._record_event("session_closed")

    # ------------------------------------------------------------------- turn

    def _start_turn(self, audio: np.ndarray | None = None, text: str | None = None) -> None:
        self._busy = True  # set synchronously so mic frames are gated immediately
        self._turn_task = asyncio.create_task(self._run_turn(audio, text))

    def _start_greeting(self) -> None:
        self._busy = True
        self._turn_task = asyncio.create_task(self._run_greeting())

    def _end_busy(self) -> None:
        """Clear busy state and open the echo-guard tail before listening resumes.

        The guard extends past when the queued TTS audio actually finishes playing
        in the browser (not just when it was sent), plus a tail for the echo decay.
        """
        self._busy = False
        self._echo_guard_until = max(time.monotonic(), self._plays_until) + self.echo_tail_s
        self.turns.reset()  # forget any echo frames buffered during speech

    async def _barge_in(self) -> None:
        if self._turn_task and not self._turn_task.done():
            await self._cancel_turn()
            await self.send_json({"type": "interrupted"})
            await self._record_event("interrupted")

    async def _cancel_turn(self) -> None:
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
            try:
                await self._turn_task
            except asyncio.CancelledError:
                pass
        self._turn_task = None

    async def _run_turn(self, audio: np.ndarray | None, text: str | None) -> None:
        assert self.session_id is not None
        loop = asyncio.get_running_loop()
        assistant_text = ""
        partial: list[str] = []
        detected_lang = "en"
        try:
            await self._record_event(
                "turn_started",
                metadata={"mode": "text" if text is not None else "voice"},
            )
            # 1. Transcribe (voice turns only) — SER runs in parallel when available
            if text is None:
                await self._emit_state("transcribing")
                t0 = time.perf_counter()

                stt_coro = loop.run_in_executor(None, self.stt.transcribe, audio)

                # Fork SER in parallel if audio is long enough
                ser_result: EmotionState = EMPTY_EMOTION
                audio_duration_s = audio.size / 16000 if audio is not None else 0
                if self.ser and audio is not None and audio_duration_s >= self.ser_min_audio_s:
                    ser_coro = loop.run_in_executor(None, self.ser.predict, audio)
                    stt_result, ser_result = await asyncio.gather(stt_coro, ser_coro)
                    self.stats.record("ser_ms", (time.perf_counter() - t0) * 1000)
                else:
                    stt_result = await stt_coro

                self.stats.record("stt_ms", (time.perf_counter() - t0) * 1000)
                text = stt_result.text
                detected_lang = stt_result.language
                if not text:
                    await self._emit_state("listening")
                    return
                await self.send_json({
                    "type": "user_transcript",
                    "text": text,
                    "language": detected_lang,
                    "language_probability": stt_result.language_probability,
                })

                # Fuse FER (from buffer) + SER
                fer_snapshot = self.fer_buffer.snapshot() if self.fer_buffer else None
                self._current_emotion = self.emotion_fusion.fuse(fer_snapshot, ser_result)
                user_event_id = await self._record_event(
                    "user_transcript",
                    role="user",
                    content=text,
                    metadata={
                        "language": detected_lang,
                        "language_probability": stt_result.language_probability,
                        "emotion_label": self._current_emotion.label,
                        "emotion_confidence": self._current_emotion.confidence,
                    },
                )

                if self._current_emotion.label != "neutral" and self._current_emotion.confidence >= self.ser_confidence_threshold:
                    await self.send_json({
                        "type": "emotion",
                        "label": self._current_emotion.label,
                        "confidence": round(self._current_emotion.confidence, 2),
                        "source": self._current_emotion.source,
                    })
                    await self._record_event(
                        "emotion_detected",
                        metadata={
                            "emotion_label": self._current_emotion.label,
                            "emotion_confidence": self._current_emotion.confidence,
                            "source": self._current_emotion.source,
                        },
                    )
            else:
                self._current_emotion = EMPTY_EMOTION
                user_event_id = await self._record_event(
                    "user_transcript",
                    role="user",
                    content=text,
                    metadata={"language": detected_lang},
                )

            await self._store_message(
                "user",
                text,
                metadata={
                    "language": detected_lang,
                    "emotion_label": self._current_emotion.label,
                    "emotion_confidence": self._current_emotion.confidence,
                },
            )

            # 2. Build windowed history, then stream LLM -> segment -> TTS
            messages = await self._windowed_messages(query=text)
            assistant_text = await self._stream_and_speak(messages, detected_lang, partial=partial)
            assistant_text = strip_emojis_and_emoticons(assistant_text)

            await self._store_message(
                "assistant",
                assistant_text,
                metadata={"language": detected_lang},
            )
            if self.memory_extractor is not None:
                await self.memory_extractor.extract_from_turn(
                    session_id=self.session_id,
                    user_text=text,
                    assistant_text=assistant_text,
                    metadata={
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "user_event_id": user_event_id,
                    },
                )
            await self._emit_state("listening")

        except asyncio.CancelledError:
            # Barge-in or disconnect: persist whatever was said so far
            said = assistant_text or "".join(partial)
            said = strip_emojis_and_emoticons(said)
            if said:
                await self._store_message("assistant", said)
            raise
        except Exception as e:
            await self.send_json({"type": "error", "message": "Something went wrong, try again."})
            print(f"[pipeline] turn failed: {type(e).__name__}: {e}")
            await self._record_event("error", metadata={"kind": type(e).__name__})
            await self._emit_state("listening")
        finally:
            self._end_busy()

    async def _run_greeting(self) -> None:
        """Proactive opening for personas like Friend — speak first, no user turn."""
        assert self.session_id is not None
        greeting = ""
        partial: list[str] = []
        try:
            if self.has_memories:
                user_msg = (
                    "(The person just opened the app. In exactly 1 sentence, ask them how "
                    "they are doing regarding what you remember about them.)"
                )
            else:
                user_msg = (
                    "(The person just opened the app. Greet them casually, like 'Hey, how's it going?' "
                    "or 'Hey, good to see you,' in exactly 1 sentence. Do NOT mention any fake shared past, "
                    "coffee shops, or bakeries.)"
                )
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_msg},
            ]
            greeting = await self._stream_and_speak(
                messages, "en", event="assistant_greeting", partial=partial
            )
            greeting = strip_emojis_and_emoticons(greeting)
            if greeting:
                await self._store_message(
                    "assistant",
                    greeting,
                    metadata={"message_type": "greeting", "language": "en"},
                )
                await self._record_event(
                    "assistant_greeting",
                    role="assistant",
                    content=greeting,
                    metadata={"language": "en"},
                )
            await self._emit_state("listening")
        except asyncio.CancelledError:
            said = greeting or "".join(partial)
            said = strip_emojis_and_emoticons(said)
            if said:
                await self._store_message("assistant", said)
            raise
        except Exception as e:
            print(f"[pipeline] greeting failed: {type(e).__name__}: {e}")
            await self._record_event("error", metadata={"kind": type(e).__name__})
            await self._emit_state("listening")
        finally:
            self._end_busy()

    async def _stream_and_speak(
        self,
        messages: list[dict[str, str]],
        language: str,
        event: str = "assistant_delta",
        partial: list[str] | None = None,
    ) -> str:
        """Stream LLM tokens to text events while synthesizing speech per sentence.

        Shared by normal turns and proactive greetings. Returns the full text.
        `partial` (if given) accumulates deltas so a cancelled caller can recover
        whatever was said before barge-in.
        """
        loop = asyncio.get_running_loop()
        await self._emit_state("generating")
        segmenter = SentenceSegmenter()
        assistant_text = ""
        t0 = time.perf_counter()
        t_first_token: float | None = None
        t_first_audio: float | None = None
        speaking = False

        async def speak(sentence: str) -> None:
            nonlocal speaking, t_first_audio
            spoken = clean_for_speech(sentence)
            if not spoken:
                return
            pcm = await loop.run_in_executor(None, self.tts.synthesize, spoken, language)
            if not pcm:
                return
            if not speaking:
                speaking = True
                await self._emit_state("speaking")
            if t_first_audio is None:
                t_first_audio = time.perf_counter()
                self.stats.record("first_audio_ms", (t_first_audio - t0) * 1000)
            await self.send_bytes(pcm)
            # Track when this audio will finish playing in the browser (24kHz int16
            # mono). Chunks queue gaplessly, so playback ends at max(now, prev_end)
            # + this chunk's duration. Used by the echo guard.
            chunk_s = len(pcm) / 2 / 24000
            now = time.monotonic()
            self._plays_until = max(now, self._plays_until) + chunk_s

        async for delta in self.llm.stream_chat(messages):
            if t_first_token is None:
                t_first_token = time.perf_counter()
                self.stats.record("llm_ttft_ms", (t_first_token - t0) * 1000)
            assistant_text += delta
            if partial is not None:
                partial.append(delta)
            await self.send_json({"type": event, "text": delta})
            await self._record_event(event, role="assistant", content=delta)
            for sentence in segmenter.feed(delta):
                await speak(sentence)

        for sentence in segmenter.flush():
            await speak(sentence)

        assistant_text = strip_emojis_and_emoticons(assistant_text)
        await self.send_json({"type": "assistant_done", "text": assistant_text})
        await self._record_event("assistant_done", role="assistant", content=assistant_text)
        return assistant_text

    async def _remember(self) -> None:
        """For memory personas: summarize this conversation and store it for next time."""
        if not self.persona.cross_session_memory or self.session_id is None:
            return
        if await self.db.has_memory_for_session(self.session_id):
            return  # already summarized (e.g. switched away earlier)

        history = await self.db.get_messages(self.session_id)
        if len(history) < 2:
            return  # nothing meaningful happened

        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        prompt = [
            {
                "role": "system",
                "content": "You write a brief third-person memory note about a friend, "
                "for your own future reference. 1-3 sentences. Capture what's going on in "
                "their life, how they seemed, and anything to follow up on. No preamble.",
            },
            {"role": "user", "content": transcript},
        ]
        try:
            summary = ""
            async for delta in self.llm.stream_chat(prompt):
                summary += delta
            summary = summary.strip()
            if summary:
                await self.db.save_memory(self.persona.id, self.session_id, summary)
                await self._record_event(
                    "memory_summary_saved",
                    metadata={"persona_id": self.persona.id},
                )
        except Exception as e:
            print(f"[pipeline] memory summary failed: {type(e).__name__}: {e}")

    async def _windowed_messages(self, query: str | None = None) -> list[dict[str, str]]:
        """Assemble current-generation prompt context through an explicit seam."""
        return await self.context_assembler.assemble(
            session_id=self.session_id,
            persona_id=self.persona.id,
            system_prompt=self.system_prompt,
            query=query,
            budget_tokens=self.context_tokens,
            emotion_state=self._current_emotion,
            emotion_confidence_threshold=self.ser_confidence_threshold,
        )
