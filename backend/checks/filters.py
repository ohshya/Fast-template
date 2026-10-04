"""Orden, rangos y filtros de los listados de usuarios y roles: uv run python -m checks.filters."""

import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from checks.common import Checker, admin, dev_client, fields_of, iso, tag

type Json = dict[str, Any]
USER_COUNT = 9


def created(response: httpx.Response, what: str) -> Json:
    """Cuerpo de una creación; si no fue 201 el script no puede seguir."""
    if response.status_code != 201:
        sys.exit(f"No se pudo crear {what}: {response.status_code} {response.text}")
    return response.json()


def items_of(response: httpx.Response) -> list[Json]:
    """Elementos de una página, o ninguno si la respuesta no es un listado."""
    return response.json()["items"] if response.status_code == 200 else []


def total_of(response: httpx.Response) -> int:
    """Total de un listado, o -1 si la respuesta no lo es."""
    return response.json()["total"] if response.status_code == 200 else -1


def stems(items: list[Json]) -> list[str]:
    """Parte inicial del nombre de cada rol, en el orden recibido."""
    return [item["name"].split("-")[0] for item in items]


def listed_roles(dev: httpx.Client, run_id: str, **params: Any) -> tuple[httpx.Response, list[str]]:
    """Roles de esta ejecución con los parámetros dados, y la parte inicial de sus nombres."""
    response = dev.get("/api/roles/", params={"search": run_id, **params})
    return response, stems(items_of(response))


def create_roles(dev: httpx.Client, run_id: str) -> dict[str, Json]:
    """Cuatro roles creados con una pausa entre cada uno para que sus fechas difieran."""
    roles: dict[str, Json] = {}
    for stem in ("Zeta", "Alfa", "Mike", "Bravo"):
        r = dev.post("/api/roles/", json={"name": f"{stem}-{run_id}", "permissions": []})
        roles[stem] = created(r, f"el rol {stem}")
        time.sleep(0.25)
    return roles


def create_users(dev: httpx.Client, run_id: str, roles: dict[str, Json]) -> list[Json]:
    """Nueve usuarios repartidos entre tres roles; los de índice múltiplo de 4 quedan inactivos."""
    password = f"Pw{tag()}{tag()}9"
    users: list[Json] = []
    for index in range(USER_COUNT):
        r = dev.post(
            "/api/users/",
            json={
                "username": f"u{run_id}{index}",
                "password": password,
                "role_id": roles[("Zeta", "Alfa", "Mike")[index % 3]]["id"],
                "is_active": index % 4 != 0,
            },
        )
        users.append(created(r, f"el usuario {index}"))
    return users


def sorting(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Ordenar con ?sort=: sentido, varios criterios y errores de validación."""
    checks.section("Ordenar (?sort=)")
    ascending = ["Alfa", "Bravo", "Mike", "Zeta"]
    r, order = listed_roles(dev, run_id, sort="name")
    checks.check("sort=name ascendente", r.status_code == 200 and order == ascending, str(order))
    _, order = listed_roles(dev, run_id, sort="-name")
    checks.check("sort=-name descendente", order == ascending[::-1], str(order))
    _, order = listed_roles(dev, run_id, sort="-created_at")
    checks.check(
        "sort=-created_at: el último creado primero",
        order == ["Bravo", "Mike", "Alfa", "Zeta"],
        str(order),
    )
    _, order = listed_roles(dev, run_id)
    checks.check(
        "sin sort: el orden por defecto del recurso (name)", order == ascending, str(order)
    )

    r = dev.get(
        "/api/users/",
        params={"search": f"u{run_id}", "sort": "is_active,-username", "size": 50},
    )
    rows = [(item["is_active"], item["username"]) for item in items_of(r)]
    expected = sorted(rows, key=lambda row: (row[0], [-ord(char) for char in row[1]]))
    checks.check(
        "varios criterios: sort=is_active,-username",
        len(rows) == USER_COUNT and rows == expected,
        str(rows),
    )
    r = dev.get("/api/roles/", params={"sort": "permissions"})
    checks.check(
        "columna no permitida -> 422 en 'sort' y en español",
        r.status_code == 422 and "Columnas permitidas" in fields_of(r).get("sort", ""),
        r.text,
    )
    r = dev.get("/api/roles/", params={"sort": "name,name,name,name,name"})
    checks.check(
        "más de 4 columnas -> 422", r.status_code == 422 and "sort" in fields_of(r), r.text
    )
    r = dev.get("/api/roles/", params={"sort": "x" * 300})
    checks.check(
        "sort demasiado largo -> 422 'Máximo 200 caracteres'",
        r.status_code == 422 and "Máximo 200" in fields_of(r).get("sort", ""),
        r.text,
    )


def stable_pages(checks: Checker, dev: httpx.Client, run_id: str) -> None:
    """Recorrer un orden con empates por páginas no repite ni pierde registros."""
    checks.section("Orden estable al paginar (desempate por id)")
    seen: list[str] = []
    for page in range(1, 6):
        r = dev.get(
            "/api/users/",
            params={"search": f"u{run_id}", "sort": "is_active", "size": 2, "page": page},
        )
        seen += [item["id"] for item in items_of(r)]
    checks.check(
        f"{USER_COUNT} usuarios en 5 páginas de 2 sin repetidos ni faltantes",
        len(seen) == USER_COUNT and len(set(seen)) == USER_COUNT,
        str(len(seen)),
    )


def ranges(checks: Checker, dev: httpx.Client, run_id: str, roles: dict[str, Json]) -> None:
    """Rangos _from y _to sobre fechas, con las fechas de creación que devolvió el servidor."""
    checks.section("Rangos (_from / _to)")
    stamp = {stem: role["created_at"] for stem, role in roles.items()}
    _, order = listed_roles(dev, run_id, created_at_from=stamp["Alfa"])
    checks.check(
        "created_at_from deja los creados desde Alfa (Alfa, Bravo, Mike) y quita Zeta",
        sorted(order) == ["Alfa", "Bravo", "Mike"],
        str(order),
    )
    _, order = listed_roles(dev, run_id, created_at_to=stamp["Alfa"])
    checks.check(
        "created_at_to deja los creados hasta Alfa (Zeta, Alfa)",
        sorted(order) == ["Alfa", "Zeta"],
        str(order),
    )
    _, order = listed_roles(dev, run_id, created_at_from=stamp["Alfa"], created_at_to=stamp["Mike"])
    checks.check(
        "from y to a la vez (Alfa..Mike, sin Bravo: se creó después)",
        sorted(order) == ["Alfa", "Mike"],
        str(order),
    )
    r = dev.get(
        "/api/roles/", params={"created_at_from": stamp["Mike"], "created_at_to": stamp["Alfa"]}
    )
    checks.check(
        "from posterior a to -> 422 en created_at_to",
        r.status_code == 422 and "created_at_to" in fields_of(r),
        r.text,
    )
    r = dev.get("/api/roles/", params={"created_at_from": "2026-01-01T00:00:00"})
    checks.check(
        "fecha sin zona horaria -> 422 'La fecha necesita zona horaria'",
        r.status_code == 422
        and fields_of(r).get("created_at_from") == "La fecha necesita zona horaria",
        r.text,
    )
    r = dev.get("/api/roles/", params={"created_at_from": "no-es-fecha"})
    checks.check(
        "fecha mal escrita -> 422 en español",
        r.status_code == 422 and "no válida" in fields_of(r).get("created_at_from", ""),
        r.text,
    )
    yesterday = iso(datetime.now(UTC) - timedelta(days=1))
    r = dev.get("/api/users/", params={"search": f"u{run_id}", "last_login_at_from": yesterday})
    checks.check(
        "rango sobre un campo opcional (last_login_at): nadie ha entrado",
        total_of(r) == 0,
        r.text,
    )


def multiple_values(
    checks: Checker,
    dev: httpx.Client,
    run_id: str,
    roles: dict[str, Json],
    users: list[Json],
) -> None:
    """Filtros de varios valores (IN), booleanos, uuid y su combinación con orden."""
    checks.section("Varios valores (IN) y combinaciones")
    search = f"u{run_id}"
    ids = [roles["Zeta"]["id"], roles["Alfa"]["id"]]
    r = dev.get("/api/users/", params={"search": search, "role_id": ids, "size": 50})
    checks.check("role_id repetido = IN (Zeta y Alfa: 6 usuarios)", total_of(r) == 6, r.text)
    r = dev.get("/api/users/", params={"search": search, "role_id": roles["Mike"]["id"]})
    checks.check("un solo role_id (Mike: 3 usuarios)", total_of(r) == 3, r.text)
    inactive = [user for user in users if not user["is_active"]]
    r = dev.get("/api/users/", params={"search": search, "is_active": "false", "size": 50})
    checks.check("is_active=false", total_of(r) == len(inactive), r.text)
    r = dev.get(
        "/api/users/",
        params={"search": search, "role_id": ids, "is_active": "true", "sort": "-username"},
    )
    wanted = [user for user in users if user["role_id"] in ids and user["is_active"]]
    names = [item["username"] for item in items_of(r)]
    checks.check(
        "IN + booleano + sort juntos",
        total_of(r) == len(wanted)
        and names == sorted((user["username"] for user in wanted), reverse=True),
        r.text,
    )
    r = dev.get("/api/users/", params={"dev": "true", "search": admin()[0]})
    checks.check(
        "filtro dev=true",
        total_of(r) >= 1 and all(item["dev"] for item in items_of(r)),
        r.text,
    )
    r = dev.get("/api/users/", params={"role_id": "no-es-uuid"})
    checks.check(
        "uuid mal escrito -> 422 Identificador no válido (campo role_id)",
        r.status_code == 422 and fields_of(r).get("role_id") == "Identificador no válido",
        r.text,
    )
    r = dev.get("/api/users/", params={"is_active": "quizas"})
    checks.check(
        "booleano mal escrito -> 422 en español",
        r.status_code == 422 and "verdadero o falso" in fields_of(r).get("is_active", ""),
        r.text,
    )
    r = dev.get("/api/users/", params={"search": search, "deleted": "true"})
    checks.check("deleted=true sigue funcionando", total_of(r) == 0, r.text)


def body_messages(checks: Checker, dev: httpx.Client) -> None:
    """Los errores de validación del cuerpo llegan en español, por campo."""
    checks.section("Mensajes de validación en español (cuerpo)")
    r = dev.post("/api/roles/", json={"name": "a"})
    checks.check(
        "'String should have at least 2 characters' en español",
        fields_of(r).get("name") == "Mínimo 2 caracteres",
        r.text,
    )
    r = dev.post("/api/roles/", json={})
    checks.check(
        "'Field required' en español",
        fields_of(r).get("name") == "Este campo es obligatorio",
        r.text,
    )
    r = dev.post("/api/roles/", json={"name": "ok", "permissions": "x"})
    checks.check(
        "tipo mal -> español", fields_of(r).get("permissions") == "Debe ser una lista", r.text
    )
    r = dev.post("/api/roles/", json={"name": "x" * 150})
    checks.check("máximo -> español", fields_of(r).get("name") == "Máximo 100 caracteres", r.text)
    r = dev.post("/api/roles/", json={"name": "ok", "permissions": list(range(2001))})
    checks.check(
        "el tope de permisos por rol es 2000",
        r.status_code == 422 and fields_of(r).get("permissions") == "Máximo 2000 elementos",
        r.text,
    )


def openapi(checks: Checker, dev: httpx.Client) -> None:
    """OpenAPI documenta los parámetros de filtro de los dos listados."""
    checks.section("OpenAPI describe los parámetros")
    r = dev.get("/openapi.json")
    if not checks.check("/openapi.json disponible (DEBUG=true)", r.status_code == 200, r.text):
        return
    paths: Json = r.json()["paths"]
    users = {item["name"]: item for item in paths["/api/users/"]["get"]["parameters"]}
    roles = {item["name"]: item for item in paths["/api/roles/"]["get"]["parameters"]}
    wanted_users = {
        "search",
        "deleted",
        "sort",
        "role_id",
        "dev",
        "is_active",
        "created_at_from",
        "created_at_to",
        "last_login_at_from",
        "last_login_at_to",
    }
    wanted_roles = {
        "search",
        "deleted",
        "sort",
        "created_at_from",
        "created_at_to",
        "updated_at_from",
        "updated_at_to",
    }
    checks.check(
        "users lista: sort, role_id, dev, is_active, rangos, search y deleted",
        wanted_users <= set(users),
        str(sorted(users)),
    )
    checks.check(
        "roles lista: sort, rangos, search y deleted",
        wanted_roles <= set(roles),
        str(sorted(roles)),
    )
    schema = users.get("role_id", {}).get("schema", {})
    checks.check(
        "role_id se documenta como lista",
        (schema.get("anyOf") or [{}])[0].get("type") == "array",
        str(schema),
    )


def main() -> None:
    """Crea datos propios de esta ejecución, comprueba los filtros y fija el código de salida."""
    checks = Checker("filters")
    dev = dev_client()
    run_id = tag()
    roles = create_roles(dev, run_id)
    users = create_users(dev, run_id, roles)
    sorting(checks, dev, run_id)
    stable_pages(checks, dev, run_id)
    ranges(checks, dev, run_id, roles)
    multiple_values(checks, dev, run_id, roles, users)
    body_messages(checks, dev)
    openapi(checks, dev)
    checks.finish()


if __name__ == "__main__":
    main()
