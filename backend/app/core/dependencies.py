from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, Request
from tortoise.transactions import in_transaction

from app.core.context import WRITE_METHODS, set_actor, set_permission
from app.core.errors import AppError, Err
from app.core.models.session import UserSession
from app.core.models.user import Users
from app.core.permissions import Permission, Scope
from app.core.services.auth import authenticate


class PermissionChecker:
    """Exige el permiso del endpoint. Las escrituras van en una transacción si `atomic`."""

    def __init__(self, permission: Permission, *, atomic: bool = True) -> None:
        self.permission = permission
        self.atomic = atomic

    async def __call__(self, request: Request) -> AsyncGenerator[Users | None]:
        user = await self._authorize(request)
        if self.atomic and request.method in WRITE_METHODS:
            async with in_transaction():
                yield user
        else:
            yield user

    async def _authorize(self, request: Request) -> Users | None:
        permission = self.permission
        set_permission(permission.id)
        if permission.scope is Scope.PUBLIC:
            return None

        user, session = await authenticate(request)
        request.state.user = user
        request.state.session = session
        set_actor(user.id, user.username, user.role_id)

        if not await user.can(permission):
            raise AppError(
                Err.DEV_ONLY if permission.scope is Scope.DEV else Err.PERMISSION_DENIED,
                log_message=(
                    f"{user.username} intentó usar {permission.key} "
                    f"(permiso {permission.id}) sin tenerlo"
                ),
                details={"permission": permission.key},
            )
        return user


def requires(permission: Permission, *, atomic: bool = True) -> Any:
    """Dependencia que protege un endpoint: `actor: Users = requires(PERMS.list)`."""
    return Depends(PermissionChecker(permission, atomic=atomic), scope="function")


def current_session(request: Request) -> UserSession:
    """Sesión de la petición. Solo después de `requires()`."""
    session = getattr(request.state, "session", None)
    if not isinstance(session, UserSession):
        raise AppError(Err.NOT_AUTHENTICATED)
    return session
