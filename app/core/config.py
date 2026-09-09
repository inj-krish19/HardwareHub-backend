from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Hardware Hub API"
    API_V1_PREFIX: str = "/api/v1"

    # Required — no defaults. App fails fast at startup if .env is missing these.
    DATABASE_URL: str
    CORS_ORIGIN: str

    # Admin panel — single shared credential pair, no user accounts/JWT needed
    # at this scale. Both teammates use the same ADMIN_ID/ADMIN_SECRET.
    ADMIN_ID: str
    ADMIN_SECRET: str  # comma-separated, e.g. "http://localhost:3000,https://hardwarehub.vercel.app"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGIN.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()