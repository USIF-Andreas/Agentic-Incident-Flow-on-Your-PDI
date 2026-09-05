"""Typed environment configuration (NFR2: zero secrets in VCS)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads credentials from `.env`. All fields have safe defaults so the
    service can boot (and be health-checked) without secrets configured."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GEMINI_API_KEY: str = ""
    SN_INSTANCE_URL: str = ""
    SN_USER: str = ""
    SN_PASSWORD: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    SN_TIMEOUT_SECONDS: float = 15.0


settings = Settings()
