"""WebSocket endpoint — the voice/text conversation channel.

Protocol (client -> server):
  binary frames            16 kHz int16 mono PCM mic audio
  {"type":"set_session","session_id": str|null, "persona": str|null}
  {"type":"user_text","text": str}
  {"type":"mute","muted": bool}
  {"type":"video_frame","data": str}   base64-encoded JPEG, ~200ms interval

Protocol (server -> client):
  binary frames            24 kHz int16 mono PCM TTS audio
  {"type":"session","session_id": str}
  {"type":"state","state":"listening"|"transcribing"|"generating"|"speaking"}
  {"type":"user_transcript","text": str, "language": str, "language_probability": float}
  {"type":"assistant_delta","text": str}
  {"type":"assistant_done","text": str}
  {"type":"interrupted"}
  {"type":"assistant_greeting","text": str}   # proactive opening (Friend persona)
  {"type":"session","session_id": str, "persona": str}
  {"type":"emotion","label": str, "confidence": float, "source": str}
  {"type":"error","message": str}
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.core.emotion import EmotionBuffer, EmotionFusion
from backend.core.pipeline import ConversationPipeline
from backend.core.vad import TurnDetector

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fer_loop(
    fer,
    fer_buffer: EmotionBuffer,
    frame_queue: asyncio.Queue,
    interval_s: float,
) -> None:
    """Background task: consume video frames, run FER at configured interval."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            b64_data = await asyncio.wait_for(frame_queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        try:
            result = await loop.run_in_executor(None, fer.predict_from_base64, b64_data)
            if result is not None:
                fer_buffer.push(result)
        except Exception:
            logger.debug("FER inference failed on frame", exc_info=True)

        await asyncio.sleep(interval_s)


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    app = websocket.app
    await websocket.accept()

    turn_detector = TurnDetector(
        vad=app.state.make_vad(),
        threshold=settings.VAD_THRESHOLD,
        min_speech_s=settings.VAD_MIN_SPEECH_S,
        end_silence_s=settings.VAD_END_SILENCE_S,
    )

    # Emotion components (may be None if disabled or load failed)
    fer_buffer = EmotionBuffer() if app.state.fer else None
    emotion_fusion = EmotionFusion(
        voice_weight=settings.EMOTION_VOICE_WEIGHT,
        face_weight=settings.EMOTION_FACE_WEIGHT,
        face_confidence_threshold=settings.EMOTION_FER_CONFIDENCE_THRESHOLD,
    ) if settings.EMOTION_ENABLED else None

    pipeline = ConversationPipeline(
        stt=app.state.stt,
        tts=app.state.tts,
        llm=app.state.llm,
        turn_detector=turn_detector,
        db=app.state.store,
        personas=app.state.personas,
        context_tokens=settings.LLM_CONTEXT_TOKENS,
        send_json=websocket.send_json,
        send_bytes=websocket.send_bytes,
        stats=app.state.stats,
        ser=app.state.ser,
        fer_buffer=fer_buffer,
        emotion_fusion=emotion_fusion,
        ser_min_audio_s=settings.EMOTION_SER_MIN_AUDIO_S,
        ser_confidence_threshold=settings.EMOTION_SER_CONFIDENCE_THRESHOLD,
        context_assembler=app.state.context_assembler,
        memory_extractor=app.state.memory_extractor,
        memory_consolidator=app.state.memory_consolidator,
    )
    pipeline.allow_barge_in = settings.ALLOW_BARGE_IN
    pipeline.echo_tail_s = settings.ECHO_TAIL_S

    # FER background loop (started on first video frame)
    fer_task: asyncio.Task | None = None
    frame_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)

    try:
        while True:
            data = await websocket.receive()
            if data.get("type") == "websocket.disconnect":
                break

            if "bytes" in data and data["bytes"] is not None:
                await pipeline.handle_audio(data["bytes"])
            elif "text" in data and data["text"] is not None:
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                match msg.get("type"):
                    case "set_session":
                        session_id = await pipeline.set_session(
                            msg.get("session_id"), msg.get("persona")
                        )
                        await websocket.send_json({
                            "type": "session",
                            "session_id": session_id,
                            "persona": pipeline.persona.id,
                        })
                        await websocket.send_json({"type": "state", "state": "listening"})
                    case "user_text":
                        if pipeline.session_id is None:
                            await pipeline.set_session(None)
                            await websocket.send_json({
                                "type": "session",
                                "session_id": pipeline.session_id,
                                "persona": pipeline.persona.id,
                            })
                        await pipeline.handle_text(msg.get("text", ""))
                    case "mute":
                        pipeline.muted = bool(msg.get("muted"))
                    case "video_frame":
                        b64 = msg.get("data")
                        if b64 and app.state.fer and fer_buffer is not None:
                            # Start FER loop on first frame
                            if fer_task is None:
                                fer_task = asyncio.create_task(
                                    _fer_loop(
                                        app.state.fer,
                                        fer_buffer,
                                        frame_queue,
                                        settings.EMOTION_FER_INTERVAL_MS / 1000,
                                    )
                                )
                            # Non-blocking put — drop frame if queue full (backpressure)
                            try:
                                frame_queue.put_nowait(b64)
                            except asyncio.QueueFull:
                                pass

    except WebSocketDisconnect:
        pass
    finally:
        if fer_task:
            fer_task.cancel()
            try:
                await fer_task
            except asyncio.CancelledError:
                pass
        await pipeline.shutdown()
