"""Batería de un atacante externo: tokens falsos, CSRF, inyecciones, escalada, DoS, fuerza bruta."""

import asyncio
import http.client
import statistics
import sys
import time
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import jwt
from fastapi_idempotency import DEFAULT_HEADER_NAME, DEFAULT_REPLAYED_HEADER_NAME
from jwt.warnings import InsecureKeyLengthWarning

from app.core.security import ACCESS_COOKIE, ALGORITHM, REFRESH_COOKIE
from app.settings import settings
from checks.common import BASE_URL, Checker, client, code_of, dev_client, execute, login, tag

MANAGER_PERMISSIONS = (
    "users.list",
    "users.read",
    "users.create",
    "users.update",
    "users.password.reset",
    "roles.list",
    "roles.read",
    "roles.create",
    "roles.update",
)
JSON_HEADERS = {"Content-Type": "application/json"}
SECURITY_HEADERS = (
    "server",
    "x-powered-by",
    "cache-control",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "strict-transport-security",
    "content-security-policy",
)
ROUTE_ATTACKS = (
    ("GET", "//api/roles/"),
    ("POST", "//api/roles/"),
    ("GET", "/API/roles/"),
    ("GET", "/api/roles/../system/health"),
    ("GET", "/api/roles/%2e%2e/system/health"),
    ("GET", "/api%2Froles/"),
    ("HEAD", "/api/roles/"),
    ("TRACE", "/api/roles/"),
    ("GET", "/api/roles;x=1/"),
    ("GET", "/api/roles/?a=" + "x" * 9000),
)
BENIGN_ROUTES = ("/api%2Froles/", "/api/roles/?a=")


@dataclass
class Lab:
    """Usuarios de prueba: un admin sin ser dev, un gestor y un usuario básico."""

    suffix: str
    password: str
    dev: httpx.Client
    boss: httpx.Client
    manager: httpx.Client
    basic: httpx.Client
    roles: dict[str, dict[str, Any]]
    assignable: list[int]
    boss_id: str
    manager_id: str


def info(name: str, detail: str) -> None:
    """Dato que se muestra pero no puntúa."""
    print(f"INFO {name}: {detail}")


def cookie(session: httpx.Client, name: str) -> str:
    """Valor de una cookie de la sesión; sale si no está (¿DEBUG=false con http?)."""
    value = session.cookies.get(name)
    if value is None:
        sys.exit(f"La sesión no tiene la cookie {name}: el servidor debe correr con DEBUG=true.")
    return value


def sign_in(username: str, password: str) -> httpx.Client:
    """Cliente con la sesión de ese usuario abierta."""
    session = client()
    response = login(session, username, password)
    if response.status_code != 200:
        sys.exit(f"No se pudo iniciar sesión como {username}: {response.status_code}")
    return session


def create(session: httpx.Client, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Crea un registro de preparación; sale si el servidor no responde 201."""
    response = session.post(path, json=body)
    if response.status_code != 201:
        sys.exit(f"No se pudo preparar {path}: {response.status_code} {response.text}")
    return response.json()


def anonymous(method: str, path: str, **kwargs: Any) -> httpx.Response:
    """Petición sin sesión: el cliente nace y muere con ella."""
    with client() as session:
        return session.request(method, path, **kwargs)


def raw(method: str, path: str, headers: dict[str, str]) -> tuple[int, str]:
    """Petición HTTP sin que ninguna librería normalice la ruta."""
    target = urlsplit(BASE_URL)
    connection_class: type[http.client.HTTPConnection] = (
        http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_class(target.netloc, timeout=30)
    try:
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


def forge(claims: dict[str, Any], key: str | bytes, algorithm: str = ALGORITHM) -> str:
    """Token firmado como lo haría el atacante."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureKeyLengthWarning)
        return jwt.encode(claims, key, algorithm=algorithm)


def reset_login_attempts() -> None:
    """Borra los intentos de login para que el límite de la prueba anterior no estorbe."""
    execute("delete from login_attempts")


def prepare(suffix: str, password: str) -> Lab:
    """Crea los roles admin, gestor y básico con un usuario cada uno y abre sus sesiones."""
    dev = dev_client()
    catalog = dev.get("/api/system/permissions").json()
    ids = {item["key"]: item["id"] for item in catalog}
    assignable = [item["id"] for item in catalog if item["assignable"]]
    permissions = {
        "boss": assignable,
        "manager": [ids[key] for key in MANAGER_PERMISSIONS],
        "basic": [ids["users.list"]],
    }
    roles: dict[str, dict[str, Any]] = {}
    sessions: dict[str, httpx.Client] = {}
    for kind, granted in permissions.items():
        roles[kind] = create(
            dev, "/api/roles/", {"name": f"{kind}-{suffix}", "permissions": granted}
        )
        username = f"{kind}{suffix}"
        body = {"username": username, "password": password, "role_id": roles[kind]["id"]}
        create(dev, "/api/users/", body)
        sessions[kind] = sign_in(username, password)
    return Lab(
        suffix=suffix,
        password=password,
        dev=dev,
        boss=sessions["boss"],
        manager=sessions["manager"],
        basic=sessions["basic"],
        roles=roles,
        assignable=assignable,
        boss_id=sessions["boss"].get("/api/auth/me").json()["id"],
        manager_id=sessions["manager"].get("/api/auth/me").json()["id"],
    )


def forged_tokens(checker: Checker, lab: Lab) -> None:
    """Tokens falsificados de todo tipo contra /api/auth/me."""
    checker.section("A. Tokens JWT falsificados")
    mine = cookie(lab.manager, ACCESS_COOKIE)
    claims = jwt.decode(mine, options={"verify_signature": False})
    now = datetime.now(UTC)
    base = {**claims, "iat": now, "exp": now + timedelta(minutes=5)}
    key = settings.key("jwt")
    cases = {
        "alg=none": forge(base, "", "none"),
        "firmado con SECRET_KEY sin derivar": forge(base, settings.secret_key),
        "firmado con la clave derivada de otro uso": forge(base, settings.key("audit")),
        "firmado con otra clave": forge(base, uuid4().hex + uuid4().hex),
        "control: token valido con la clave derivada": forge(base, key),
        "emisor incorrecto": forge({**base, "iss": "https://evil.example"}, key),
        "refresh usado como access": forge({**base, "type": "refresh"}, key),
        "sin jti": forge({name: value for name, value in base.items() if name != "jti"}, key),
        "jti que no es el ultimo": forge({**base, "jti": str(uuid4())}, key),
        "sesion inexistente": forge({**base, "session": str(uuid4())}, key),
        "usuario inexistente": forge({**base, "sub": str(uuid4())}, key),
        "caducado": forge({**base, "exp": now - timedelta(minutes=1)}, key),
        "HS512": forge(base, key, "HS512"),
        "firma alterada": mine[:-3] + ("BBB" if mine.endswith("AAA") else "AAA"),
        "basura": "no.es.un.token",
    }
    for name, token in cases.items():
        response = anonymous("GET", "/api/auth/me", headers={"Cookie": f"{ACCESS_COOKIE}={token}"})
        wanted = 200 if name.startswith("control") else 401
        detail = f"{response.status_code} {response.text[:80]}"
        checker.check(f"JWT {name}", response.status_code == wanted, detail)

    response = anonymous("GET", "/api/auth/me", headers={"Authorization": f"Bearer {mine}"})
    checker.check(
        "token por cabecera Authorization no se acepta", response.status_code == 401, response.text
    )
    refresh_token = cookie(lab.manager, REFRESH_COOKIE)
    response = anonymous(
        "GET", "/api/auth/me", headers={"Cookie": f"{ACCESS_COOKIE}={refresh_token}"}
    )
    checker.check(
        "refresh token en la cookie de acceso", response.status_code == 401, response.text
    )
    response = anonymous(
        "POST", "/api/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE}={mine}"}
    )
    checker.check("access token como refresh", response.status_code == 401, response.text)


def denied(
    checker: Checker,
    name: str,
    response: httpx.Response,
    statuses: tuple[int, ...] = (403, 422),
) -> None:
    """Comprueba que la petición fue rechazada con uno de esos estados."""
    checker.check(
        name, response.status_code in statuses, f"{response.status_code} {response.text[:100]}"
    )


def privilege_escalation(checker: Checker, lab: Lab) -> None:
    """Un gestor con users.* y roles.* sin ser admin intenta subir de nivel."""
    checker.section("B. Escalada de privilegios (gestor sin ser admin)")
    manager, suffix, password = lab.manager, lab.suffix, lab.password
    boss_role, manager_role, basic_role = (lab.roles[kind] for kind in ("boss", "manager", "basic"))
    denied(
        checker,
        "crear usuario con un rol con mas permisos que yo",
        manager.post(
            "/api/users/",
            json={"username": f"esc{suffix}", "password": password, "role_id": boss_role["id"]},
        ),
    )
    denied(
        checker,
        "ampliar los permisos de mi propio rol",
        manager.patch(f"/api/roles/{manager_role['id']}", json={"permissions": lab.assignable}),
    )
    denied(
        checker,
        "crear un rol con mas permisos que yo",
        manager.post("/api/roles/", json={"name": f"Super{suffix}", "permissions": lab.assignable}),
    )
    denied(
        checker,
        "asignarme el rol admin",
        manager.patch(f"/api/users/{lab.manager_id}", json={"role_id": boss_role["id"]}),
    )
    denied(
        checker,
        "cambiar la clave de un usuario con mas permisos",
        manager.post(f"/api/users/{lab.boss_id}/password", json={"new_password": f"Otra{tag()}1"}),
    )
    denied(
        checker,
        "desactivar a un usuario con mas permisos",
        manager.patch(f"/api/users/{lab.boss_id}", json={"is_active": False}),
    )
    denied(
        checker,
        "crear un usuario dev sin serlo",
        manager.post(
            "/api/users/", json={"username": f"dv{suffix}", "password": password, "dev": True}
        ),
        (403,),
    )
    denied(
        checker,
        "hacerme dev",
        manager.patch(f"/api/users/{lab.manager_id}", json={"dev": True}),
        (403,),
    )
    response = manager.post(
        "/api/users/",
        json={"username": f"ok{suffix}", "password": password, "role_id": basic_role["id"]},
    )
    checker.check(
        "crear usuario con un rol menor (legitimo)",
        response.status_code == 201,
        response.text[:100],
    )

    forged_id = str(uuid4())
    response = manager.post(
        "/api/users/",
        json={
            "username": f"mass{suffix}",
            "password": password,
            "id": forged_id,
            "deleted_at": "2020-01-01T00:00:00Z",
            "created_by_id": str(uuid4()),
            "dev": False,
        },
    )
    body = response.json() if response.status_code == 201 else {}
    checker.check(
        "asignacion masiva (id/deleted_at) ignorada",
        response.status_code == 201 and body["deleted_at"] is None and body["id"] != forged_id,
        response.text[:100],
    )

    manager_session = lab.manager.get("/api/auth/sessions").json()[0]["id"]
    response = lab.basic.delete(f"/api/auth/sessions/{manager_session}")
    checker.check(
        "IDOR: cerrar la sesion de otro usuario", response.status_code == 404, response.text
    )
    denied(
        checker,
        "ver sesiones ajenas sin permiso",
        lab.basic.get(f"/api/users/{lab.manager_id}/sessions"),
        (403,),
    )
    denied(checker, "leer la auditoria sin permiso", lab.basic.get("/api/events/"), (403,))
    denied(checker, "catalogo de errores sin permiso", lab.basic.get("/api/system/errors"), (403,))


def cross_idempotency(checker: Checker, lab: Lab) -> None:
    """La clave de idempotencia de un usuario no devuelve su respuesta a otro."""
    checker.section("C. Idempotencia entre usuarios")
    key = {DEFAULT_HEADER_NAME: str(uuid4())}
    body = {"name": f"Cruz{lab.suffix}", "permissions": []}
    first = lab.dev.post("/api/roles/", json=body, headers=key)
    second = lab.manager.post("/api/roles/", json=body, headers=key)
    checker.check(
        "la misma clave en otra sesion no reutiliza mi respuesta",
        first.status_code == 201 and second.headers.get(DEFAULT_REPLAYED_HEADER_NAME) != "true",
        f"{second.status_code} {second.text[:100]}",
    )


def csrf(checker: Checker, lab: Lab) -> None:
    """Escrituras con Origin ajeno, parecido o disfrazado, y CORS."""
    checker.section("D. CSRF por Origin")
    legit = settings.cors_origins[0] if settings.cors_origins else BASE_URL.rstrip("/")
    own_host = urlsplit(BASE_URL).netloc
    variants = (
        "https://evil.example",
        "null",
        f"{legit}.evil.com",
        f"{legit}@evil.com",
        legit.upper(),
        f"{legit}0",
        f"{legit}/",
        legit.replace("://", "://evil."),
    )
    for origin in variants:
        if origin in settings.cors_origins or urlsplit(origin).netloc == own_host:
            continue
        response = lab.dev.post(
            "/api/roles/",
            json={"name": f"Csrf{tag()}", "permissions": []},
            headers={"Origin": origin},
        )
        checker.check(
            f"Origin {origin!r}",
            response.status_code == 403 and code_of(response) == "PRM_003",
            str(response.status_code),
        )
    response = lab.dev.post(
        "/api/roles/",
        json={"name": f"CsrfOk{lab.suffix}", "permissions": []},
        headers={"Origin": legit},
    )
    checker.check("Origin legitimo", response.status_code == 201, str(response.status_code))
    response = lab.dev.post(
        "/api/roles/",
        json={"name": f"CsrfRef{lab.suffix}", "permissions": []},
        headers={"Referer": "https://evil.example/x"},
    )
    info(
        "solo Referer ajeno, sin Origin (los navegadores siempre envian Origin en POST cruzado)",
        str(response.status_code),
    )
    hostile = {"Origin": "https://evil.example"}
    response = anonymous(
        "OPTIONS",
        "/api/system/health",
        headers={**hostile, "Access-Control-Request-Method": "GET"},
    )
    checker.check(
        "CORS no refleja origenes ajenos",
        "access-control-allow-origin" not in response.headers,
        str(dict(response.headers)),
    )
    response = anonymous("GET", "/api/system/health", headers=hostile)
    checker.check(
        "CORS no da acceso a origenes ajenos (GET)",
        "access-control-allow-origin" not in response.headers,
        str(dict(response.headers)),
    )


def hostile_input(checker: Checker, lab: Lab) -> None:
    """Inyecciones, números y textos extremos, JSON roto y nombres confusos."""
    checker.section("E. Inyecciones y entradas hostiles")
    dev, suffix, password = lab.dev, lab.suffix, lab.password
    for payload in ("' OR '1'='1", "'; DROP TABLE roles;--", "\\", "%", "_", "\x00"):
        response = dev.get("/api/roles/", params={"search": payload})
        checker.check(
            f"search={payload!r}",
            response.status_code in (200, 422),
            f"{response.status_code} {response.text[:100]}",
        )
    response = dev.get("/api/roles/", params={"search": "%"})
    shown = response.json().get("total") if response.status_code == 200 else response.status_code
    info(
        "search='%' devuelve",
        f"{shown} roles (total real: {dev.get('/api/roles/').json()['total']})",
    )

    response = dev.get("/api/roles/", params={"page": 10**12, "size": 100})
    denied(checker, "page enorme", response, (200, 422))
    response = dev.get("/api/roles/", params={"size": 100000})
    checker.check(
        "size enorme se limita",
        response.status_code == 422 or response.json().get("size", 0) <= 100,
        str(response.status_code),
    )
    response = dev.get("/api/roles/no-es-un-uuid")
    checker.check(
        "id que no es UUID -> 422", response.status_code == 422, str(response.status_code)
    )

    cases = (
        (
            "byte NUL en un texto no rompe el servidor",
            {"name": f"a\x00b{suffix}", "permissions": []},
            (400, 422),
        ),
        (
            "entero gigante en permisos no rompe el servidor",
            {"name": f"Big{suffix}", "permissions": [2**70]},
            (400, 422),
        ),
        ("permiso negativo", {"name": f"Neg{suffix}", "permissions": [-5]}, (400, 422)),
        ("texto de 5000 caracteres", {"name": "x" * 5000, "permissions": []}, (422,)),
        (
            "lista de 50000 elementos",
            {"name": f"Lst{suffix}", "permissions": list(range(1, 50000))},
            (422,),
        ),
    )
    for name, body, statuses in cases:
        denied(checker, name, dev.post("/api/roles/", json=body), statuses)

    response = dev.post("/api/users/", json={"username": f"аna{suffix}", "password": password})
    checker.check(
        "usuario con letra cirilica (confundible)",
        response.status_code == 422,
        f"{response.status_code} {response.text[:100]}",
    )
    response = dev.post("/api/users/", json={"username": f"MAYUS{suffix}", "password": password})
    checker.check(
        "usuario se guarda en minusculas",
        response.status_code == 201 and response.json()["username"] == f"mayus{suffix}",
        response.text[:100],
    )
    response = anonymous(
        "POST", "/api/auth/login", json={"username": f"  MAYUS{suffix} ", "password": password}
    )
    checker.check(
        "login ignora mayusculas y espacios",
        response.status_code == 200,
        f"{response.status_code} {response.text[:80]}",
    )
    response = dev.post("/api/roles/", content=b"{", headers=JSON_HEADERS)
    checker.check("JSON roto -> 422", response.status_code == 422, str(response.status_code))
    deep = b"[" * 200000 + b"]" * 200000
    response = dev.post("/api/roles/", content=deep, headers=JSON_HEADERS)
    denied(checker, "JSON anidado 200000 niveles", response, (400, 413, 422))


def tampered_routes(checker: Checker, lab: Lab) -> None:
    """Rutas y métodos manipulados."""
    checker.section("F. Rutas y metodos manipulados")
    headers = {"Cookie": f"{ACCESS_COOKIE}={cookie(lab.dev, ACCESS_COOKIE)}"}
    for method, path in ROUTE_ATTACKS:
        status, text = raw(method, path, headers)
        benign = path.startswith(BENIGN_ROUTES)
        checker.check(
            f"{method} {path[:45]}",
            status in (401, 403, 404, 405, 307, 308, 414, 422) or (status == 200 and benign),
            f"{status} {text[:80]}",
        )
    response = lab.dev.get("/api/roles/", headers={"X-HTTP-Method-Override": "DELETE"})
    checker.check(
        "X-HTTP-Method-Override no se respeta",
        response.status_code == 200,
        str(response.status_code),
    )


def leaks(checker: Checker) -> None:
    """Información que la API no debe dar a un desconocido."""
    checker.section("G. Fugas de informacion")
    response = anonymous("GET", "/api/system/health")
    shown = {name: value for name, value in response.headers.items() if name in SECURITY_HEADERS}
    info("cabeceras de la respuesta", str(shown))
    headers = response.headers
    checker.check(
        "cabeceras de seguridad en la API",
        headers.get("x-content-type-options") == "nosniff"
        and headers.get("x-frame-options") == "DENY"
        and headers.get("referrer-policy") == "no-referrer"
        and headers.get("cache-control") == "no-store",
        str(shown),
    )
    checker.check(
        "health publico no revela version ni hora",
        set(response.json()) <= {"status", "database"},
        response.text,
    )
    response = anonymous("GET", "/api/roles/", headers={"Cookie": f"{ACCESS_COOKIE}=x"})
    checker.check(
        "error 401 sin detalle tecnico",
        "debug" not in response.text and "Traceback" not in response.text,
        response.text[:120],
    )
    secret = f"secreto-{tag()}"
    response = anonymous(
        "POST", "/api/auth/login", json={"username": f"eco{tag()}", "password": [secret]}
    )
    checker.check(
        "422 no devuelve la entrada del usuario",
        response.status_code == 422
        and "input" not in response.text
        and secret not in response.text,
        response.text[:160],
    )


def chunks(megabytes: int) -> Iterator[bytes]:
    """Cuerpo JSON de ese tamaño, enviado por trozos y sin Content-Length."""
    piece = b"A" * (1024 * 1024)
    yield b'{"name": "'
    for _ in range(megabytes):
        yield piece
    yield b'", "permissions": []}'


async def flood(requests: int) -> tuple[int, float]:
    """Peticiones simultáneas a health: cuántas dan 200 y cuánto tardan."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as session:
        started = time.perf_counter()
        responses = await asyncio.gather(
            *(session.get("/api/system/health") for _ in range(requests))
        )
        return sum(
            1 for item in responses if item.status_code == 200
        ), time.perf_counter() - started


async def race(dev: httpx.Client, username: str, password: str) -> list[int]:
    """Ocho altas simultáneas del mismo usuario, cada una con su propia clave de idempotencia."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60, cookies=dev.cookies) as session:
        responses = await asyncio.gather(
            *(
                session.post(
                    "/api/users/",
                    json={"username": username, "password": password},
                    headers={DEFAULT_HEADER_NAME: str(uuid4())},
                )
                for _ in range(8)
            )
        )
        return sorted(item.status_code for item in responses)


def denial_of_service(checker: Checker, lab: Lab) -> None:
    """Cuerpos enormes, ráfagas y carreras."""
    checker.section("H. Denegacion de servicio")
    for megabytes in (12, 60):
        started = time.perf_counter()
        try:
            response = lab.dev.post("/api/roles/", content=chunks(megabytes), headers=JSON_HEADERS)
        except (httpx.HTTPError, OSError) as error:
            info(f"  {megabytes} MB", f"conexion cortada: {type(error).__name__}")
            continue
        outcome = f"{response.status_code} en {time.perf_counter() - started:.1f}s"
        checker.check(
            f"cuerpo de {megabytes} MB por chunked se rechaza", response.status_code == 413, outcome
        )
        info(f"  {megabytes} MB", outcome)
    response = lab.dev.post("/api/roles/", content=b"x" * (2 * 1024 * 1024), headers=JSON_HEADERS)
    checker.check(
        "cuerpo de 2 MB (Content-Length) se rechaza",
        response.status_code == 413,
        str(response.status_code),
    )

    succeeded, took = asyncio.run(flood(300))
    info("300 peticiones concurrentes a health", f"{succeeded} ok en {took:.1f}s")
    statuses = asyncio.run(race(lab.dev, f"race{lab.suffix}", lab.password))
    checker.check(
        "carrera: mismo usuario creado 8 veces a la vez -> una sola vez",
        statuses.count(201) == 1 and all(status in (201, 409) for status in statuses),
        str(statuses),
    )


def median_login_ms(usernames: list[str]) -> float:
    """Mediana de lo que tarda un login fallido con cada usuario, en milisegundos."""
    samples: list[float] = []
    with client() as session:
        for username in usernames:
            started = time.perf_counter()
            session.post(
                "/api/auth/login", json={"username": username, "password": f"Mala{tag()}1"}
            )
            samples.append(time.perf_counter() - started)
    return statistics.median(samples) * 1000


def timing(checker: Checker, lab: Lab) -> None:
    """El login no debe tardar distinto si el usuario existe."""
    checker.section("I. Tiempos: enumeracion de usuarios")
    existing = median_login_ms([f"basic{lab.suffix}"] * 6)
    missing = median_login_ms([f"noexiste{index}{lab.suffix}" for index in range(6)])
    info("mediana existente / inexistente", f"{existing:.0f} ms / {missing:.0f} ms")
    checker.check(
        "login tarda parecido exista o no el usuario",
        abs(existing - missing) < max(60, existing * 0.35),
        f"{existing:.0f} vs {missing:.0f} ms",
    )


def brute_force(checker: Checker, lab: Lab) -> None:
    """Muchas contraseñas contra un usuario hasta que el servidor se planta."""
    checker.section("J. Fuerza bruta")
    username = f"basic{lab.suffix}"
    with client() as session:
        statuses = [
            session.post(
                "/api/auth/login", json={"username": username, "password": f"Mala{index}Clave1"}
            ).status_code
            for index in range(14)
        ]
        checker.check("fuerza bruta contra un usuario se frena", 429 in statuses, str(statuses))
        response = login(session, username, lab.password)
    checker.check(
        "aun con la clave correcta, esta bloqueado",
        response.status_code == 429,
        str(response.status_code),
    )


def refresh_reuse(checker: Checker, lab: Lab) -> None:
    """Un refresh token usado dos veces cierra la sesión."""
    checker.section("K. Sesiones")
    session = sign_in(f"boss{lab.suffix}", lab.password)
    headers = {"Cookie": f"{REFRESH_COOKIE}={cookie(session, REFRESH_COOKIE)}"}
    first = anonymous("POST", "/api/auth/refresh", headers=headers)
    second = anonymous("POST", "/api/auth/refresh", headers=headers)
    checker.check(
        "refresh usado dos veces: el segundo falla",
        first.status_code == 200 and second.status_code == 401,
        f"{first.status_code} {second.status_code}",
    )
    info(
        "tras reutilizar el refresh, la sesion original",
        str(session.get("/api/auth/me").status_code),
    )


def main() -> None:
    """Prepara tres usuarios y lanza toda la batería contra el servidor."""
    checker = Checker("Batería de ataques")
    reset_login_attempts()
    try:
        lab = prepare(tag(), f"Prueba{tag()}1")
        forged_tokens(checker, lab)
        privilege_escalation(checker, lab)
        cross_idempotency(checker, lab)
        csrf(checker, lab)
        hostile_input(checker, lab)
        tampered_routes(checker, lab)
        leaks(checker)
        denial_of_service(checker, lab)
        timing(checker, lab)
        brute_force(checker, lab)
        refresh_reuse(checker, lab)
    finally:
        reset_login_attempts()
    checker.finish()


if __name__ == "__main__":
    main()
