"""Comportamiento del núcleo contra un servidor en marcha: uv run python -m checks.smoke."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from app.core.security import ACCESS_COOKIE, ACCESS_MINUTES, REFRESH_COOKIE, REFRESH_DAYS
from app.settings import settings
from checks.common import BASE_URL, Checker, admin, client, code_of, fields_of, iso, login, tag

WRITES = 25


@dataclass
class Ana:
    """Usuario con un rol de permisos limitados, creado por el script."""

    session: httpx.Client
    name: str
    password: str
    role_id: str


def wrong_password() -> str:
    """Contraseña incorrecta distinta cada vez: una petición idéntica se repetiría sin evaluarse."""
    return f"Mala{uuid4().hex[:10]}"


def fresh_password() -> str:
    """Contraseña válida según la política, distinta en cada ejecución."""
    return f"Pw{uuid4().hex[:10]}9"


def cookie_header(values: dict[str, str]) -> dict[str, str]:
    """Cabecera Cookie con solo las cookies indicadas."""
    return {"Cookie": "; ".join(f"{name}={value}" for name, value in values.items())}


def surface(checks: Checker, anon: httpx.Client) -> None:
    """Rutas públicas y errores que no dependen de la sesión."""
    checks.section("Superficie pública")
    r = anon.get("/api/system/health")
    up = r.status_code == 200 and r.json()["database"] == "up"
    checks.check("health público 200", up, r.text)
    r = anon.get("/api/system/info")
    denied = r.status_code == 401 and code_of(r) == "AUT_002"
    checks.check("sin sesión -> 401 AUT_002", denied, r.text)
    checks.check("X-Request-ID en la respuesta", bool(r.headers.get("x-request-id")))
    r = anon.get("/api/nada")
    missing = r.status_code == 404 and code_of(r) == "SYS_404"
    checks.check("ruta inexistente -> 404 SYS_404", missing, r.text)
    r = anon.put("/api/system/health")
    not_allowed = r.status_code == 405 and code_of(r) == "SYS_405"
    checks.check("método no permitido -> 405 SYS_405", not_allowed, r.text)


def sign_in(checks: Checker, anon: httpx.Client, ghost: str) -> httpx.Client:
    """Login erróneo y correcto, validación de entrada, cookies y perfil. Devuelve la sesión dev."""
    checks.section("Inicio de sesión")
    username, password = admin()
    r = login(anon, ghost, wrong_password())
    rejected = r.status_code == 401 and code_of(r) == "AUT_001"
    checks.check("login con clave mala -> 401 AUT_001", rejected, r.text)
    r = login(anon, "x" * 60, wrong_password())
    invalid = r.status_code == 422 and code_of(r) == "VAL_422"
    checks.check("username largo -> 422 VAL_422", invalid, r.text)
    checks.check("422 trae errores por campo", bool(fields_of(r)), r.text)

    dev = client()
    r = login(dev, username, password)
    if not checks.check("login dev 200", r.status_code == 200 and r.json()["dev"] is True, r.text):
        checks.finish()
    cookies = r.headers.get_list("set-cookie")
    attributes = [[part.strip().lower() for part in cookie.split(";")[1:]] for cookie in cookies]
    checks.check(
        "cookies httponly",
        len(cookies) == 2 and all("httponly" in each for each in attributes),
        str(cookies),
    )
    checks.check(
        "debug: cookies sin Secure y SameSite=lax",
        all("secure" not in each and "samesite=lax" in each for each in attributes),
        str(cookies),
    )
    names = sorted(cookie.split("=", 1)[0] for cookie in cookies)
    checks.check(
        "las cookies se llaman como el prefijo de APP_NAME",
        names == sorted([ACCESS_COOKIE, REFRESH_COOKIE]),
        str(names),
    )
    r = dev.get("/api/auth/me")
    granted = r.status_code == 200 and len(r.json()["permissions"]) > 10
    checks.check("me 200 con permisos", granted, r.text)
    return dev


def catalogs(checks: Checker, dev: httpx.Client) -> dict[str, int]:
    """Catálogos del sistema y error inesperado. Devuelve el id de cada permiso por su clave."""
    checks.section("Catálogos del sistema")
    r = dev.get("/api/system/permissions")
    listed = r.status_code == 200 and any(item["endpoint"] for item in r.json())
    if not checks.check("catálogo de permisos con endpoint", listed, r.text[:200]):
        checks.finish()
    ids: dict[str, int] = {item["key"]: item["id"] for item in r.json()}
    r = dev.get("/api/system/errors")
    checks.check("catálogo de errores", r.status_code == 200 and len(r.json()) > 20, r.text[:200])
    r = dev.get("/api/system/info")
    info: dict[str, Any] = r.json() if r.status_code == 200 else {}
    policies = (
        info.get("access_expire_minutes") == ACCESS_MINUTES
        and info.get("refresh_expire_days") == REFRESH_DAYS
    )
    checks.check("info trae las políticas de sesión", policies, r.text)
    r = dev.get("/api/system/test-error/500")
    unexpected = r.status_code == 500 and code_of(r) == "SYS_500" and "debug" in r.json()["error"]
    checks.check("excepción real -> 500 SYS_500 con detalle en debug", unexpected, r.text)
    return ids


def roles_and_users(checks: Checker, dev: httpx.Client, ids: dict[str, int], run_id: str) -> Ana:
    """Altas, duplicados y relaciones de roles y usuarios. Devuelve a ana, aún sin sesión."""
    checks.section("Roles y usuarios")
    granted = [ids["roles.list"], ids["roles.read"], ids["users.list"]]
    name = f"Vendedor-{run_id}"
    r = dev.post("/api/roles/", json={"name": name, "permissions": granted})
    if not checks.check("crear rol 201", r.status_code == 201, r.text):
        checks.finish()
    role = r.json()
    checks.check(
        "permisos guardados como lista de enteros ordenada",
        role["permissions"] == sorted(granted),
        str(role),
    )
    r = dev.get("/api/roles/", params={"search": name.lower()})
    found = r.status_code == 200 and r.json()["total"] == 1
    checks.check("búsqueda de roles sin distinguir mayúsculas", found, r.text)
    r = dev.post("/api/roles/", json={"name": name, "permissions": []})
    duplicated = r.status_code == 409 and code_of(r) == "SYS_409"
    checks.check("rol duplicado -> 409 SYS_409", duplicated, r.text)
    r = dev.post("/api/roles/", json={"name": f"Raro-{run_id}", "permissions": [999999]})
    unknown = r.status_code == 422 and code_of(r) == "ROL_004"
    checks.check("permiso desconocido -> 422 ROL_004", unknown, r.text)
    r = dev.patch(f"/api/roles/{role['id']}", json={"description": "Ventas"})
    edited = r.status_code == 200 and r.json()["description"] == "Ventas"
    checks.check("editar rol", edited, r.text)

    ana = Ana(session=client(), name=f"ana{run_id}", password=fresh_password(), role_id=role["id"])
    r = dev.post(
        "/api/users/",
        json={"username": ana.name, "password": ana.password, "role_id": role["id"]},
    )
    if not checks.check("crear usuario con rol 201", r.status_code == 201, r.text):
        checks.finish()
    r = dev.post("/api/users/", json={"username": ana.name, "password": ana.password})
    checks.check("usuario duplicado -> 409", r.status_code == 409, r.text)
    r = dev.post(
        "/api/users/",
        json={"username": f"zoe{run_id}", "password": ana.password, "role_id": str(uuid4())},
    )
    related = r.status_code == 422 and code_of(r) == "VAL_REL"
    checks.check("rol inexistente -> 422 VAL_REL", related, r.text)
    r = dev.delete(f"/api/roles/{role['id']}")
    in_use = r.status_code == 409 and code_of(r) == "ROL_003"
    checks.check("rol en uso no se elimina -> 409 ROL_003", in_use, r.text)
    return ana


def restricted_user(checks: Checker, ana: Ana, run_id: str) -> None:
    """Lo que ana puede y no puede hacer con los permisos de su rol."""
    checks.section("Permisos de un usuario con rol")
    r = login(ana.session, ana.name, ana.password)
    checks.check("login ana", r.status_code == 200, r.text)
    r = ana.session.get("/api/users/")
    checks.check("ana lista usuarios (users.list)", r.status_code == 200, r.text)
    r = ana.session.post(
        "/api/users/", json={"username": f"otro{run_id}", "password": fresh_password()}
    )
    forbidden = r.status_code == 403 and code_of(r) == "PRM_001"
    checks.check("ana no crea usuarios -> 403 PRM_001", forbidden, r.text)
    r = ana.session.get("/api/system/test-error/418")
    dev_only = r.status_code == 403 and code_of(r) == "PRM_002"
    checks.check("ruta solo dev -> 403 PRM_002", dev_only, r.text)


def idempotency(checks: Checker, dev: httpx.Client, run_id: str) -> str:
    """Repetición automática y claves explícitas. Devuelve el id del rol creado con repetición."""
    checks.section("Idempotencia")
    body = {"name": f"Idem-{run_id}", "permissions": []}
    first = dev.post("/api/roles/", json=body)
    second = dev.post("/api/roles/", json=body)
    checks.check(
        "idempotencia automática: misma respuesta y cabecera",
        first.status_code == 201
        and second.json() == first.json()
        and second.headers.get("idempotent-replayed") == "true",
        f"{first.text} | {second.text}",
    )
    key = {"Idempotency-Key": str(uuid4())}
    a = dev.post("/api/roles/", json={"name": f"K1-{run_id}", "permissions": []}, headers=key)
    b = dev.post("/api/roles/", json={"name": f"K2-{run_id}", "permissions": []}, headers=key)
    reused = a.status_code == 201 and b.status_code == 422 and code_of(b) == "IDM_002"
    checks.check("Idempotency-Key con otro cuerpo -> 422 IDM_002", reused, b.text)
    r = dev.post(
        "/api/roles/",
        json={"name": f"K3-{run_id}", "permissions": []},
        headers={"Idempotency-Key": "x" * 300},
    )
    too_long = r.status_code == 422 and code_of(r) == "IDM_003"
    checks.check("clave larga -> 422 IDM_003", too_long, r.text)
    return str(first.json().get("id", ""))


def origins(checks: Checker, dev: httpx.Client, anon: httpx.Client, run_id: str) -> None:
    """Escrituras con cabecera Origin y preflight de CORS."""
    checks.section("Origen y CORS")
    allowed = settings.cors_origins[0]
    own = BASE_URL.rstrip("/")
    r = dev.post(
        "/api/roles/",
        json={"name": f"Otro-{run_id}", "permissions": []},
        headers={"Origin": "https://evil.example"},
    )
    foreign = r.status_code == 403 and code_of(r) == "PRM_003"
    checks.check("origen ajeno -> 403 PRM_003", foreign, r.text)
    r = dev.post(
        "/api/roles/",
        json={"name": f"Otro2-{run_id}", "permissions": []},
        headers={"Origin": allowed},
    )
    checks.check("origen permitido pasa", r.status_code == 201, r.text)
    r = dev.post(
        "/api/roles/",
        json={"name": f"Otro3-{run_id}", "permissions": []},
        headers={"Origin": own},
    )
    checks.check("origen del propio servidor pasa", r.status_code == 201, r.text)
    r = anon.options(
        "/api/roles/",
        headers={
            "Origin": allowed,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "idempotency-key,content-type",
        },
    )
    allow_headers = r.headers.get("access-control-allow-headers", "").lower()
    checks.check(
        "preflight CORS con Idempotency-Key",
        r.status_code == 200 and "idempotency-key" in allow_headers,
        str(r.headers),
    )


def reversible_delete(
    checks: Checker, dev: httpx.Client, ana: Ana, role_id: str, run_id: str
) -> None:
    """Eliminar, listar eliminados, restaurar y borrar definitivamente un rol."""
    checks.section("Borrado reversible y definitivo")
    r = dev.delete(f"/api/roles/{role_id}")
    checks.check("eliminar rol reversible", r.status_code == 200, r.text)
    r = dev.get("/api/roles/", params={"deleted": "true", "search": f"Idem-{run_id}"})
    listed = r.status_code == 200 and any(item["id"] == role_id for item in r.json()["items"])
    checks.check("listar eliminados", listed, r.text[:200])
    r = dev.post(f"/api/roles/{role_id}/restore")
    restored = r.status_code == 200 and r.json()["deleted_at"] is None
    checks.check("restaurar rol", restored, r.text)
    r = dev.delete(f"/api/roles/{role_id}/hard")
    checks.check("borrado definitivo (dev)", r.status_code == 200, r.text)
    r = ana.session.delete(f"/api/roles/{role_id}/hard")
    checks.check("borrado definitivo prohibido a ana", r.status_code == 403, r.text)


def audit(checks: Checker, dev: httpx.Client, role_id: str, ghost: str) -> None:
    """Registro de eventos: listado, historial, estadísticas, login fallido y cadena."""
    checks.section("Auditoría")
    r = dev.get("/api/events/", params={"size": 5})
    checks.check(
        "auditoría lista eventos", r.status_code == 200 and r.json()["total"] > 10, r.text[:200]
    )
    r = dev.get(f"/api/events/history/roles/{role_id}")
    checks.check(
        "historial del rol (creación+edición)",
        r.status_code == 200 and r.json()["total"] >= 2,
        r.text[:300],
    )
    r = dev.get("/api/events/stats")
    checks.check("estadísticas", r.status_code == 200 and r.json()["total"] > 10, r.text[:200])
    r = dev.get(
        "/api/events/", params={"category": "security", "error_code": "AUT_001", "search": ghost}
    )
    checks.check(
        "login fallido quedó auditado",
        r.status_code == 200 and r.json()["total"] >= 1,
        r.text[:200],
    )
    r = dev.get("/api/events/verify")
    intact = r.status_code == 200 and r.json()["intact"] is True
    checks.check("cadena de eventos intacta", intact, r.text)


def sessions(checks: Checker, ana: Ana) -> None:
    """Listado de sesiones propias, rotación del refresh y detección de su reutilización."""
    checks.section("Sesiones y refresh")
    r = ana.session.get("/api/auth/sessions")
    own = r.status_code == 200 and len(r.json()) == 1 and "location" not in r.json()[0]
    checks.check("ana lista sus sesiones", own, r.text)
    old_refresh = ana.session.cookies.get(REFRESH_COOKIE) or ""
    r = ana.session.post("/api/auth/refresh")
    rotated = r.status_code == 200 and ana.session.cookies.get(REFRESH_COOKIE) != old_refresh
    checks.check("refresh rota tokens", rotated, r.text)
    thief = client()
    r = thief.post("/api/auth/refresh", headers=cookie_header({REFRESH_COOKIE: old_refresh}))
    reused = r.status_code == 401 and code_of(r) == "AUT_004"
    checks.check("reutilizar refresh -> 401 y sesión cerrada", reused, r.text)
    r = ana.session.get("/api/auth/me")
    checks.check("la sesión robada quedó revocada", r.status_code == 401, r.text)


def password_change(checks: Checker, ana: Ana) -> None:
    """Cambio de contraseña propio y cierre de sesión."""
    checks.section("Contraseña y cierre de sesión")
    session = client()
    login(session, ana.name, ana.password)
    r = session.post(
        "/api/auth/password",
        json={"current_password": wrong_password(), "new_password": fresh_password()},
    )
    checks.check("cambiar clave con la actual mala -> 422", r.status_code == 422, r.text)
    r = session.post(
        "/api/auth/password",
        json={"current_password": ana.password, "new_password": fresh_password()},
    )
    checks.check("cambiar clave", r.status_code == 200, r.text)
    r = session.post("/api/auth/logout")
    checks.check("logout", r.status_code == 200, r.text)
    r = session.get("/api/auth/me")
    checks.check("tras logout -> 401", r.status_code == 401, r.text)


def throttling(checks: Checker, anon: httpx.Client, dev: httpx.Client, run_id: str) -> None:
    """Demasiados intentos de login seguidos para un usuario."""
    checks.section("Límite de intentos de login")
    r = dev.get("/api/system/info")
    attempts = int(r.json()["login_attempts"])
    victim = f"n{run_id}"
    for _ in range(attempts + 1):
        login(anon, victim, wrong_password())
    r = login(anon, victim, wrong_password())
    limited = r.status_code == 429 and code_of(r) == "SYS_429"
    checks.check("demasiados intentos -> 429 SYS_429", limited, r.text)


def docs(checks: Checker, anon: httpx.Client) -> None:
    """Documentación de la API, que solo existe con DEBUG=true."""
    checks.section("Documentación en debug")
    r = anon.get("/docs")
    checks.check("debug: /docs disponible", r.status_code == 200)
    r = anon.get("/redoc")
    checks.check("/redoc no existe", r.status_code == 404)
    r = anon.get("/openapi.json")
    checks.check(
        "debug: /openapi.json disponible", r.status_code == 200 and "/api/roles/" in r.text
    )


async def burst_sequences(http: httpx.AsyncClient, stem: str) -> tuple[int, list[int]]:
    """Cuántos eventos dejaron las escrituras y las secuencias de todo el tramo que ocupan."""
    mine = await http.get("/api/events/", params={"search": stem, "size": 100})
    if mine.status_code != 200:
        return 0, []
    body: dict[str, Any] = mine.json()
    moments = [datetime.fromisoformat(item["created_at"]) for item in body["items"]]
    found: list[int] = []
    page = 1
    while moments:
        window = await http.get(
            "/api/events/",
            params={
                "date_from": iso(min(moments)),
                "date_to": iso(max(moments)),
                "order": "oldest",
                "size": 100,
                "page": page,
            },
        )
        if window.status_code != 200:
            break
        listing: dict[str, Any] = window.json()
        found += [item["sequence"] for item in listing["items"]]
        if page >= listing.get("pages", 1):
            break
        page += 1
    return int(body["total"]), found


async def concurrent_writes(checks: Checker, run_id: str) -> None:
    """Escrituras simultáneas: todas 201, cadena intacta y secuencias sin huecos."""
    checks.section("Concurrencia")
    username, password = admin()
    stem = f"Par{run_id}"
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as http:
        r = await http.post("/api/auth/login", json={"username": username, "password": password})
        if not checks.check("login dev para la concurrencia", r.status_code == 200, r.text):
            return
        replies = await asyncio.gather(
            *(
                http.post("/api/roles/", json={"name": f"{stem}-{i}", "permissions": []})
                for i in range(WRITES)
            )
        )
        failed = [reply.status_code for reply in replies if reply.status_code != 201]
        checks.check(f"{WRITES} escrituras concurrentes 201", not failed, str(failed))
        r = await http.get("/api/events/verify")
        checks.check(
            "cadena intacta tras la concurrencia",
            r.status_code == 200 and r.json()["intact"] is True,
            r.text,
        )
        own, sequences = await burst_sequences(http, stem)
        checks.check("cada escritura dejó su evento", own == WRITES, f"{own} eventos")
        first = sequences[0] if sequences else 0
        contiguous = sequences == list(range(first, first + len(sequences)))
        checks.check(
            "secuencias contiguas sin huecos",
            bool(sequences) and contiguous and len(sequences) >= own,
            str(sequences[:10]),
        )


def main() -> None:
    """Ejecuta las comprobaciones del núcleo y fija el código de salida."""
    checks = Checker("smoke")
    run_id = tag()
    anon = client()
    surface(checks, anon)
    dev = sign_in(checks, anon, f"x{run_id}")
    ids = catalogs(checks, dev)
    ana = roles_and_users(checks, dev, ids, run_id)
    restricted_user(checks, ana, run_id)
    idem_role_id = idempotency(checks, dev, run_id)
    origins(checks, dev, anon, run_id)
    reversible_delete(checks, dev, ana, idem_role_id, run_id)
    audit(checks, dev, ana.role_id, f"x{run_id}")
    sessions(checks, ana)
    password_change(checks, ana)
    throttling(checks, anon, dev, run_id)
    docs(checks, anon)
    asyncio.run(concurrent_writes(checks, run_id))
    checks.finish()


if __name__ == "__main__":
    main()
