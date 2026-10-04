import asyncio
import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import bcrypt
import jwt
from fastapi import Response
from user_agents import parse

from app.settings import settings

ACCESS_COOKIE = f"{settings.cookie_prefix}_access"
REFRESH_COOKIE = f"{settings.cookie_prefix}_refresh"
ACCESS_MINUTES = 15
REFRESH_DAYS = 7
ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


def _prepare(password: str) -> bytes:
    """HMAC-SHA256 en base64: evita el límite de 72 bytes de bcrypt."""
    digest = hmac.new(settings.key("password"), password.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest)


def _hash(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode()


def _check(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode())
    except ValueError:
        return False


async def hash_password(password: str) -> str:
    """Hash bcrypt de la contraseña, fuera del bucle de eventos: bcrypt tarda cientos de ms."""
    return await asyncio.to_thread(_hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    """Si la contraseña coincide con el hash, fuera del bucle de eventos."""
    return await asyncio.to_thread(_check, password, hashed)


_dummy_hash: list[str] = []


async def dummy_password_hash() -> str:
    """Hash de relleno para que el login tarde lo mismo si el usuario no existe."""
    if not _dummy_hash:
        _dummy_hash.append(await hash_password("contraseña-que-nunca-coincide"))
    return _dummy_hash[0]


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: UUID
    session_id: UUID
    jti: str
    type: TokenType


class TokenError(Exception):
    """Token rechazado. `expired` marca la caducidad."""

    def __init__(self, reason: str, *, expired: bool = False) -> None:
        super().__init__(reason)
        self.expired = expired


def create_token(
    user_id: UUID, session_id: UUID, token_type: TokenType
) -> tuple[str, str, datetime]:
    """Devuelve (token, jti, caducidad)."""
    lifetime = (
        timedelta(minutes=ACCESS_MINUTES)
        if token_type == "access"
        else timedelta(days=REFRESH_DAYS)
    )
    jti = str(uuid4())
    issued = datetime.now(UTC)
    expires = issued + lifetime
    payload = {
        "sub": str(user_id),
        "session": str(session_id),
        "jti": jti,
        "type": token_type,
        "iss": settings.jwt_issuer,
        "iat": issued,
        "exp": expires,
    }
    return jwt.encode(payload, settings.key("jwt"), algorithm=ALGORITHM), jti, expires


def read_token(token: str, expected: TokenType) -> TokenClaims:
    """Valida firma, emisor, caducidad y tipo."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.key("jwt"),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "iss", "sub", "jti", "session", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token caducado", expired=True) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Token inválido: {exc}") from exc

    if payload.get("type") != expected:
        raise TokenError("Token de otro tipo")

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise TokenError("Token sin identificador")

    try:
        user_id = UUID(str(payload.get("sub")))
        session_id = UUID(str(payload.get("session")))
    except ValueError as exc:
        raise TokenError("Token con identificadores inválidos") from exc

    return TokenClaims(user_id=user_id, session_id=session_id, jti=jti, type=expected)


def set_token_cookies(response: Response, access: str, refresh: str) -> None:
    """Tokens en cookies httponly."""
    for key, value, seconds in (
        (ACCESS_COOKIE, access, ACCESS_MINUTES * 60),
        (REFRESH_COOKIE, refresh, REFRESH_DAYS * 86400),
    ):
        response.set_cookie(
            key=key,
            value=value,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            max_age=seconds,
            path="/",
        )


def clear_token_cookies(response: Response) -> None:
    """Borra las cookies de sesión."""
    for key in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            key=key,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            path="/",
        )


def describe_user_agent(raw: str | None) -> str:
    """Navegador, sistema y dispositivo en una línea."""
    if not raw:
        return "Desconocido"
    agent: Any = parse(raw)
    device = "Móvil" if agent.is_mobile else "Tablet" if agent.is_tablet else "Escritorio"
    return f"{agent.browser.family} {agent.browser.version_string} · {agent.os.family} · {device}"[
        :255
    ]
