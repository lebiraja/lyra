"""Configuration — all knobs env-driven via pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    HOST: str = "0.0.0.0"
    PORT: int = 2323
    DEBUG: bool = False

    # llama.cpp server (OpenAI-compatible)
    LLM_BASE_URL: str = "http://localhost:2380/v1"
    LLM_MODEL: str = "qwen3-4b-instruct-2507"
    LLM_MAX_TOKENS: int = 400
    LLM_TEMPERATURE: float = 0.7
    LLM_CONTEXT_TOKENS: int = 8192

    # Model file locations (mounted ro in docker)
    MODELS_DIR: Path = BASE_DIR / "models"

    # STT (faster-whisper)
    STT_MODEL: str = "large-v3-turbo"
    STT_DEVICE: str = "cuda"
    STT_COMPUTE_TYPE: str = "int8"

    # Voice — English (Kokoro)
    TTS_VOICE: str = "af_heart"
    TTS_SPEED: float = 1.0

    # Voice — Tamil (Piper)
    PIPER_TAMIL_ENABLED: bool = True

    # VAD turn-taking
    VAD_THRESHOLD: float = 0.5
    VAD_MIN_SPEECH_S: float = 0.25
    VAD_END_SILENCE_S: float = 0.9  # tolerate mid-sentence pauses before ending a turn

    # Echo / feedback handling (laptop speakers without headphones)
    # When false (default), the mic is ignored while the assistant speaks + a tail,
    # so it never transcribes its own voice. Set true if you use headphones and want
    # to interrupt the assistant by speaking.
    ALLOW_BARGE_IN: bool = False
    ECHO_TAIL_S: float = 0.8

    # Emotion detection (CPU-only, opt-in)
    EMOTION_ENABLED: bool = True
    EMOTION_FER_ENABLED: bool = True
    EMOTION_FER_INTERVAL_MS: int = 200
    EMOTION_FER_CONFIDENCE_THRESHOLD: float = 0.4
    EMOTION_SER_CONFIDENCE_THRESHOLD: float = 0.3
    EMOTION_SER_MIN_AUDIO_S: float = 1.0
    EMOTION_VOICE_WEIGHT: float = 0.55
    EMOTION_FACE_WEIGHT: float = 0.45
    EMOTION_SER_MODEL: str = "superb/wav2vec2-base-superb-er"

    MEMORY_ENABLED: bool = True
    MEMORY_HYBRID_RETRIEVAL: bool = True
    MEMORY_RECENT_MESSAGE_LIMIT: int = 8
    MEMORY_SEMANTIC_LIMIT: int = 8
    MEMORY_CONSOLIDATE_ON_SWITCH: bool = True

    # Semantic memory graph store (off until runtime wiring is enabled)
    SEMANTIC_MEMORY_ENABLED: bool = False
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "clarity-memory-dev"
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_CONNECT_TIMEOUT_S: float = 5.0

    DB_PATH: Path = BASE_DIR / "data" / "medusa.db"
    LOGS_DIR: Path = BASE_DIR / "logs"

    @property
    def piper_tamil_model(self) -> Path:
        return self.MODELS_DIR / "piper-tamil" / "ta_IN-Valluvar-medium.onnx"

    @property
    def piper_tamil_config(self) -> Path:
        return self.MODELS_DIR / "piper-tamil" / "ta_IN-Valluvar-medium.onnx.json"

    @property
    def kokoro_model(self) -> Path:
        return self.MODELS_DIR / "kokoro" / "kokoro-v1.0.onnx"

    @property
    def kokoro_voices(self) -> Path:
        return self.MODELS_DIR / "kokoro" / "voices-v1.0.bin"

    @property
    def silero_model(self) -> Path:
        return self.MODELS_DIR / "silero" / "silero_vad.onnx"


settings = Settings()
