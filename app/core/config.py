from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_ADMIN_SECRET_LENGTH = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Hardware Hub API"
    API_V1_PREFIX: str = "/api/v1"

    # Required — no defaults. App fails fast at startup if .env is missing these.
    DATABASE_URL: str
    # One or more allowed frontend origins, comma-separated,
    # e.g. "http://localhost:3000,https://hardwarehub.vercel.app"
    CORS_ORIGIN: str

    # Admin panel — single shared credential pair, no user accounts/JWT needed
    # at this scale. Both teammates use the same ADMIN_ID/ADMIN_SECRET.
    ADMIN_ID: str
    ADMIN_SECRET: str

    @field_validator("ADMIN_SECRET")
    @classmethod
    def _secret_is_long_enough(cls, value: str) -> str:
        # There is no limit on wrong guesses, so the secret itself has to be hard to guess.
        if len(value) < MIN_ADMIN_SECRET_LENGTH:
            raise ValueError(
                f"ADMIN_SECRET must be at least {MIN_ADMIN_SECRET_LENGTH} characters. "
                "Use a long random value, for example: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return value

    @field_validator("ADMIN_ID")
    @classmethod
    def _id_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ADMIN_ID must not be empty.")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGIN.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()