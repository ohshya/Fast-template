from pathlib import Path
from typing import Any

from aerich.models import Aerich
from tortoise.exceptions import OperationalError

from app import registry
from app.core import registry as core
from app.settings import settings

TORTOISE_ORM: dict[str, Any] = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": [module.__name__ for module in (*core.MODELS, *registry.MODELS)],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}


def uses_migrations() -> bool:
    """Si el proyecto tiene `backend/migrations/`: desde entonces el esquema lo gestiona aerich."""
    return (Path(__file__).resolve().parents[2] / "migrations").is_dir()


async def require_migrations() -> None:
    """Con migraciones en el proyecto, exige que esta base ya tenga alguna aplicada."""
    if not uses_migrations():
        return
    try:
        applied = await Aerich.exists()
    except OperationalError:
        applied = False
    if not applied:
        raise RuntimeError(
            "Este proyecto tiene migraciones y esta base no las ha recibido: "
            "ejecuta `uv run aerich upgrade` antes de arrancar."
        )
