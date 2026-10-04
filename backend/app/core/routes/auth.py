from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from tortoise.transactions import in_transaction

from app.core.dependencies import current_session, requires
from app.core.errors import AppError, Err
from app.core.models.event import EventAction
from app.core.models.role import Role
from app.core.models.session import UserSession
from app.core.models.user import Users
from app.core.permissions import Scope, permission
from app.core.schemas.auth import LoginIn, MeOut, PasswordChange, SessionOut
from app.core.schemas.common import Message
from app.core.schemas.validators import validate_username
from app.core.security import (
    clear_token_cookies,
    dummy_password_hash,
    hash_password,
    set_token_cookies,
    verify_password,
)
from app.core.services.auth import (
    clear_login_attempts,
    granted_permissions,
    open_session,
    refresh,
    reserve_login_attempt,
)
from app.core.services.event_log import record_security

GROUP = "Sesión"
LOGIN = permission(2001, "auth.login", GROUP, "Iniciar sesión", Scope.PUBLIC)
REFRESH = permission(2002, "auth.refresh", GROUP, "Renovar los tokens de sesión", Scope.PUBLIC)
LOGOUT = permission(2003, "auth.logout", GROUP, "Cerrar la sesión actual", Scope.AUTHENTICATED)
ME = permission(2004, "auth.me", GROUP, "Ver el perfil propio", Scope.AUTHENTICATED)
SESSIONS_LIST = permission(
    2005, "auth.sessions.list", GROUP, "Ver las sesiones propias", Scope.AUTHENTICATED
)
SESSIONS_REVOKE = permission(
    2006, "auth.sessions.revoke", GROUP, "Cerrar una sesión propia", Scope.AUTHENTICATED
)
SESSIONS_REVOKE_OTHERS = permission(
    2007,
    "auth.sessions.revoke_others",
    GROUP,
    "Cerrar las demás sesiones propias",
    Scope.AUTHENTICATED,
)
PASSWORD_CHANGE = permission(
    2008, "auth.password.change", GROUP, "Cambiar la contraseña propia", Scope.AUTHENTICATED
)

router = APIRouter(prefix="/auth", tags=["Sesión"])


async def build_me(user: Users) -> MeOut:
    role = await Role.get_or_none(id=user.role_id) if user.role_id else None
    granted = await granted_permissions(user)
    return MeOut(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        dev=user.dev,
        role_id=user.role_id,
        role_name=role.name if role else None,
        permissions=[item.id for item in granted],
        permission_keys=[item.key for item in granted],
        last_login_at=user.last_login_at,
    )


@router.post("/login", response_model=MeOut)
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    _public: None = requires(LOGIN, atomic=False),
):
    """Abre sesión y deja los tokens en cookies. No es atómica: el intento se anota aunque falle."""
    origin = request.client.host if request.client else "desconocido"
    await reserve_login_attempt(origin, data.username)

    user = await Users.filter(username=data.username).first()
    valid = await verify_password(
        data.password, user.password if user else await dummy_password_hash()
    )
    if user is None or not valid:
        try:
            shown = validate_username(data.username)
        except ValueError:
            shown = "<inválido>"
        raise AppError(
            Err.INVALID_CREDENTIALS,
            log_message=f"Intento de acceso fallido para '{shown}'",
            details={"username": shown},
        )
    if not user.is_active:
        raise AppError(Err.USER_INACTIVE, log_message=f"'{user.username}' está desactivado")

    async with in_transaction():
        await clear_login_attempts(origin, data.username)
        session, access_token, refresh_token = await open_session(user, request)
        user.last_login_at = datetime.now(UTC)
        await user.save(update_fields=["last_login_at"])
        await record_security(
            EventAction.LOGIN,
            f"{user.username} inició sesión desde {session.ip_address or 'origen desconocido'}",
            actor_id=user.id,
            actor_username=user.username,
            actor_role_id=user.role_id,
            entity_type=UserSession.entity_name(),
            entity_id=session.id,
            entity_label=session.user_agent,
        )

    set_token_cookies(response, access_token, refresh_token)
    return await build_me(user)


@router.post("/refresh", response_model=Message)
async def refresh_session(
    request: Request,
    response: Response,
    _public: None = requires(REFRESH, atomic=False),
):
    """Renueva los tokens. No es atómica: un token robado cierra la sesión aunque falle."""
    try:
        _user, access_token, refresh_token = await refresh(request)
    except AppError:
        request.state.clear_auth_cookies = True
        raise
    set_token_cookies(response, access_token, refresh_token)
    return Message(detail="Sesión renovada")


@router.post("/logout", response_model=Message)
async def logout(request: Request, response: Response, user: Users = requires(LOGOUT)):
    """Cierra la sesión actual."""
    await current_session(request).revoke("cierre de sesión")
    clear_token_cookies(response)
    await record_security(EventAction.LOGOUT, f"{user.username} cerró su sesión")
    return Message(detail="Sesión cerrada")


@router.get("/me", response_model=MeOut)
async def me(user: Users = requires(ME)):
    """Datos y permisos del usuario conectado."""
    return await build_me(user)


@router.get("/sessions", response_model=list[SessionOut])
async def my_sessions(request: Request, user: Users = requires(SESSIONS_LIST)):
    """Sesiones abiertas del usuario."""
    current = current_session(request)
    rows = await UserSession.filter(user_id=user.id).order_by("-last_activity")
    return [SessionOut.of(row, current.id) for row in rows]


@router.post("/sessions/revoke-others", response_model=Message)
async def close_my_other_sessions(request: Request, user: Users = requires(SESSIONS_REVOKE_OTHERS)):
    """Cierra todas las sesiones salvo la actual."""
    current = current_session(request)
    others = await UserSession.filter(user_id=user.id).exclude(id=current.id)
    for session in others:
        await session.revoke("cierre masivo del propio usuario")
    await record_security(
        EventAction.SESSION_REVOKED,
        f"{user.username} cerró {len(others)} sesiones abiertas en otros dispositivos",
    )
    return Message(detail=f"Se cerraron {len(others)} sesiones")


@router.delete("/sessions/{session_id}", response_model=Message)
async def close_my_session(
    session_id: UUID,
    request: Request,
    response: Response,
    user: Users = requires(SESSIONS_REVOKE),
):
    """Cierra una sesión propia."""
    session = await UserSession.filter(id=session_id, user_id=user.id).first()
    if session is None:
        raise AppError(Err.SESSION_NOT_FOUND)

    await session.revoke("cerrada por el usuario")
    await record_security(
        EventAction.SESSION_REVOKED,
        f"{user.username} cerró la sesión de {session.user_agent or 'un dispositivo'}",
        entity_type=UserSession.entity_name(),
        entity_id=session.id,
    )
    if current_session(request).id == session_id:
        clear_token_cookies(response)
    return Message(detail="Sesión cerrada")


@router.post("/password", response_model=Message)
async def change_my_password(
    data: PasswordChange, request: Request, user: Users = requires(PASSWORD_CHANGE, atomic=False)
):
    """Cambia la contraseña propia, con el mismo límite de intentos que el login."""
    origin = request.client.host if request.client else "desconocido"
    await reserve_login_attempt(origin, user.username)
    if not await verify_password(data.current_password, user.password):
        await record_security(
            EventAction.ACCESS_DENIED,
            f"{user.username} falló al confirmar su contraseña actual",
            severity="warning",
        )
        raise AppError(
            Err.VALIDATION,
            log_message=f"{user.username} falló al confirmar su contraseña actual",
            fields={"current_password": "La contraseña actual no es correcta"},
        )

    new_hash = await hash_password(data.new_password)
    async with in_transaction():
        await clear_login_attempts(origin, user.username)
        user.password = new_hash
        await user.save(update_fields=["password"])

        current = current_session(request)
        others = await UserSession.filter(user_id=user.id).exclude(id=current.id)
        for session in others:
            await session.revoke("cambio de contraseña")

        await record_security(
            EventAction.PASSWORD_CHANGE,
            f"{user.username} cambió su contraseña ({len(others)} sesiones cerradas)",
            severity="warning",
            entity_type=Users.entity_name(),
            entity_id=user.id,
            entity_label=user.username,
        )
    return Message(detail="Contraseña actualizada")
