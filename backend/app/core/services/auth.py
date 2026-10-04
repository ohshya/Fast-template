import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Request
from starlette.requests import HTTPConnection

from app.core.errors import AppError, Err
from app.core.models.event import EventAction
from app.core.models.login_attempt import LoginAttempt
from app.core.models.session import UserSession
from app.core.models.user import Users
from app.core.permissions import PERMISSIONS, Permission
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    TokenClaims,
    TokenError,
    TokenType,
    create_token,
    describe_user_agent,
    read_token,
)
from app.core.services.event_log import record_security

MAX_SESSIONS_PER_USER = 5
LOGIN_ATTEMPTS = 10
LOGIN_ATTEMPTS_PER_IP = 50
LOGIN_WINDOW_SECONDS = 300


def _login_window_start() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=LOGIN_WINDOW_SECONDS)


async def reserve_login_attempt(ip: str, username: str) -> None:
    """Anota el intento antes de comprobar la clave, para contar ráfagas; 429 si hay demasiados."""
    attempt = await LoginAttempt.create(ip=ip, username=username.lower())
    recent = LoginAttempt.filter(ip=ip, created_at__gte=_login_window_start())
    limits = (
        (recent.filter(username=username.lower()), LOGIN_ATTEMPTS),
        (recent, LOGIN_ATTEMPTS_PER_IP),
    )
    for query, limit in limits:
        if await query.count() <= limit:
            continue
        await attempt.delete()
        first = await query.order_by("created_at").first()
        wait = LOGIN_WINDOW_SECONDS
        if first is not None:
            elapsed = (datetime.now(UTC) - first.created_at).total_seconds()
            wait = math.ceil(LOGIN_WINDOW_SECONDS - elapsed)
        raise AppError(
            Err.RATE_LIMITED,
            log_message=f"Demasiados intentos de login desde {ip} para '{username}'",
            details={"retry_after_seconds": max(wait, 1)},
        )
    await LoginAttempt.filter(created_at__lt=_login_window_start()).delete()


async def clear_login_attempts(ip: str, username: str) -> None:
    """Olvida los intentos de ese usuario e IP tras un login correcto."""
    await LoginAttempt.filter(ip=ip, username=username.lower()).delete()


def _claims(token: str | None, expected: TokenType) -> TokenClaims:
    if not token:
        raise AppError(Err.NOT_AUTHENTICATED)
    try:
        return read_token(token, expected)
    except TokenError as exc:
        spec = Err.SESSION_EXPIRED if exc.expired else Err.INVALID_TOKEN
        raise AppError(spec, log_message=str(exc)) from exc


async def _enforce_session_limit(user: Users) -> None:
    now = datetime.now(UTC)
    alive: list[UserSession] = []
    for session in await UserSession.filter(user_id=user.id).order_by("last_activity"):
        if session.expires_at < now:
            await session.revoke("expirada")
        else:
            alive.append(session)
    excess = max(0, len(alive) - MAX_SESSIONS_PER_USER + 1)
    for session in alive[:excess]:
        await session.revoke("límite de sesiones alcanzado")


async def open_session(user: Users, request: Request) -> tuple[UserSession, str, str]:
    """Abre una sesión y devuelve (sesión, token de acceso, token de refresco)."""
    await _enforce_session_limit(user)

    session = UserSession(user_id=user.id)
    access_token, access_jti, _ = create_token(user.id, session.id, "access")
    refresh_token, refresh_jti, expires_at = create_token(user.id, session.id, "refresh")

    session.access_token_jti = access_jti
    session.refresh_token_jti = refresh_jti
    session.expires_at = expires_at
    session.last_activity = datetime.now(UTC)
    session.user_agent = describe_user_agent(request.headers.get("user-agent"))
    session.ip_address = request.client.host if request.client else None
    await session.save()
    return session, access_token, refresh_token


async def _load_session(session_id: UUID, user_id: UUID) -> UserSession:
    session = await UserSession.filter(id=session_id, user_id=user_id).first()
    if session is None:
        raise AppError(Err.INVALID_TOKEN, log_message="La sesión ya no existe o fue revocada")
    if session.is_expired():
        await session.revoke("expirada")
        raise AppError(Err.SESSION_EXPIRED)
    return session


async def _load_user(user_id: UUID) -> Users:
    user = await Users.filter(id=user_id).first()
    if user is None:
        raise AppError(Err.INVALID_TOKEN, log_message="El usuario del token ya no existe")
    if not user.is_active:
        raise AppError(Err.USER_INACTIVE)
    return user


async def authenticate(connection: HTTPConnection) -> tuple[Users, UserSession]:
    """Identifica al usuario por la cookie de acceso."""
    claims = _claims(connection.cookies.get(ACCESS_COOKIE), "access")
    session = await _load_session(claims.session_id, claims.user_id)
    if session.access_token_jti != claims.jti:
        raise AppError(Err.INVALID_TOKEN, log_message="Token de acceso ya rotado")

    user = await _load_user(claims.user_id)
    if datetime.now(UTC) - session.last_activity > timedelta(seconds=60):
        await session.touch()
    return user, session


async def _revoke_stolen(session: UserSession, claims: TokenClaims) -> None:
    await session.revoke("token de refresco reutilizado")
    await record_security(
        EventAction.ACCESS_DENIED,
        "Se detectó la reutilización de un token de refresco; la sesión fue cerrada",
        severity="critical",
        actor_id=claims.user_id,
        entity_type=UserSession.entity_name(),
        entity_id=session.id,
    )


async def refresh(request: Request) -> tuple[Users, str, str]:
    """Rota los tokens. Un token de refresco ya usado cierra la sesión."""
    claims = _claims(request.cookies.get(REFRESH_COOKIE), "refresh")
    session = await _load_session(claims.session_id, claims.user_id)
    if session.refresh_token_jti != claims.jti:
        await _revoke_stolen(session, claims)
        raise AppError(Err.INVALID_TOKEN, log_message="Reutilización de token de refresco")

    user = await _load_user(claims.user_id)
    access_token, access_jti, _ = create_token(session.user_id, session.id, "access")
    refresh_token, refresh_jti, expires_at = create_token(session.user_id, session.id, "refresh")
    now = datetime.now(UTC)
    rotated = await UserSession.filter(id=session.id, refresh_token_jti=claims.jti).update(
        access_token_jti=access_jti,
        refresh_token_jti=refresh_jti,
        expires_at=expires_at,
        last_activity=now,
        updated_at=now,
    )
    if not rotated:
        await _revoke_stolen(session, claims)
        raise AppError(Err.INVALID_TOKEN, log_message="Renovación simultánea con el mismo token")
    return user, access_token, refresh_token


async def granted_permissions(user: Users) -> list[Permission]:
    """Permisos asignables del usuario: todos si es dev, los de su rol si no."""
    ids = await user.allowed_ids()
    return sorted((PERMISSIONS[pid] for pid in ids if pid in PERMISSIONS), key=lambda p: p.id)
