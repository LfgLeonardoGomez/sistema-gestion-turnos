from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_database_url: str
    app_db_password: str
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = True
    session_hours: int = Field(default=12, ge=1, le=168)
    app_env: str = "production"

    @model_validator(mode="after")
    def secure_deployment(self) -> "Settings":
        origin = urlparse(self.app_origin)
        local = origin.hostname in {"localhost", "127.0.0.1", "::1"}
        if (origin.scheme not in {"http", "https"} or not origin.hostname
                or origin.path not in {"", "/"} or origin.username or origin.password
                or origin.query or origin.fragment):
            raise ValueError("APP_ORIGIN debe ser un origen HTTP(S) sin ruta")
        if not local and (origin.scheme != "https" or not self.cookie_secure):
            raise ValueError("Fuera de localhost se requieren HTTPS y COOKIE_SECURE=true")
        if self.app_env not in {"development", "production"}:
            raise ValueError("APP_ENV debe ser development o production")
        if self.app_env == "development" and not local:
            raise ValueError("APP_ENV=development sólo se permite en localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
