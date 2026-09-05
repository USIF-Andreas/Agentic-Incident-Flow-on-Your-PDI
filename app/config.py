from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from .env so secrets never land in git. Empty defaults let the
    # service boot for health checks even with nothing configured.

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GEMINI_API_KEY: str = ""
    SN_INSTANCE_URL: str = ""
    SN_USER: str = ""
    SN_PASSWORD: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    SN_TIMEOUT_SECONDS: float = 15.0


settings = Settings()
