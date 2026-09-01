"""All configuration comes from the environment. Never hardcode secrets."""
from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder shipped in .env.example. Refusing to boot on it outside
# development is what stops a real deployment running on a guessable key.
PLACEHOLDER_SECRET = "CHANGE_ME_IN_ENV"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "EXPRESS OS API"
    ENV: str = "development"            # development | staging | production
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://express:express@db:5432/express"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800         # seconds; avoids stale connections

    # Auth / crypto
    SECRET_KEY: str = PLACEHOLDER_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    ALGORITHM: str = "HS256"
    MIN_PASSWORD_LENGTH: int = 8

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:4310"

    # Local timezone for time-of-day context on Home (storage stays UTC)
    LOCAL_TZ: str = "UTC"

    # JOCasta LLM (optional). If unset, JOCasta falls back to the rule planner
    # and the deterministic conversation templates — it degrades, never breaks.
    #
    # Google Gemini is the active provider. GEMINI_MODEL is deliberately a
    # setting rather than a constant: model ids age out, and a shut-down id
    # should be fixable from the environment rather than by a code change.
    GEMINI_API_KEY: str | None = None
    # Verified reachable on the Developer API free tier. 3.7-flash returns 503
    # "high demand" there and gemini-flash-latest hits the shared quota, so the
    # default is the newest Flash that actually answers for this account.
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Anthropic settings are kept so an existing .env still loads and so the
    # provider can be switched back without a code change. Nothing reads
    # ANTHROPIC_API_KEY while GEMINI_API_KEY is set; see app/jocasta/llm.py.
    ANTHROPIC_API_KEY: str | None = None
    JOCASTA_MODEL: str = "claude-opus-5"

    JOCASTA_MAX_TOKENS: int = 8000
    JOCASTA_EFFORT: str = "low"         # low | medium | high | xhigh | max
    JOCASTA_TIMEOUT_SECONDS: float = 30.0
    JOCASTA_MAX_RETRIES: int = 2

    # Integration credentials. Absent by default: an integration whose credential
    # is missing reports "unconfigured" instead of pretending it can connect.
    OAUTH_REDIRECT_BASE: str = "http://localhost:4311"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    APPLE_TEAM_ID: str | None = None
    SPOTIFY_CLIENT_ID: str | None = None

    # Seed
    DEMO_EMAIL: str = "demo@express.os"
    DEMO_PASSWORD: str = "expressdemo"

    # ---- derived helpers -------------------------------------------------
    @property
    def is_development(self) -> bool:
        return self.ENV.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        """Refresh cookie gets Secure everywhere except local development."""
        return not self.is_development

    @property
    def expose_error_detail(self) -> bool:
        """Only development returns exception text to the client."""
        return self.is_development

    @model_validator(mode="after")
    def _guard(self):
        if not self.is_development:
            if self.SECRET_KEY in (PLACEHOLDER_SECRET, "", None) or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    f"SECRET_KEY must be a real value of at least 32 characters when ENV={self.ENV}. "
                    "Generate one with: openssl rand -hex 32"
                )
            if self.DEMO_PASSWORD == "expressdemo":
                raise ValueError(
                    f"DEMO_PASSWORD is still the shipped default while ENV={self.ENV}. "
                    "Change it, or unset DEMO_EMAIL to skip demo seeding."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
