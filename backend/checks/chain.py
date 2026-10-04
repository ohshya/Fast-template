"""Cadena de eventos: triggers de solo-añadir, verify() por partes y manipulaciones directas."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx

from checks.common import Checker, code_of, database, dev_client, execute, iso, query, tag


def triggers_active() -> bool:
    """Si los dos triggers de solo-añadir de `events` están activos."""
    rows = query(
        "select count(*) as active from pg_trigger where tgrelid = 'events'::regclass "
        "and tgname in ('events_no_change', 'events_no_truncate') and tgenabled in ('O', 'A')"
    )
    return int(rows[0]["active"]) == 2


async def _attempt(statement: str) -> str:
    """Ejecuta una sentencia suelta y devuelve el mensaje de error, o '' si no falló."""
    async with database() as connection:
        try:
            await connection.execute(statement)
        except Exception as error:
            return str(error)
    return ""


def attempt(statement: str) -> str:
    """Versión síncrona de `_attempt`, para usar fuera de una corrutina."""
    return asyncio.run(_attempt(statement))


def triggers_block_writes(checker: Checker) -> None:
    """Ni el dueño de la tabla puede modificar o truncar `events` con los triggers activos."""
    checker.check("2 triggers activos tras arrancar", triggers_active())
    for verb, statement in (
        ("UPDATE", "update events set message = 'x'"),
        ("DELETE", "delete from events"),
        ("TRUNCATE", "truncate events"),
    ):
        error = attempt(statement)
        checker.check(
            f"{verb} rechazado incluso para el dueño de la tabla",
            "solo añadir" in error and verb in error,
            error,
        )
    remaining = query("select count(*) as total from events")
    checker.check("nada se borro", int(remaining[0]["total"]) > 0)


def generate_events(dev: httpx.Client, count: int = 12) -> list[dict[str, str]]:
    """Crea `count` roles para generar eventos nuevos y devuelve un lote amplio de eventos."""
    for _ in range(count):
        response = dev.post("/api/roles/", json={"name": f"Cad-{tag()}", "permissions": []})
        if response.status_code != 201:
            sys.exit(f"No se pudo crear un rol de prueba: {response.status_code} {response.text}")
    page = dev.get("/api/events/", params={"order": "oldest", "size": 100}).json()
    events: list[dict[str, str]] = page["items"]
    return events


def whole_chain_intact(checker: Checker, dev: httpx.Client) -> None:
    """La cadena entera debe estar intacta y su conteo debe casar con la tabla."""
    report = dev.get("/api/events/verify").json()
    checker.check("cadena entera intacta", report["intact"] and report["append_only"], str(report))
    checker.check(
        "detalle de la cadena entera",
        report["detail"]
        == f"La cadena de eventos está intacta. Eventos comprobados: {report['checked']}.",
        report["detail"],
    )
    total_rows = query("select count(*) as total from events")
    checker.check(
        "checked == total",
        report["checked"] == report["total"] == int(total_rows[0]["total"]),
        str(report),
    )


def single_event_checks(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """Un solo evento verificado por id: intacto y enlazado; también el primero y el último."""
    middle = events[len(events) // 2]
    report = dev.get("/api/events/verify", params={"event_id": middle["id"]}).json()
    checker.check(
        "un solo evento: intacto y enlazado",
        report["intact"] and report["checked"] == 1,
        str(report),
    )
    first = dev.get("/api/events/verify", params={"event_id": events[0]["id"]}).json()
    checker.check("primer evento (sin anterior)", first["intact"], str(first))
    last_report = dev.get("/api/events/verify", params={"event_id": events[-1]["id"]}).json()
    checker.check("ultimo evento (compara con la cabeza)", last_report["intact"], str(last_report))


def period_checks(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """Verificación acotada a un periodo de fechas, con sus bordes y el caso vacío."""
    low, high = events[3], events[8]
    period = dev.get(
        "/api/events/verify",
        params={"date_from": low["created_at"], "date_to": high["created_at"]},
    ).json()
    expected_rows = query(
        "select count(*) as total from events where sequence between $1 and $2",
        low["sequence"],
        high["sequence"],
    )
    expected = int(expected_rows[0]["total"])
    checker.check(
        "periodo: intacto y cuenta lo esperado",
        period["intact"] and period["checked"] == expected,
        f"{period} esperado={expected}",
    )
    checker.check(
        "periodo: el detalle lo dice", "Eventos comprobados" in period["detail"], period["detail"]
    )

    future = dev.get(
        "/api/events/verify", params={"date_from": iso(datetime.now(UTC) + timedelta(days=5))}
    ).json()
    checker.check(
        "periodo sin eventos",
        future["intact"]
        and future["checked"] == 0
        and future["detail"] == "No hay eventos que comprobar.",
        str(future),
    )
    only_from = dev.get("/api/events/verify", params={"date_from": low["created_at"]}).json()
    checker.check("solo date_from (hasta el final)", only_from["intact"], str(only_from))
    only_to = dev.get("/api/events/verify", params={"date_to": high["created_at"]}).json()
    checker.check("solo date_to (desde el principio)", only_to["intact"], str(only_to))


def validation_errors(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """event_id y periodo no se combinan; fechas sin zona; ids inválidos; evento inexistente."""
    middle = events[len(events) // 2]
    started = datetime.now(UTC)
    response = dev.get(
        "/api/events/verify", params={"event_id": middle["id"], "date_from": iso(started)}
    )
    checker.check(
        "event_id + periodo -> 422",
        response.status_code == 422 and code_of(response) == "VAL_422",
        response.text,
    )
    ended = datetime.now(UTC)
    response = dev.get(
        "/api/events/verify", params={"date_from": iso(ended), "date_to": iso(started)}
    )
    checker.check(
        "date_from posterior a date_to -> 422", response.status_code == 422, response.text
    )
    response = dev.get("/api/events/verify", params={"event_id": str(uuid4())})
    checker.check("evento inexistente -> 404", response.status_code == 404, response.text)
    response = dev.get("/api/events/verify", params={"date_from": "2026-01-01T00:00:00"})
    checker.check("fecha sin zona horaria -> 422", response.status_code == 422, response.text)
    response = dev.get("/api/events/verify", params={"event_id": "no-es-uuid"})
    checker.check("event_id malformado -> 422", response.status_code == 422, response.text)


def edit_middle_event(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """Edita un evento del medio con el trigger apagado y comprueba que se detecta y se repara."""
    middle = len(events) // 2
    target, neighbour = events[middle], events[middle + 1]
    before, after = events[middle - 3], events[middle + 5]
    target_id = UUID(target["id"])
    execute("drop table if exists events_bak")
    execute("create table events_bak as select * from events where id = $1", target_id)
    execute("alter table events disable trigger events_no_change")
    try:
        execute("update events set message = 'ALTERADO' where id = $1", target_id)
    finally:
        execute("alter table events enable trigger events_no_change")

    whole = dev.get("/api/events/verify").json()
    checker.check(
        "editar: la cadena entera lo detecta",
        not whole["intact"] and whole["first_broken_id"] == target["id"],
        str(whole),
    )
    single = dev.get("/api/events/verify", params={"event_id": target["id"]}).json()
    checker.check(
        "editar: el evento alterado, individual",
        not single["intact"] and "firma" in single["detail"],
        str(single),
    )
    bounded = dev.get(
        "/api/events/verify",
        params={"date_from": before["created_at"], "date_to": after["created_at"]},
    ).json()
    checker.check("editar: un periodo que lo incluye", not bounded["intact"], str(bounded))
    outside = dev.get(
        "/api/events/verify",
        params={"date_from": events[0]["created_at"], "date_to": events[1]["created_at"]},
    ).json()
    checker.check(
        "editar: un periodo que NO lo incluye sigue intacto", outside["intact"], str(outside)
    )
    neighbour_report = dev.get("/api/events/verify", params={"event_id": neighbour["id"]}).json()
    checker.check(
        "editar: el vecino, individual, sigue intacto",
        neighbour_report["intact"],
        str(neighbour_report),
    )
    detail = dev.get(f"/api/events/{target['id']}").json()
    checker.check("editar: is_intact del detalle es false", detail["is_intact"] is False)

    execute("alter table events disable trigger events_no_change")
    try:
        execute("update events e set message = b.message from events_bak b where e.id = b.id")
    finally:
        execute("alter table events enable trigger events_no_change")
    execute("drop table if exists events_bak")
    checker.check(
        "editar: restaurado, vuelve a estar intacta", dev.get("/api/events/verify").json()["intact"]
    )


def delete_middle_event(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """Borra un evento del medio con el trigger apagado y comprueba que se detecta y se repara."""
    middle = len(events) // 2
    target, neighbour, previous = events[middle], events[middle + 1], events[middle - 1]
    before, after = events[middle - 3], events[middle + 5]
    target_id = UUID(target["id"])
    execute("drop table if exists events_bak")
    execute("create table events_bak as select * from events where id = $1", target_id)
    execute("alter table events disable trigger events_no_change")
    try:
        execute("delete from events where id = $1", target_id)
    finally:
        execute("alter table events enable trigger events_no_change")

    whole = dev.get("/api/events/verify").json()
    checker.check("borrar del medio: la cadena entera lo detecta", not whole["intact"], str(whole))
    neighbour_report = dev.get("/api/events/verify", params={"event_id": neighbour["id"]}).json()
    checker.check(
        "borrar del medio: el siguiente lo detecta, individual",
        not neighbour_report["intact"] and "falta" in neighbour_report["detail"],
        str(neighbour_report),
    )
    bounded = dev.get(
        "/api/events/verify",
        params={"date_from": before["created_at"], "date_to": after["created_at"]},
    ).json()
    checker.check("borrar del medio: un periodo que lo rodea", not bounded["intact"], str(bounded))
    previous_report = dev.get("/api/events/verify", params={"event_id": previous["id"]}).json()
    checker.check(
        "borrar del medio: el anterior, individual, sigue intacto",
        previous_report["intact"],
        str(previous_report),
    )

    execute("alter table events disable trigger events_no_change")
    try:
        execute("insert into events select * from events_bak")
    finally:
        execute("alter table events enable trigger events_no_change")
    execute("drop table if exists events_bak")
    checker.check("borrar del medio: restaurado", dev.get("/api/events/verify").json()["intact"])


def delete_tail_scenarios(
    checker: Checker, dev: httpx.Client, events: list[dict[str, str]]
) -> None:
    """Borra el último evento sin tocar la cabeza, y reajustándola también (límite conocido)."""
    middle = len(events) // 2
    before, after = events[middle - 3], events[middle + 5]
    tail = dev.get("/api/events/", params={"size": 1}).json()["items"][0]
    tail_id = UUID(tail["id"])
    execute("drop table if exists events_bak")
    execute("create table events_bak as select * from events where id = $1", tail_id)
    execute("alter table events disable trigger events_no_change")
    try:
        execute("delete from events where id = $1", tail_id)

        whole = dev.get("/api/events/verify").json()
        checker.check(
            "borrar el ultimo (cabeza intacta): la cadena entera lo detecta",
            not whole["intact"] and "no coincide con el último evento" in whole["detail"],
            str(whole),
        )
        checker.check(
            "borrar el ultimo: con el trigger apagado, el informe lo dice",
            whole["append_only"] is False,
            str(whole),
        )
        reaching = dev.get("/api/events/verify", params={"date_from": before["created_at"]}).json()
        checker.check(
            "borrar el ultimo: un periodo que llega al final lo detecta",
            not reaching["intact"],
            str(reaching),
        )
        bounded = dev.get(
            "/api/events/verify",
            params={"date_from": before["created_at"], "date_to": after["created_at"]},
        ).json()
        checker.check(
            "borrar el ultimo: un periodo que no llega al final no mira la cabeza",
            bounded["intact"],
            str(bounded),
        )

        head_before = query("select sequence, last_hash from event_chain")[0]
        new_tail = query("select sequence, hash from events order by sequence desc limit 1")[0]
        execute(
            "update event_chain set sequence = $1, last_hash = $2",
            new_tail["sequence"],
            new_tail["hash"],
        )
        limited = dev.get("/api/events/verify").json()
        checker.check(
            "borrar el ultimo Y reajustar la cabeza: NO se detecta (limitacion documentada)",
            limited["intact"] and not limited["append_only"],
            str(limited),
        )
        execute("insert into events select * from events_bak")
        execute(
            "update event_chain set sequence = $1, last_hash = $2",
            head_before["sequence"],
            head_before["last_hash"],
        )
    finally:
        execute("alter table events enable trigger events_no_change")
    execute("drop table if exists events_bak")
    restored = dev.get("/api/events/verify").json()
    checker.check(
        "estado restaurado", restored["intact"] and restored["append_only"], str(restored)
    )


def truncate_guard_reflected(checker: Checker, dev: httpx.Client) -> None:
    """El trigger de TRUNCATE desactivado se refleja en el informe; reactivarlo lo corrige."""
    execute("alter table events disable trigger events_no_truncate")
    try:
        report = dev.get("/api/events/verify").json()
        checker.check(
            "truncate desactivado: append_only false",
            report["intact"] and report["append_only"] is False,
            str(report),
        )
    finally:
        execute("alter table events enable trigger events_no_truncate")
    restored = dev.get("/api/events/verify").json()
    checker.check("reactivado: append_only true", restored["append_only"] is True, str(restored))


def chain_head_deleted(checker: Checker, dev: httpx.Client, events: list[dict[str, str]]) -> None:
    """Si falta la fila de la cabeza, verify() lo detecta; restaurarla lo corrige."""
    middle = len(events) // 2
    before, after = events[middle - 3], events[middle + 5]
    execute("drop table if exists event_chain_bak")
    execute("create table event_chain_bak as select * from event_chain")
    try:
        execute("delete from event_chain")
        report = dev.get("/api/events/verify").json()
        checker.check(
            "cabeza borrada: se detecta",
            not report["intact"] and "Falta la cabeza" in report["detail"],
            str(report),
        )
        bounded = dev.get(
            "/api/events/verify",
            params={"date_from": before["created_at"], "date_to": after["created_at"]},
        ).json()
        checker.check(
            "cabeza borrada: un periodo que no llega al final no la mira",
            bounded["intact"],
            str(bounded),
        )
    finally:
        execute("insert into event_chain select * from event_chain_bak")
        execute("drop table if exists event_chain_bak")
    checker.check("cabeza restaurada", dev.get("/api/events/verify").json()["intact"])


def forged_rows(checker: Checker, dev: httpx.Client) -> None:
    """Filas falsas con sequence <= 0: el INSERT sigue permitido pero verify() las detecta."""
    for fake_sequence in (0, -7):
        rows = query(
            "insert into events (id, sequence, category, action, severity, message, hash) "
            "values (uuidv7(), $1, 'system', 'system', 'info', 'falsificado', 'x') returning id",
            fake_sequence,
        )
        fake_id = rows[0]["id"]
        whole = dev.get("/api/events/verify").json()
        checker.check(
            f"fila falsa con sequence {fake_sequence}: la cadena entera no dice intacta",
            not whole["intact"],
            str(whole),
        )
        single = dev.get("/api/events/verify", params={"event_id": str(fake_id)}).json()
        checker.check(
            f"fila falsa con sequence {fake_sequence}: verificada por id se detecta",
            not single["intact"],
            str(single),
        )
        execute("alter table events disable trigger events_no_change")
        try:
            execute("delete from events where id = $1", fake_id)
        finally:
            execute("alter table events enable trigger events_no_change")
        checker.check(
            f"fila falsa {fake_sequence} retirada: intacta",
            dev.get("/api/events/verify").json()["intact"],
        )


def extreme_dates(checker: Checker, dev: httpx.Client) -> None:
    """Fechas extremas (año 1 y año 9999) no deben romper ni verify() ni el listado."""
    for params in (
        {"date_from": "0001-01-01T00:00:00Z"},
        {"date_to": "9999-12-31T23:59:59.999999Z"},
    ):
        report = dev.get("/api/events/verify", params=params)
        checker.check(
            f"verify {params}", report.status_code == 200 and report.json()["intact"], report.text
        )
        listing = dev.get("/api/events/", params={**params, "size": 5})
        checker.check(f"listado {params}", listing.status_code == 200, listing.text)


def main() -> None:
    """Genera eventos, verifica la cadena entera y por partes, y prueba manipulaciones directas."""
    checker = Checker("Cadena de eventos")
    dev = dev_client()

    checker.section("1. los triggers bloquean lo que deben")
    triggers_block_writes(checker)

    checker.section("2. genero eventos y verifico")
    events = generate_events(dev)
    checker.check("hay eventos", len(events) >= 12)
    whole_chain_intact(checker, dev)
    single_event_checks(checker, dev, events)
    period_checks(checker, dev, events)

    checker.section("3. validaciones")
    validation_errors(checker, dev, events)

    checker.section("4. manipulaciones (como dueño de la base, quitando el trigger un momento)")
    edit_middle_event(checker, dev, events)
    delete_middle_event(checker, dev, events)
    delete_tail_scenarios(checker, dev, events)

    checker.section("5. el trigger desactivado se ve en el informe, y reactivarlo lo corrige")
    truncate_guard_reflected(checker, dev)

    checker.section("6. cabeza borrada")
    chain_head_deleted(checker, dev, events)

    checker.section("7. filas falsas con sequence <= 0 (el INSERT sigue permitido)")
    forged_rows(checker, dev)

    checker.section("8. fechas extremas por HTTP")
    extreme_dates(checker, dev)

    checker.finish()


if __name__ == "__main__":
    main()
