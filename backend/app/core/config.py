from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TestVasja API"
    environment: str = "local"
    debug: bool = True

    # postgresql+psycopg://user:password@host:port/database
    database_url: str = "postgresql+psycopg://testvasja:testvasja@localhost:5432/testvasja"

    # CORS origin of the Nuxt dev server.
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
