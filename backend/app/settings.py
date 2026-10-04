import hashlib
import hmac
import re
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DATABASE_URL = "postgres://postgres:admin@localhost:5432/template"
DEV_SECRET_KEY = "clave-solo-para-desarrollo-no-usar-en-produccion-0123456789"


class Settings(BaseSettings):
    """Ajustes del entorno. Sin `.env` ni variables rigen los de desarrollo, solo con DEBUG=true."""

    debug: bool = True
    app_name: str = "Template"
    app_version: str = "0.1.0"
    database_url: str = DEV_DATABASE_URL
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    secret_key: str = DEV_SECRET_KEY
    jwt_issuer: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cookie_prefix(self) -> str:
        """Prefijo de las cookies de sesión, sacado de APP_NAME: dos proyectos no se pisan."""
        return re.sub(r"[^a-z0-9]+", "-", self.app_name.lower()).strip("-") or "app"

    @property
    def cookie_secure(self) -> bool:
        return not self.debug

    @property
    def cookie_samesite(self) -> Literal["strict", "lax"]:
        return ("strict", "lax")[self.debug]

    def key(self, purpose: str) -> bytes:
        """Clave derivada de SECRET_KEY para un solo uso: filtrar una no compromete a las demás."""
        return hmac.new(self.secret_key.encode(), purpose.encode(), hashlib.sha256).digest()

    @model_validator(mode="after")
    def _check_environment(self) -> Self:
        """Exige PostgreSQL, una clave larga y, fuera de desarrollo, valores propios y https."""
        if not self.database_url.startswith("postgres://"):
            raise ValueError("DATABASE_URL es obligatoria y debe empezar por postgres://")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY es obligatoria y debe tener al menos 32 caracteres")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS no admite *: las cookies viajan con credenciales")
        if not self.debug and DEV_DATABASE_URL == self.database_url:
            raise ValueError("Con DEBUG=false hay que poner tu propia DATABASE_URL")
        if not self.debug and DEV_SECRET_KEY == self.secret_key:
            raise ValueError("Con DEBUG=false hay que poner tu propia SECRET_KEY")
        if not self.debug and not all(
            origin.startswith("https://") for origin in [self.jwt_issuer, *self.cors_origins]
        ):
            raise ValueError("Con DEBUG=false JWT_ISSUER y CORS_ORIGINS deben usar https://")
        return self


settings = Settings()
