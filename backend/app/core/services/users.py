from collections.abc import Iterable
from uuid import UUID

from tortoise.transactions import in_transaction

from app.core.errors import AppError, Err
from app.core.models.role import Role
from app.core.models.user import Users
from app.core.schemas.validators import validate_password, validate_username
from app.core.security import hash_password
from app.core.services.event_log import record_system


def check_dev_change(actor: Users, wants_dev: bool | None) -> None:
    """Solo un dev toca la marca dev de una cuenta."""
    if wants_dev is not None and not actor.dev:
        raise AppError(
            Err.CANNOT_ELEVATE_TO_DEV,
            log_message=f"{actor.username} intentó cambiar la marca dev sin ser dev",
        )


async def check_can_grant(actor: Users, permission_ids: Iterable[int]) -> None:
    """Quien no es dev solo concede o gestiona permisos que él mismo tiene."""
    if actor.dev:
        return
    excess = set(permission_ids) - await actor.allowed_ids()
    if excess:
        raise AppError(
            Err.PRIVILEGE_ESCALATION,
            log_message=f"{actor.username} intentó gestionar permisos ajenos: {sorted(excess)}",
            details={"permissions": sorted(excess)},
        )


async def check_role_assignable(actor: Users, role_id: UUID | None) -> None:
    """Un rol solo se asigna si sus permisos caben dentro de los del que lo asigna."""
    role = await Role.get_or_none(id=role_id) if role_id else None
    if role is not None:
        await check_can_grant(actor, role.permissions)


async def protect_account(actor: Users, target: Users) -> None:
    """Solo un dev toca a un dev, y nadie gestiona a quien tiene más permisos que él."""
    if target.dev and not actor.dev:
        raise AppError(
            Err.DEV_ACCOUNT_PROTECTED,
            log_message=f"{actor.username} intentó modificar la cuenta dev {target.username}",
            details={"user_id": str(target.id)},
        )
    await check_can_grant(actor, await target.allowed_ids())


async def create_dev_user(username: str, password: str) -> Users | None:
    """Crea un usuario dev; None si el nombre ya existe."""
    username = validate_username(username)
    validate_password(password)
    if await Users.with_deleted().filter(username=username).exists():
        return None
    async with in_transaction():
        user = await Users.create(
            username=username, password=await hash_password(password), dev=True
        )
        await record_system(f"Usuario desarrollador '{user.username}' creado por consola")
    return user
