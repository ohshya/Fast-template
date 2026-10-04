from uuid import uuid7

from tortoise import fields
from tortoise.models import Model


class LoginAttempt(Model):
    """Intento de login, anotado antes de comprobar la clave y olvidado si acierta."""

    id = fields.UUIDField(primary_key=True, default=uuid7)
    ip = fields.CharField(max_length=45, db_index=True)
    username = fields.CharField(max_length=50, db_index=True)
    created_at = fields.DatetimeField(auto_now_add=True, db_index=True)

    class Meta(Model.Meta):
        table = "login_attempts"
