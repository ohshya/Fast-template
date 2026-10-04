import asyncio
import os
import sys
from collections.abc import Callable
from getpass import getpass

from tortoise import Tortoise

from app.core.database import TORTOISE_ORM, require_migrations, uses_migrations
from app.core.schemas.validators import validate_password, validate_username
from app.core.services.event_log import ensure_event_chain, install_event_guards
from app.core.services.users import create_dev_user


def _ask(prompt: str, validator: Callable[[str], str], *, secret: bool = False) -> str:
    """Pide un dato por consola hasta que pase el validador."""
    while True:
        value = (getpass(prompt) if secret else input(prompt)).strip()
        try:
            return validator(value)
        except ValueError as error:
            print(f"  -> {error}")


async def _interactive() -> None:
    """Pide usuario y contraseña por consola hasta crear la cuenta."""
    print("\n=== Crear usuario desarrollador ===\n")
    while True:
        username = _ask("Usuario: ", validate_username)
        while True:
            password = _ask("Contraseña: ", validate_password, secret=True)
            if password == getpass("Repetir contraseña: "):
                break
            print("  -> Las contraseñas no coinciden")
        user = await create_dev_user(username, password)
        if user is not None:
            print(f"\nListo. Usuario '{user.username}' ({user.id}) creado con acceso total.\n")
            return
        print("  -> Ese nombre ya está en uso")


async def _from_environment(username: str, password: str) -> None:
    """Crea la cuenta con ADMIN_USERNAME y ADMIN_PASSWORD; si ya existe, no hace nada."""
    try:
        user = await create_dev_user(username, password)
    except ValueError as error:
        print(f"ADMIN_USERNAME o ADMIN_PASSWORD no son válidos: {error}")
        sys.exit(1)
    if user is None:
        print(f"El usuario '{username}' ya existe; no se crea de nuevo.")
    else:
        print(f"Usuario desarrollador '{user.username}' creado.")


async def main() -> None:
    """Crea el primer usuario dev. Sin preguntar si hay ADMIN_USERNAME y ADMIN_PASSWORD."""
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        if not uses_migrations():
            await Tortoise.generate_schemas()
        await require_migrations()
        await ensure_event_chain()
        await install_event_guards()
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        if username and password:
            await _from_environment(username, password)
        else:
            await _interactive()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
