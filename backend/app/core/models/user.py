from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields

from app.core.models.entity import Entity
from app.core.models.role import Role
from app.core.permissions import Permission, Scope, assignable_ids

if TYPE_CHECKING:
    from app.core.models.session import UserSession


class Users(Entity):
    """Usuario. `dev` da acceso total; `role` da su lista de permisos."""

    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)
    dev = fields.BooleanField(default=False)
    role: fields.ForeignKeyNullableRelation[Role] = fields.ForeignKeyField(
        "models.Role", related_name="users", null=True, on_delete=fields.SET_NULL
    )
    role_id: UUID | None
    last_login_at = fields.DatetimeField(null=True)

    sessions: fields.ReverseRelation[UserSession]

    audit_label_field = "username"
    audit_redact = frozenset({"password"})
    audit_ignore = frozenset({"last_login_at"})

    role_permissions: set[int] | None = None

    class Meta(Entity.Meta):
        table = "users"

    def __str__(self) -> str:
        return self.username

    async def permission_ids(self) -> set[int]:
        """Permisos de su rol; se consultan una vez por objeto."""
        if self.role_permissions is None:
            role = await Role.get_or_none(id=self.role_id) if self.role_id else None
            self.role_permissions = set(role.permissions) if role else set()
        return self.role_permissions

    async def allowed_ids(self) -> set[int]:
        """Permisos que puede usar y conceder: los asignables si es dev, los de su rol si no."""
        return set(assignable_ids()) if self.dev else await self.permission_ids()

    async def can(self, permission: Permission) -> bool:
        """Si puede usar el endpoint de ese permiso."""
        if self.dev:
            return True
        if permission.scope in (Scope.PUBLIC, Scope.AUTHENTICATED):
            return True
        if permission.scope is Scope.DEV:
            return False
        return permission.id in await self.permission_ids()
