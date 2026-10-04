from typing import Any
from uuid import UUID

from fastapi import APIRouter
from tortoise.functions import Count

from app.core.crud import Resource
from app.core.errors import AppError, Err
from app.core.models.role import Role
from app.core.models.user import Users
from app.core.permissions import crud_permissions, unknown_permissions
from app.core.schemas.role import RoleCreate, RoleOut, RoleUpdate
from app.core.services.users import check_can_grant

PERMS = crud_permissions(4000, "roles", "Roles", "roles")


def _check_permissions(ids: list[int]) -> list[int]:
    unknown = unknown_permissions(ids)
    if unknown:
        raise AppError(
            Err.UNKNOWN_PERMISSION,
            details={"unknown": unknown},
            fields={"permissions": f"Identificadores no asignables: {unknown}"},
        )
    return sorted(set(ids))


class RolesResource(Resource[Role]):
    model = Role
    create_schema = RoleCreate
    update_schema = RoleUpdate
    out_schema = RoleOut
    permissions = PERMS
    not_found = Err.ROLE_NOT_FOUND
    search_fields = ("name",)
    range_fields = ("created_at", "updated_at")
    sort_fields = ("name", "created_at", "updated_at")
    ordering = ("name",)

    async def serialize(self, items: list[Role]) -> list[Any]:
        counts: dict[UUID, int] = dict.fromkeys((item.id for item in items), 0)
        rows = (
            await Users.filter(role_id__in=list(counts))
            .annotate(total=Count("id"))
            .group_by("role_id")
            .values("role_id", "total")
        )
        for row in rows:
            counts[row["role_id"]] = int(row["total"])
        return [
            RoleOut(
                id=item.id,
                name=item.name,
                description=item.description,
                permissions=sorted(item.permissions),
                users_count=counts[item.id],
                created_at=item.created_at,
                updated_at=item.updated_at,
                deleted_at=item.deleted_at,
            )
            for item in items
        ]

    async def before_create(self, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        permissions = _check_permissions(data["permissions"])
        await check_can_grant(actor, permissions)
        return {**data, "permissions": permissions}

    async def before_update(self, item: Role, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        await check_can_grant(actor, item.permissions)
        if data.get("permissions") is not None:
            permissions = _check_permissions(data["permissions"])
            await check_can_grant(actor, permissions)
            data = {**data, "permissions": permissions}
        return data

    async def before_delete(self, item: Role, actor: Users, *, hard: bool) -> None:
        await check_can_grant(actor, item.permissions)
        query = Users.with_deleted() if hard else Users.all()
        if await query.filter(role_id=item.id).exists():
            raise AppError(Err.ROLE_IN_USE, details={"role_id": str(item.id)})

    async def before_restore(self, item: Role, actor: Users) -> None:
        await check_can_grant(actor, item.permissions)


resource = RolesResource()
router = APIRouter(prefix="/roles", tags=["Roles"])
resource.mount(router)
