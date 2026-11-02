"""
ResolveAIV2 — Application Configuration

Environment-based settings via pydantic-settings.
All secrets and provider selections are configured here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──
    app_name: str = "ResolveAIV2"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-to-a-random-secret-key-in-production"

    # ── Database ──
    database_url: str = "sqlite+aiosqlite:///./resolveai.db"

    # ── JWT ──
    jwt_secret_key: str = "change-me-to-a-random-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── CORS ──
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ── AI Provider ──
    ai_provider: str = "mock"  # mock | openai | gemini | groq | local
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.8-27b"

    # ── RAG Retriever ──
    rag_retriever: str = "tfidf"  # tfidf | faiss

    # ── Voice Providers ──
    stt_provider: str = "sarvam"  # browser | sarvam | whisper | stub
    tts_provider: str = "browser"  # browser | sarvam | edge

    # ── Sarvam Neural Voice (TTS & STT) ──
    sarvam_api_key: str | None = None
    sarvam_speaker: str = "kavya"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_stt_mode: str = "translit"  # translit | codemix | transcribe | verbatim
    sarvam_stt_language_code: str = "unknown"  # 'unknown' enables automatic language detection
    sarvam_stt_keyterms: list[str] = [
        "ResolveAI",
        "refund",
        "Tanglish",
        "Hinglish",
        "order ID",
        "tracking",
        "supervisor",
        "fraud",
        "replacement",
        "cancellation",
        "delivery",
        "account",
        "UPI",
        "transaction",
        "OTP",
        "status",
    ]
    sarvam_stt_prompt: str | None = (
        "Indian customer support conversation. Transcribe speech naturally in the spoken Indian "
        "language, regional code-mixed speech, or Indian English. "
        "Preserve English technical terms, order IDs like ORD-101, tickets like TKT-301, UPI, and amounts "
        "accurately without translating."
    )
    sarvam_stt_timeout: float = 15.0
    sarvam_stt_max_duration_sec: float = 30.0
    sarvam_pitch: float = 0.0  # -0.5 to 0.5 (negative lowers pitch, positive raises pitch)
    sarvam_sample_rate: int = 22050  # 8000, 16000, 22050, 24000, 44100, 48000

    # ── LiveKit Real-Time Voice Transport ──
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None

    # ── Email / Password Reset ──
    email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "noreply@resolveai.com"
    smtp_from_name: str = "ResolveAI Support"
    smtp_tls: bool = True
    smtp_ssl: bool = False

    # ── Frontend URL ──
    frontend_url: str = "http://localhost:5173"

    # ── Google OAuth ──
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
