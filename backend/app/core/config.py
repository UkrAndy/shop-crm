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

    # Session cookie. See docs/design-docs/design-auth.md.
    session_cookie_name: str = "testvasja_session"
    session_idle_seconds: int = 8 * 60 * 60
    session_absolute_seconds: int = 30 * 24 * 60 * 60

    @property
    def session_cookie_secure(self) -> bool:
        """`Secure` everywhere except local development, where there is no TLS.

        Derived rather than configured: a deployment that forgets to set it must
        fail closed, and `environment` is already required to be correct.
        """
        return self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
