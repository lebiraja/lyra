"""Medusa backend — FastAPI app factory (bilingual EN/TA)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api import rest, ws
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from backend.config import settings

def setup_logging() -> None:
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    log_file = settings.LOGS_DIR / "medusa.log"
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        l = logging.getLogger(logger_name)
        l.handlers = []
        l.propagate = True

setup_logging()
from backend.core.llm import LLMClient
from backend.core.personas import PersonaRegistry
from backend.core.pipeline import LatencyStats
from backend.db import Database
from backend.memory.consolidator import SessionMemoryConsolidator
from backend.memory.context_assembler import HistoryContextAssembler, HybridContextAssembler
from backend.memory.extractor import ShadowMemoryExtractor
from backend.memory.neo4j_store import create_semantic_memory_store
from backend.memory.retriever import HybridMemoryRetriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    app.state.stats = LatencyStats()
    app.state.personas = PersonaRegistry()

    app.state.store = Database(settings.DB_PATH)
    await app.state.store.connect()
    # Transitional alias while the API and tests still reference `app.state.db`.
    app.state.db = app.state.store
    app.state.graph_store = await create_semantic_memory_store()
    app.state.memory_extractor = ShadowMemoryExtractor(
        app.state.store,
        app.state.graph_store,
        enabled=settings.MEMORY_ENABLED,
    )
    app.state.memory_retriever = HybridMemoryRetriever(
        app.state.store,
        app.state.graph_store,
        recent_message_limit=settings.MEMORY_RECENT_MESSAGE_LIMIT,
        semantic_limit=settings.MEMORY_SEMANTIC_LIMIT,
    )
    app.state.memory_consolidator = SessionMemoryConsolidator(
        app.state.store,
        app.state.graph_store,
    )
    if settings.MEMORY_ENABLED and settings.MEMORY_HYBRID_RETRIEVAL:
        app.state.context_assembler = HybridContextAssembler(
            app.state.store,
            app.state.memory_retriever,
            settings.LLM_MAX_TOKENS,
        )
    else:
        app.state.context_assembler = HistoryContextAssembler(
            app.state.store,
            settings.LLM_MAX_TOKENS,
        )

    app.state.llm = LLMClient(
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=settings.LLM_TEMPERATURE,
    )

    print("Loading STT (Whisper %s, %s, %s)..." % (settings.STT_MODEL, settings.STT_DEVICE, settings.STT_COMPUTE_TYPE))
    from backend.core.stt import WhisperSTT

    app.state.stt = WhisperSTT(
        model_size=settings.STT_MODEL,
        device=settings.STT_DEVICE,
        compute_type=settings.STT_COMPUTE_TYPE,
    )

    print("Loading TTS — English (Kokoro-82M, voice=%s)..." % settings.TTS_VOICE)
    from backend.core.tts import KokoroTTS, PiperTTS, TTSRouter

    kokoro = KokoroTTS(
        settings.kokoro_model, settings.kokoro_voices, settings.TTS_VOICE, settings.TTS_SPEED
    )

    piper_tamil = None
    if settings.PIPER_TAMIL_ENABLED and settings.piper_tamil_model.exists():
        print("Loading TTS — Tamil (Piper)...")
        piper_tamil = PiperTTS(settings.piper_tamil_model, settings.piper_tamil_config)
    elif settings.PIPER_TAMIL_ENABLED:
        print("WARNING: Piper Tamil model not found at %s — Tamil TTS disabled" % settings.piper_tamil_model)

    app.state.tts = TTSRouter(kokoro=kokoro, piper_tamil=piper_tamil)

    from backend.core.vad import SileroVAD

    # Each WS connection gets its own VAD (stateful), sharing nothing
    app.state.make_vad = lambda: SileroVAD(settings.silero_model)

    # Emotion models — CPU only, loaded after GPU models.
    app.state.ser = None
    app.state.fer = None
    if settings.EMOTION_ENABLED:
        try:
            from backend.core.emotion import SpeechEmotionRecognizer

            print("Loading SER (%s, CPU)..." % settings.EMOTION_SER_MODEL)
            app.state.ser = SpeechEmotionRecognizer(model_id=settings.EMOTION_SER_MODEL)
        except Exception as e:
            print("WARNING: SER load failed (%s) — voice emotion disabled" % e)

        if settings.EMOTION_FER_ENABLED:
            try:
                from backend.core.emotion import FacialEmotionRecognizer

                print("Loading FER (EmotiEffNet-B0 ONNX, CPU)...")
                app.state.fer = FacialEmotionRecognizer()
            except Exception as e:
                print("WARNING: FER load failed (%s) — facial emotion disabled" % e)

    app.state.ready = True
    print("Backend ready.")

    yield

    await app.state.llm.close()
    if app.state.graph_store is not None:
        await app.state.graph_store.close()
    await app.state.store.close()


app = FastAPI(title="Medusa", version="3.0.0", lifespan=lifespan)
app.include_router(rest.router, prefix="/api")
app.include_router(ws.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
