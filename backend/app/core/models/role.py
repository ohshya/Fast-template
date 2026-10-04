from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.contrib.postgres.fields import ArrayField

from app.core.models.entity import Entity

if TYPE_CHECKING:
    from app.core.models.user import Users


class Role(Entity):
    """Nombre y lista de identificadores de permiso."""

    name = fields.CharField(max_length=100, unique=True)
    description = fields.CharField(max_length=255, default="")
    permissions: list[int] = ArrayField(element_type="int", default=list)

    users: fields.ReverseRelation[Users]

    audit_label_field = "name"

    class Meta(Entity.Meta):
        table = "roles"
