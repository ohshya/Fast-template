"""Idempotencia de las escrituras: uv run python -m checks.idempotency."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt

from app.core.security import ACCESS_COOKIE, ALGORITHM, REFRESH_COOKIE
from app.settings import settings
from checks.common import BASE_URL, Checker, admin, client, code_of, dev_client, tag

COPIES = 10


def keyed(key: str) -> dict[str, str]:
    """Cabecera Idempotency-Key."""
    return {"Idempotency-Key": key}


def cookie_header(values: dict[str, str]) -> dict[str, str]:
    """Cabecera Cookie con solo las cookies indicadas."""
    return {"Cookie": "; ".join(f"{name}={value}" for name, value in values.items())}


def replayed(response: httpx.Response) -> bool:
    """Si la respuesta es la repetición de una guardada."""
    return response.headers.get("idempotent-replayed") == "true"


def create_role(
    session: httpx.Client, name: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    """POST de un rol sin permisos."""
    return session.post("/api/roles/", json={"name": name, "permissions": []}, headers=headers)


def count_roles(session: httpx.Client, name: str) -> int:
    """Roles cuyo nombre contiene el texto dado, o -1 si el listado falla."""
    response = session.get("/api/roles/", params={"search": name})
    return int(response.json()["total"]) if response.status_code == 200 else -1


def expired_access_cookie(session: httpx.Client) -> str:
    """Token de acceso ya caducado de la sesión abierta, firmado como lo hace el servidor."""
    user = session.get("/api/auth/me").json()
    opened = session.get("/api/auth/sessions").json()
    current = next(item for item in opened if item["is_current"])
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": user["id"],
        "session": current["id"],
        "jti": str(uuid4()),
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=30),
    }
    return jwt.encode(claims, settings.key("jwt"), algorithm=ALGORITHM)


def automatic_window(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Sin clave, la misma escritura repetida enseguida devuelve la respuesta guardada."""
    checks.section("Repetición automática (sin clave)")
    name = f"R0-{run_id}"
    first = create_role(dev, name)
    second = create_role(dev, name)
    checks.check(
        "primera vez: 201 sin marca de repetición",
        first.status_code == 201 and not replayed(first),
        first.text,
    )
    checks.check(
        "idéntica enseguida: misma respuesta e Idempotent-Replayed",
        second.status_code == 201 and replayed(second) and second.json() == first.json(),
        second.text,
    )
    checks.check("el rol se creó una sola vez", count_roles(dev, name) == 1, name)
    other = create_role(dev, f"R0b-{run_id}")
    checks.check(
        "otro cuerpo no se confunde con la anterior",
        other.status_code == 201 and not replayed(other),
        other.text,
    )


def explicit_key(checks: Checker, dev: httpx.Client, run_id: str) -> str:
    """Reintento con la misma clave y el mismo o distinto cuerpo. Devuelve el id del rol creado."""
    checks.section("Clave explícita")
    key = str(uuid4())
    name = f"R1-{run_id}"
    first = create_role(dev, name, keyed(key))
    retry = create_role(dev, name, keyed(key))
    checks.check(
        "primera vez con clave: 201 sin marca de repetición",
        first.status_code == 201 and not replayed(first),
        first.text,
    )
    checks.check(
        "reintento con la misma clave y cuerpo: misma respuesta e Idempotent-Replayed",
        retry.status_code == 201 and replayed(retry) and retry.json() == first.json(),
        retry.text,
    )
    checks.check("el rol se creó una sola vez", count_roles(dev, name) == 1, name)
    other = create_role(dev, f"R2-{run_id}", keyed(key))
    checks.check(
        "la misma clave con otro cuerpo -> 422 IDM_002",
        other.status_code == 422 and code_of(other) == "IDM_002",
        other.text,
    )
    checks.check("el cuerpo rechazado no creó nada", count_roles(dev, f"R2-{run_id}") == 0)
    return first.json().get("id", "") if first.status_code == 201 else ""


def invalid_keys(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """La clave debe tener entre 1 y 255 caracteres."""
    checks.section("Claves no válidas")
    r = create_role(dev, f"R3-{run_id}", keyed(""))
    checks.check(
        "clave vacía -> 422 IDM_003", r.status_code == 422 and code_of(r) == "IDM_003", r.text
    )
    r = create_role(dev, f"R3a-{run_id}", keyed("x" * 255))
    checks.check("clave de 255 caracteres (el máximo) -> 201", r.status_code == 201, r.text)
    r = create_role(dev, f"R3b-{run_id}", keyed("x" * 256))
    checks.check(
        "clave de 256 caracteres -> 422 IDM_003",
        r.status_code == 422 and code_of(r) == "IDM_003",
        r.text,
    )


def error_with_key(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Un error 4xx con clave queda guardado: el cuerpo corregido necesita una clave nueva."""
    checks.section("Un 4xx con clave queda guardado")
    key = str(uuid4())
    bad = create_role(dev, "", keyed(key))
    checks.check(
        "cuerpo no válido (nombre vacío) -> 422 VAL_422",
        bad.status_code == 422 and code_of(bad) == "VAL_422",
        bad.text,
    )
    name = f"R4-{run_id}"
    same_key = create_role(dev, name, keyed(key))
    checks.check(
        "el cuerpo corregido con la MISMA clave -> 422 IDM_002",
        same_key.status_code == 422 and code_of(same_key) == "IDM_002",
        same_key.text,
    )
    new_key = create_role(dev, name, keyed(str(uuid4())))
    checks.check(
        "el cuerpo corregido con una clave NUEVA se crea (201)",
        new_key.status_code == 201,
        new_key.text,
    )


def other_session(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """La clave se guarda por sesión: otra sesión puede usar la misma sin chocar."""
    checks.section("La clave es por sesión")
    other = dev_client()
    key = str(uuid4())
    first = create_role(dev, f"R5a-{run_id}", keyed(key))
    second = create_role(other, f"R5b-{run_id}", keyed(key))
    checks.check("sesión A con la clave: 201", first.status_code == 201, first.text)
    checks.check(
        "sesión B con la misma clave y otro cuerpo: 201, no choca ni repite",
        second.status_code == 201 and not replayed(second),
        second.text,
    )


def other_methods(checks: Checker, dev: httpx.Client, role_id: str) -> None:
    """PATCH y DELETE también se repiten; GET ignora la clave."""
    checks.section("PATCH y DELETE también, GET no")
    key = str(uuid4())
    body = {"description": "x"}
    first = dev.patch(f"/api/roles/{role_id}", json=body, headers=keyed(key))
    retry = dev.patch(f"/api/roles/{role_id}", json=body, headers=keyed(key))
    checks.check(
        "PATCH con clave: el reintento repite la respuesta",
        first.status_code == 200
        and not replayed(first)
        and retry.status_code == 200
        and replayed(retry)
        and retry.json() == first.json(),
        retry.text,
    )
    key = str(uuid4())
    first = dev.delete(f"/api/roles/{role_id}", headers=keyed(key))
    retry = dev.delete(f"/api/roles/{role_id}", headers=keyed(key))
    checks.check(
        "DELETE con clave: el reintento repite el 200 en vez de dar 404",
        first.status_code == 200 and retry.status_code == 200 and replayed(retry),
        f"{first.status_code} {retry.status_code} {retry.text}",
    )
    r = dev.get("/api/roles/", headers=keyed(key))
    checks.check(
        "GET con clave: se ignora (200 y sin repetición)",
        r.status_code == 200 and not replayed(r),
        r.text,
    )


def after_expired_access(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Un 401 por acceso caducado no se repite al reintentar con la sesión renovada."""
    checks.section("Escritura tras caducar el token de acceso")
    refresh = dev.cookies.get(REFRESH_COOKIE) or ""
    only_refresh = cookie_header({REFRESH_COOKIE: refresh})

    key = str(uuid4())
    name = f"R6-{run_id}"
    first = create_role(client(), name, {**keyed(key), **only_refresh})
    checks.check(
        "con solo la cookie de refresh y clave -> 401 AUT_002",
        first.status_code == 401 and code_of(first) == "AUT_002",
        first.text,
    )
    retry = create_role(dev, name, keyed(key))
    checks.check(
        "con sesión válida y la MISMA clave se ejecuta (201, no repite el 401)",
        retry.status_code == 201 and not replayed(retry),
        retry.text,
    )
    checks.check("el rol se creó una sola vez", count_roles(dev, name) == 1, name)

    name = f"R6b-{run_id}"
    first = create_role(client(), name, only_refresh)
    checks.check(
        "con solo la cookie de refresh y sin clave -> 401 AUT_002",
        first.status_code == 401 and code_of(first) == "AUT_002",
        first.text,
    )
    retry = create_role(dev, name)
    checks.check(
        "con sesión válida y sin clave se ejecuta (201, no repite el 401)",
        retry.status_code == 201 and not replayed(retry),
        retry.text,
    )

    renewing = dev_client()
    cookies = {
        ACCESS_COOKIE: expired_access_cookie(renewing),
        REFRESH_COOKIE: renewing.cookies.get(REFRESH_COOKIE) or "",
    }
    key = str(uuid4())
    name = f"R7-{run_id}"
    first = create_role(client(), name, {**keyed(key), **cookie_header(cookies)})
    checks.check(
        "con el token de acceso caducado y clave -> 401 AUT_003",
        first.status_code == 401 and code_of(first) == "AUT_003",
        first.text,
    )
    renewed = renewing.post("/api/auth/refresh")
    checks.check("renovar con el refresh -> 200", renewed.status_code == 200, renewed.text)
    retry = create_role(renewing, name, keyed(key))
    checks.check(
        "tras renovar, la MISMA clave se ejecuta (201, no repite el 401)",
        retry.status_code == 201 and not replayed(retry),
        retry.text,
    )
    checks.check("el rol se creó una sola vez", count_roles(renewing, name) == 1, name)


async def simultaneous(key: str, name: str) -> list[tuple[int, bool]]:
    """Lanza COPIES escrituras idénticas con la misma clave a la vez: (estado, es repetición)."""
    username, password = admin()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as http:
        signed = await http.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        if signed.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión como {username}: {signed.status_code}")

        async def once() -> tuple[int, bool]:
            reply = await http.post(
                "/api/roles/", json={"name": name, "permissions": []}, headers=keyed(key)
            )
            return reply.status_code, replayed(reply)

        return list(await asyncio.gather(*(once() for _ in range(COPIES))))


def same_key_at_once(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Envíos simultáneos con la misma clave se ejecutan una sola vez."""
    checks.section("Envíos simultáneos con la misma clave")
    name = f"Doble-{run_id}"
    results = asyncio.run(simultaneous(str(uuid4()), name))
    executed = [status for status, repeated in results if not repeated]
    checks.check(
        f"{COPIES} envíos simultáneos: todos 201",
        all(status == 201 for status, _ in results),
        str(results),
    )
    checks.check(
        "solo uno se ejecuta; los demás repiten su respuesta", len(executed) == 1, str(results)
    )
    checks.check("el rol se creó una sola vez", count_roles(dev, name) == 1, name)


def main() -> None:
    """Recorre los escenarios de idempotencia con datos propios y fija el código de salida."""
    checks = Checker("idempotency")
    dev = dev_client()
    run_id = tag()
    automatic_window(checks, dev, run_id)
    role_id = explicit_key(checks, dev, run_id)
    invalid_keys(checks, dev, run_id)
    error_with_key(checks, dev, run_id)
    other_session(checks, dev, run_id)
    other_methods(checks, dev, role_id)
    after_expired_access(checks, dev, run_id)
    same_key_at_once(checks, dev, run_id)
    checks.finish()


if __name__ == "__main__":
    main()
