from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.core.crud import Resource
from app.core.dependencies import requires
from app.core.errors import AppError, Err
from app.core.models.event import EventAction
from app.core.models.role import Role
from app.core.models.session import UserSession
from app.core.models.user import Users
from app.core.permissions import crud_permissions, permission
from app.core.schemas.auth import SessionOut
from app.core.schemas.common import Message
from app.core.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate
from app.core.security import hash_password
from app.core.services.event_log import record_security
from app.core.services.users import check_dev_change, check_role_assignable, protect_account

GROUP = "Usuarios"
PERMS = crud_permissions(3000, "users", GROUP, "usuarios")
PASSWORD_RESET = permission(
    3011, "users.password.reset", GROUP, "Restablecer la contraseña de un usuario"
)
SESSIONS_LIST = permission(
    3012, "users.sessions.list", GROUP, "Ver las sesiones de cualquier usuario"
)
SESSIONS_REVOKE = permission(
    3013, "users.sessions.revoke", GROUP, "Cerrar las sesiones de cualquier usuario"
)


class UsersResource(Resource[Users]):
    model = Users
    create_schema = UserCreate
    update_schema = UserUpdate
    out_schema = UserOut
    permissions = PERMS
    not_found = Err.USER_NOT_FOUND
    search_fields = ("username",)
    filter_fields = ("is_active", "dev", "role_id")
    range_fields = ("created_at", "last_login_at")
    sort_fields = ("username", "is_active", "created_at", "last_login_at")
    ordering = ("username",)

    async def serialize(self, items: list[Users]) -> list[Any]:
        role_ids = {item.role_id for item in items if item.role_id}
        names = {role.id: role.name for role in await Role.with_deleted().filter(id__in=role_ids)}
        return [
            UserOut(
                id=item.id,
                username=item.username,
                is_active=item.is_active,
                dev=item.dev,
                role_id=item.role_id,
                role_name=names.get(item.role_id) if item.role_id else None,
                created_at=item.created_at,
                updated_at=item.updated_at,
                deleted_at=item.deleted_at,
                last_login_at=item.last_login_at,
            )
            for item in items
        ]

    async def before_create(self, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        check_dev_change(actor, data.get("dev") or None)
        await check_role_assignable(actor, data.get("role_id"))
        return {**data, "password": await hash_password(data["password"])}

    async def before_update(
        self, item: Users, data: dict[str, Any], actor: Users
    ) -> dict[str, Any]:
        await protect_account(actor, item)
        await check_role_assignable(actor, data.get("role_id"))
        if "dev" in data:
            check_dev_change(actor, data["dev"])
        if item.id == actor.id and (data.get("is_active") is False or data.get("dev") is False):
            raise AppError(
                Err.CANNOT_MODIFY_SELF, log_message="Intento de desactivarse o quitarse el rol dev"
            )
        return data

    async def before_delete(self, item: Users, actor: Users, *, hard: bool) -> None:
        if item.id == actor.id:
            raise AppError(Err.CANNOT_MODIFY_SELF, log_message="Intento de eliminarse a sí mismo")
        await protect_account(actor, item)

    async def after_delete(self, item: Users, actor: Users) -> None:
        for session in await UserSession.filter(user_id=item.id):
            await session.revoke("usuario eliminado")

    async def before_restore(self, item: Users, actor: Users) -> None:
        await protect_account(actor, item)


resource = UsersResource()
router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.post("/{item_id}/password", response_model=Message)
async def reset_password(
    item_id: UUID, data: PasswordReset, actor: Users = requires(PASSWORD_RESET)
):
    """Restablece la contraseña de otro usuario y cierra sus sesiones."""
    user = await resource.get(item_id)
    if user.id == actor.id:
        raise AppError(
            Err.CANNOT_MODIFY_SELF,
            log_message="Intento de restablecer su propia contraseña sin dar la actual",
            details={"use": "POST /api/auth/password"},
        )
    await protect_account(actor, user)
    user.password = await hash_password(data.new_password)
    await user.save(update_fields=["password"])

    for session in await UserSession.filter(user_id=user.id):
        await session.revoke("contraseña restablecida")

    await record_security(
        EventAction.PASSWORD_CHANGE,
        f"{actor.username} restableció la contraseña de {user.username}",
        severity="warning",
        entity_type=Users.entity_name(),
        entity_id=user.id,
        entity_label=user.username,
    )
    return Message(detail="Contraseña restablecida; se cerraron sus sesiones")


@router.get("/{item_id}/sessions", response_model=list[SessionOut])
async def list_user_sessions(item_id: UUID, actor: Users = requires(SESSIONS_LIST)):
    """Sesiones abiertas de un usuario."""
    user = await resource.get(item_id, include_deleted=True)
    await protect_account(actor, user)
    rows = await UserSession.filter(user_id=user.id).order_by("-last_activity")
    return [SessionOut.of(row, None) for row in rows]


@router.delete("/{item_id}/sessions", response_model=Message)
async def revoke_user_sessions(item_id: UUID, actor: Users = requires(SESSIONS_REVOKE)):
    """Cierra todas las sesiones de un usuario."""
    user = await resource.get(item_id, include_deleted=True)
    await protect_account(actor, user)
    rows = await UserSession.filter(user_id=user.id)
    for session in rows:
        await session.revoke(f"cerrada por {actor.username}")
    await record_security(
        EventAction.SESSION_REVOKED,
        f"{actor.username} cerró {len(rows)} sesiones de {user.username}",
        severity="warning",
        entity_type=Users.entity_name(),
        entity_id=user.id,
        entity_label=user.username,
    )
    return Message(detail=f"Se cerraron {len(rows)} sesiones")


resource.mount(router)
