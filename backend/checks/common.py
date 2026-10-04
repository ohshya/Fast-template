import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import asyncpg
import httpx

BASE_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")


def admin() -> tuple[str, str]:
    """Usuario dev y contraseña de ADMIN_USERNAME y ADMIN_PASSWORD; sale si faltan."""
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        sys.exit("Define ADMIN_USERNAME y ADMIN_PASSWORD con un usuario dev (create_admin).")
    return username, password


def tag() -> str:
    """Texto corto y único para que las pruebas no choquen entre ejecuciones."""
    return uuid4().hex[:6]


def client() -> httpx.Client:
    """Cliente HTTP con jar de cookies propio."""
    return httpx.Client(base_url=BASE_URL, timeout=60)


def login(session: httpx.Client, username: str, password: str) -> httpx.Response:
    """Inicia sesión y deja las cookies en el cliente."""
    return session.post("/api/auth/login", json={"username": username, "password": password})


def dev_client() -> httpx.Client:
    """Cliente con sesión de usuario dev abierta."""
    username, password = admin()
    session = client()
    response = login(session, username, password)
    if response.status_code != 200:
        sys.exit(
            f"No se pudo iniciar sesión como {username}: {response.status_code} {response.text}"
        )
    return session


def error_of(response: httpx.Response) -> dict[str, Any]:
    """Cuerpo `error` de una respuesta de error, o {} si no lo tiene."""
    try:
        return response.json().get("error") or {}
    except ValueError:
        return {}


def code_of(response: httpx.Response) -> str | None:
    """Código de error de la API de una respuesta."""
    return error_of(response).get("code")


def fields_of(response: httpx.Response) -> dict[str, str]:
    """Errores por campo de una respuesta 422 o 409."""
    return error_of(response).get("fields") or {}


def iso(moment: datetime) -> str:
    """Fecha en ISO 8601 UTC con Z."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@asynccontextmanager
async def database() -> AsyncGenerator[asyncpg.Connection]:
    """Conexión directa a la base con DATABASE_URL, para preparar o alterar datos en las pruebas."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Define DATABASE_URL (la misma que usa el servidor).")
    connection = await asyncpg.connect(url.replace("postgres://", "postgresql://", 1))
    try:
        yield connection
    finally:
        await connection.close()


def query(statement: str, *args: Any) -> list[asyncpg.Record]:
    """Ejecuta una consulta y devuelve sus filas."""

    async def run() -> list[asyncpg.Record]:
        async with database() as connection:
            return await connection.fetch(statement, *args)

    return asyncio.run(run())


def execute(statement: str, *args: Any) -> None:
    """Ejecuta una sentencia sin resultado."""

    async def run() -> None:
        async with database() as connection:
            await connection.execute(statement, *args)

    asyncio.run(run())


class Checker:
    """Cuenta aciertos y fallos, imprime cada comprobación y decide el código de salida."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.failures: list[str] = []
        self.total = 0

    def section(self, name: str) -> None:
        """Encabezado de un bloque de comprobaciones."""
        print(f"\n== {name}")

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        """Registra una comprobación."""
        self.total += 1
        print(("PASS " if condition else "FAIL ") + name + ("" if condition else f"  -> {detail}"))
        if not condition:
            self.failures.append(name)
        return condition

    def finish(self) -> None:
        """Resumen final; sale con 1 si algo falló."""
        print(f"\n{self.title}: {self.total - len(self.failures)}/{self.total} correctas")
        if self.failures:
            print("Fallos:", *self.failures, sep="\n  - ")
            sys.exit(1)
