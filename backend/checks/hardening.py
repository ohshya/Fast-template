from uuid import uuid4

from tortoise.exceptions import OperationalError

from app.core.errors import normalize
from checks.common import Checker, client, code_of, dev_client, error_of, fields_of, login, tag


def main() -> None:
    """Protección de cuentas y sesiones, login fallido, valores únicos y errores de concurrencia."""
    checker = Checker("hardening")
    check = checker.check
    dev = dev_client()
    me = dev.get("/api/auth/me").json()
    mark = tag()

    checker.section("un usuario con permisos de sesiones no ve las de un dev")
    role = dev.post(
        "/api/roles/", json={"name": f"Gestor {mark}", "permissions": [3001, 3011, 3012]}
    ).json()
    dev.post(
        "/api/users/",
        json={"username": f"gest{mark}", "password": "Gestor12345", "role_id": role["id"]},
    )
    manager = client()
    login(manager, f"gest{mark}", "Gestor12345")
    r = manager.get(f"/api/users/{me['id']}/sessions")
    check(
        "ver las sesiones de un dev -> 403 USR_005",
        r.status_code == 403 and code_of(r) == "USR_005",
        r.text,
    )
    other = dev.post(
        "/api/users/", json={"username": f"otro{mark}", "password": "Otro12345"}
    ).json()
    r = manager.get(f"/api/users/{other['id']}/sessions")
    check("ver las sesiones de un usuario normal -> 200", r.status_code == 200, r.text)

    checker.section("restablecer la propia contraseña")
    own_id = manager.get("/api/auth/me").json()["id"]
    r = manager.post(f"/api/users/{own_id}/password", json={"new_password": "Nueva12345"})
    details = error_of(r).get("details", {})
    check(
        "un usuario no puede restablecerse la propia (USR_003)",
        r.status_code == 409
        and code_of(r) == "USR_003"
        and details.get("use") == "POST /api/auth/password",
        r.text,
    )
    r = dev.post(f"/api/users/{me['id']}/password", json={"new_password": "Nueva12345"})
    check("ni siquiera un dev", r.status_code == 409 and code_of(r) == "USR_003", r.text)
    r = manager.post(f"/api/users/{other['id']}/password", json={"new_password": "Otro123456"})
    check("restablecer la de otro sigue funcionando", r.status_code == 200, r.text)

    checker.section("login fallido: el nombre tecleado")
    anonymous = client()
    r = anonymous.post(
        "/api/auth/login", json={"username": "MiClave Secreta 123!", "password": "x" * 9}
    )
    check(
        "formato inválido -> 401 y details.username neutro",
        r.status_code == 401 and error_of(r).get("details", {}).get("username") == "<inválido>",
        r.text,
    )
    r = anonymous.post("/api/auth/login", json={"username": f"noexiste{mark}", "password": "x" * 9})
    check(
        "usuario válido que no existe: se muestra tal cual",
        error_of(r).get("details", {}).get("username") == f"noexiste{mark}",
        r.text,
    )
    events = dev.get("/api/events/", params={"error_code": "AUT_001", "size": 50}).json()["items"]
    check(
        "ningún evento guarda el texto con formato inválido",
        not any("MiClave" in (event["message"] or "") for event in events),
        str([event["message"] for event in events][:3]),
    )

    checker.section("un valor único que choca con un registro eliminado lo dice")
    name = f"Unico {mark}"
    created = dev.post("/api/roles/", json={"name": name, "permissions": []}).json()
    dev.delete(f"/api/roles/{created['id']}")
    r = dev.post(
        "/api/roles/",
        json={"name": name, "permissions": []},
        headers={"Idempotency-Key": str(uuid4())},
    )
    check(
        "409 con el aviso de restaurar",
        r.status_code == 409 and "eliminado" in fields_of(r).get("name", ""),
        r.text,
    )
    dev.post(f"/api/roles/{created['id']}/restore")
    r = dev.post(
        "/api/roles/",
        json={"name": name, "permissions": []},
        headers={"Idempotency-Key": str(uuid4())},
    )
    check(
        "con el registro activo: mensaje normal",
        r.status_code == 409 and fields_of(r).get("name") == "Ya existe un registro con este valor",
        r.text,
    )

    checker.section("conteo de usuarios por rol")
    r = dev.get("/api/roles/", params={"search": f"Gestor {mark}"})
    check("users_count del rol Gestor = 1", r.json()["items"][0]["users_count"] == 1, r.text)

    checker.section("errores de concurrencia de PostgreSQL")

    class Deadlock(Exception):
        sqlstate = "40P01"

    for label, exc in (
        ("directa", Deadlock("deadlock detected")),
        ("envuelta por Tortoise", OperationalError(Deadlock("deadlock detected"))),
    ):
        error, _ = normalize(exc)
        check(
            f"40P01 {label} -> 409 SYS_CONC",
            error.spec.code == "SYS_CONC" and error.spec.status == 409,
            error.spec.code,
        )
    checker.finish()


if __name__ == "__main__":
    main()
