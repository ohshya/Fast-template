"""Inyección en logs, vida máxima de sesión, cookie robada tras logout y X-Forwarded-For."""

import sys
from uuid import UUID, uuid4

import httpx
from fastapi_idempotency import DEFAULT_HEADER_NAME

from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE
from checks.common import Checker, admin, client, dev_client, execute, login, query, tag


def permission_id(dev: httpx.Client, key: str) -> int:
    """Identificador del permiso con esa clave en el catálogo; sale si no existe."""
    for item in dev.get("/api/system/permissions").json():
        if item["key"] == key:
            return int(item["id"])
    sys.exit(f"El catálogo de permisos no tiene '{key}'")


def create_user(dev: httpx.Client, username: str, password: str, role_id: str | None = None) -> str:
    """Crea un usuario y devuelve su id; sale si el servidor no responde 201."""
    body: dict[str, object] = {"username": username, "password": password}
    if role_id is not None:
        body["role_id"] = role_id
    response = dev.post("/api/users/", json=body)
    if response.status_code != 201:
        sys.exit(f"No se pudo crear {username}: {response.status_code} {response.text}")
    return str(response.json()["id"])


def log_injection(checker: Checker, dev: httpx.Client) -> None:
    """Un usuario con saltos de línea o escapes ANSI no llega al registro ni lo falsifica."""
    marker = f"FORGED{tag()}"
    malicious = f"evil\n{marker}\x1b[31m"
    with client() as session:
        response = session.post(
            "/api/auth/login", json={"username": malicious, "password": f"Mala{tag()}1"}
        )
    checker.check("el login falla con 401", response.status_code == 401, response.text)
    events = dev.get("/api/events/", params={"search": marker, "size": 5}).json()["items"]
    checker.check("el texto del usuario malicioso no se guarda", not events, str(events))
    failed = dev.get("/api/events/", params={"error_code": "AUT_001", "size": 5}).json()["items"]
    checker.check(
        "el intento sí queda registrado, con el nombre neutro",
        any("<inválido>" in event["message"] for event in failed),
        str([event["message"] for event in failed]),
    )


def session_lifetime(checker: Checker, dev: httpx.Client) -> None:
    """Una sesión deja de servir a los 30 días, aunque el token de acceso no haya caducado."""
    suffix = tag()
    username, password = f"life{suffix}", f"Prueba{suffix}1"
    user_id = create_user(dev, username, password)
    with client() as victim:
        response = login(victim, username, password)
        if response.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión como {username}: {response.status_code}")
        checker.check(
            "sesion recien abierta funciona", victim.get("/api/auth/me").status_code == 200
        )
        execute(
            "update user_sessions set created_at = now() - interval '31 days' where user_id = $1",
            UUID(user_id),
        )
        checker.check(
            "a los 31 dias la sesion no sirve aunque el token no haya caducado",
            victim.get("/api/auth/me").status_code == 401,
        )
        checker.check(
            "y tampoco se puede renovar", victim.post("/api/auth/refresh").status_code == 401
        )


def stolen_cookie_idempotency(checker: Checker, dev: httpx.Client) -> None:
    """La respuesta guardada por una clave de idempotencia no sirve con la sesión ya cerrada."""
    suffix = tag()
    username, password = f"rob{suffix}", f"Prueba{suffix}1"
    create_permission = permission_id(dev, "roles.create")
    role = dev.post(
        "/api/roles/", json={"name": f"Rob{suffix}", "permissions": [create_permission]}
    )
    if role.status_code != 201:
        sys.exit(f"No se pudo crear el rol: {role.status_code} {role.text}")
    create_user(dev, username, password, role.json()["id"])

    with client() as thief:
        response = login(thief, username, password)
        if response.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión como {username}: {response.status_code}")
        access_token = thief.cookies.get(ACCESS_COOKIE)
        refresh_token = thief.cookies.get(REFRESH_COOKIE)
        key = {DEFAULT_HEADER_NAME: str(uuid4())}
        body = {"name": f"Secreto{suffix}", "permissions": []}
        first = thief.post("/api/roles/", json=body, headers=key)
        thief.post("/api/auth/logout")

    stolen = {"Cookie": f"{ACCESS_COOKIE}={access_token}; {REFRESH_COOKIE}={refresh_token}"}
    with client() as attacker:
        replay = attacker.post("/api/roles/", json=body, headers={**stolen, **key})
    checker.check(
        "con la sesion cerrada, la cookie robada no recibe la respuesta guardada",
        first.status_code == 201 and replay.status_code == 401,
        f"{first.status_code} {replay.status_code} {replay.text[:120]}",
    )


def forwarded_for_from_trusted_proxy(checker: Checker) -> None:
    """Desde la dirección de confianza del proxy, X-Forwarded-For fija la IP guardada."""
    username, password = admin()
    spoofed = "203.0.113.9"
    with client() as session:
        response = session.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"X-Forwarded-For": spoofed},
        )
        if response.status_code != 200:
            sys.exit(f"No se pudo iniciar sesión como {username}: {response.status_code}")
        user_id = session.get("/api/auth/me").json()["id"]
    rows = query(
        "select ip_address from user_sessions where user_id = $1 order by created_at desc limit 1",
        UUID(user_id),
    )
    stored = rows[0]["ip_address"] if rows else None
    checker.check(
        "el proxy de confianza fija la IP del cliente con X-Forwarded-For",
        stored == spoofed,
        f"ip guardada: {stored}",
    )


def main() -> None:
    """Lanza las cuatro comprobaciones contra el servidor en marcha."""
    checker = Checker("Sesiones y registro")
    dev = dev_client()
    checker.section("1. Inyeccion en logs")
    log_injection(checker, dev)
    checker.section("2. Vida maxima de la sesion (30 dias)")
    session_lifetime(checker, dev)
    checker.section("3. Cookie robada tras cerrar sesion e idempotencia")
    stolen_cookie_idempotency(checker, dev)
    checker.section("4. X-Forwarded-For desde el proxy de confianza")
    forwarded_for_from_trusted_proxy(checker)
    checker.finish()


if __name__ == "__main__":
    main()
