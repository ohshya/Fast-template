"""Límite de intentos de login y cambio de contraseña: uv run python -m checks.login."""

import asyncio
import sys
from collections import Counter

import httpx

from checks.common import (
    BASE_URL,
    Checker,
    client,
    code_of,
    dev_client,
    error_of,
    execute,
    fields_of,
    login,
    query,
    tag,
)

BURST = 40


def wrong_password() -> str:
    """Contraseña incorrecta distinta cada vez: una petición idéntica se repetiría sin evaluarse."""
    return f"Mala{tag()}{tag()}"


def fresh_password() -> str:
    """Contraseña válida según la política, distinta en cada ejecución."""
    return f"Pw{tag()}{tag()}9"


def reset() -> None:
    """Vacía los intentos de login y las respuestas de idempotencia guardadas."""
    execute("DELETE FROM login_attempts; DELETE FROM fastapi_idempotency_requests")


def stored_attempts(username: str) -> int:
    """Filas de login_attempts que tiene un usuario."""
    rows = query("SELECT count(*) AS total FROM login_attempts WHERE username = $1", username)
    return int(rows[0]["total"])


def failures(session: httpx.Client, username: str, count: int) -> list[httpx.Response]:
    """Logins seguidos con contraseñas incorrectas y todas distintas."""
    return [login(session, username, wrong_password()) for _ in range(count)]


def create_user(dev: httpx.Client, username: str, password: str) -> str:
    """Crea un usuario sin rol y devuelve su id; sin él el script no puede seguir."""
    response = dev.post("/api/users/", json={"username": username, "password": password})
    if response.status_code != 201:
        sys.exit(f"No se pudo crear {username}: {response.status_code} {response.text}")
    return response.json()["id"]


def policy(dev: httpx.Client) -> tuple[int, int, int]:
    """Límites que declara el servidor: intentos por usuario, por IP y ventana en segundos."""
    response = dev.get("/api/system/info")
    if response.status_code != 200:
        sys.exit(f"No se pudo leer /api/system/info: {response.status_code} {response.text}")
    info = response.json()
    return (
        int(info["login_attempts"]),
        int(info["login_attempts_per_ip"]),
        int(info["login_window_seconds"]),
    )


def lockout(
    checks: Checker, anon: httpx.Client, name: str, password: str, attempts: int, window: int
) -> None:
    """Tras el máximo de fallos seguidos el usuario se bloquea, aunque luego acierte la clave."""
    checks.section("Bloqueo tras fallos seguidos")
    reset()
    results = failures(anon, name, attempts + 2)
    statuses = [result.status_code for result in results]
    checks.check(
        f"{attempts} fallos seguidos dan 401 y los siguientes 429",
        statuses == [401] * attempts + [429] * 2,
        str(statuses),
    )
    codes = [code_of(result) for result in results]
    checks.check(
        "los códigos son AUT_001 y después SYS_429",
        codes == ["AUT_001"] * attempts + ["SYS_429"] * 2,
        str(codes),
    )
    stored = stored_attempts(name)
    checks.check(
        f"filas guardadas: {attempts}; los 429 no dejan rastro", stored == attempts, str(stored)
    )
    r = login(anon, name, password)
    checks.check(
        "con la clave correcta y ya bloqueado: 429 (el bloqueo se aplica antes de mirar la clave)",
        r.status_code == 429 and code_of(r) == "SYS_429",
        r.text,
    )
    wait = error_of(r).get("details", {}).get("retry_after_seconds", 0)
    checks.check("el 429 indica cuántos segundos esperar", 1 <= wait <= window, str(wait))


def success_clears(checks: Checker, name: str, password: str, attempts: int) -> None:
    """Un login correcto olvida los fallos anteriores del usuario."""
    checks.section("Un login correcto olvida los fallos")
    reset()
    visitor = client()
    failures(visitor, name, attempts - 1)
    r = login(visitor, name, password)
    checks.check(
        f"tras {attempts - 1} fallos, la clave correcta entra", r.status_code == 200, r.text
    )
    stored = stored_attempts(name)
    checks.check("no quedan filas del usuario", stored == 0, str(stored))


def password_change(
    checks: Checker, name: str, password: str, new_password: str, attempts: int
) -> httpx.Client:
    """El cambio de contraseña comparte el límite del login. Devuelve la sesión del usuario."""
    checks.section("Cambio de contraseña con el mismo límite")
    reset()
    session = client()
    r = login(session, name, password)
    if not checks.check("login del usuario de prueba", r.status_code == 200, r.text):
        return session
    results = [
        session.post(
            "/api/auth/password",
            json={"current_password": wrong_password(), "new_password": new_password},
        )
        for _ in range(attempts + 2)
    ]
    outcomes = [(result.status_code, code_of(result)) for result in results]
    expected = [(422, "VAL_422")] * attempts + [(429, "SYS_429")] * 2
    checks.check(
        f"clave actual mala x{attempts + 2}: {attempts} veces 422 y después 429",
        outcomes == expected,
        str(outcomes),
    )
    checks.check(
        "el 422 señala el campo current_password",
        "current_password" in fields_of(results[0]),
        results[0].text,
    )
    reset()
    r = session.post(
        "/api/auth/password", json={"current_password": password, "new_password": new_password}
    )
    checks.check("cambio correcto", r.status_code == 200, r.text)
    stored = stored_attempts(name)
    checks.check("tras el cambio correcto no quedan filas del usuario", stored == 0, str(stored))
    return session


def no_enumeration(checks: Checker, anon: httpx.Client, name: str, run_id: str) -> None:
    """Un usuario inexistente responde igual que una clave mala de un usuario real."""
    checks.section("Usuario inexistente")
    ghost = login(anon, f"nadie{run_id}", wrong_password())
    real = login(anon, name, wrong_password())
    checks.check(
        "usuario inexistente -> 401 AUT_001",
        ghost.status_code == 401 and code_of(ghost) == "AUT_001",
        ghost.text,
    )
    same = (
        ghost.status_code == real.status_code
        and error_of(ghost).get("code") == error_of(real).get("code")
        and error_of(ghost).get("message") == error_of(real).get("message")
    )
    checks.check(
        "responde igual que una clave mala de un usuario real (no revela quién existe)",
        same,
        f"{ghost.text} | {real.text}",
    )


def inactive_user(
    checks: Checker,
    anon: httpx.Client,
    dev: httpx.Client,
    session: httpx.Client,
    user_id: str,
    name: str,
    password: str,
) -> None:
    """Un usuario desactivado no entra, su intento cuenta y su sesión abierta deja de servir."""
    checks.section("Usuario desactivado")
    reset()
    r = dev.patch(f"/api/users/{user_id}", json={"is_active": False})
    checks.check("desactivar usuario", r.status_code == 200, r.text)
    r = login(anon, name, password)
    checks.check(
        "login del desactivado con la clave correcta -> 403 AUT_006",
        r.status_code == 403 and code_of(r) == "AUT_006",
        r.text,
    )
    stored = stored_attempts(name)
    checks.check("su intento queda guardado (cuenta como intento)", stored == 1, str(stored))
    r = session.get("/api/auth/me")
    checks.check(
        "su sesión abierta deja de servir -> 403 AUT_006",
        r.status_code == 403 and code_of(r) == "AUT_006",
        r.text,
    )


def ip_limit(checks: Checker, anon: httpx.Client, run_id: str, per_ip: int) -> None:
    """El límite por IP cuenta los intentos de todos los usuarios y se aplica en el siguiente."""
    checks.section("Límite por IP")
    reset()
    probe = f"ip{run_id}a"
    login(anon, probe, wrong_password())
    rows = query("SELECT ip FROM login_attempts WHERE username = $1", probe)
    if not checks.check("un intento deja su fila con la IP de origen", len(rows) == 1, str(rows)):
        return
    origin = str(rows[0]["ip"])
    reset()
    execute(
        "INSERT INTO login_attempts (id, ip, username, created_at) "
        "SELECT gen_random_uuid(), $1::text, 'relleno' || n::text, now() "
        "FROM generate_series(1, $2::int) AS n",
        origin,
        per_ip - 1,
    )
    last_allowed = login(anon, f"ip{run_id}b", wrong_password())
    checks.check(
        f"con {per_ip - 1} intentos de la IP, el número {per_ip} todavía se evalúa (401)",
        last_allowed.status_code == 401 and code_of(last_allowed) == "AUT_001",
        last_allowed.text,
    )
    over = login(anon, f"ip{run_id}c", wrong_password())
    checks.check(
        f"el intento {per_ip + 1} de la IP -> 429 aunque sea de otro usuario",
        over.status_code == 429 and code_of(over) == "SYS_429",
        over.text,
    )


async def simultaneous_failures(username: str, run_id: str) -> Counter[tuple[int, str | None]]:
    """Lanza BURST logins con clave mala a la vez y cuenta (estado, código) de las respuestas."""

    async def attempt(http: httpx.AsyncClient, index: int) -> tuple[int, str | None]:
        reply = await http.post(
            "/api/auth/login",
            json={"username": username, "password": f"Mala{run_id}{index:05d}"},
        )
        return reply.status_code, code_of(reply)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as http:
        return Counter(await asyncio.gather(*(attempt(http, index) for index in range(BURST))))


def burst(
    checks: Checker, anon: httpx.Client, dev: httpx.Client, run_id: str, attempts: int
) -> None:
    """Intentos simultáneos: se evalúan como mucho `attempts` y el resto recibe 429."""
    checks.section("Ráfaga de intentos simultáneos")
    name = f"b{run_id}"
    create_user(dev, name, fresh_password())
    reset()
    outcomes = asyncio.run(simultaneous_failures(name, run_id))
    evaluated = outcomes[(401, "AUT_001")]
    limited = outcomes[(429, "SYS_429")]
    stored = stored_attempts(name)
    summary = str(dict(outcomes))
    checks.check(
        f"{BURST} intentos simultáneos evalúan como mucho {attempts}",
        evaluated <= attempts,
        summary,
    )
    checks.check(
        "todos los demás reciben 429, sin otros resultados", evaluated + limited == BURST, summary
    )
    checks.check(
        "cada intento evaluado deja su fila y los 429 no dejan rastro",
        stored == evaluated,
        f"{stored} filas, {evaluated} evaluados",
    )
    r = login(anon, name, wrong_password())
    checks.check(
        "uno más tras la ráfaga: 429 si el cupo está lleno",
        stored < attempts or r.status_code == 429,
        r.text,
    )


def main() -> None:
    """Recorre los escenarios de bloqueo con usuarios propios y fija el código de salida."""
    checks = Checker("login")
    reset()
    dev = dev_client()
    run_id = tag()
    attempts, per_ip, window = policy(dev)
    anon = client()
    name, password, new_password = f"l{run_id}", fresh_password(), fresh_password()
    user_id = create_user(dev, name, password)
    lockout(checks, anon, name, password, attempts, window)
    success_clears(checks, name, password, attempts)
    session = password_change(checks, name, password, new_password, attempts)
    no_enumeration(checks, anon, name, run_id)
    inactive_user(checks, anon, dev, session, user_id, name, new_password)
    ip_limit(checks, anon, run_id, per_ip)
    burst(checks, anon, dev, run_id, attempts)
    reset()
    checks.finish()


if __name__ == "__main__":
    main()
