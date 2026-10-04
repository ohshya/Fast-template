import logging
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.context import under_api

logger = logging.getLogger("uvicorn.error")


class Scope(StrEnum):
    """Quién puede entrar a un endpoint."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ROLE = "role"
    DEV = "dev"


@dataclass(frozen=True, slots=True)
class Permission:
    """Identificador de un endpoint y, a la vez, la llave que lo abre."""

    id: int
    key: str
    group: str
    description: str
    scope: Scope = Scope.ROLE

    @property
    def assignable(self) -> bool:
        """Si se puede marcar en un rol. Solo los de alcance ROLE."""
        return self.scope is Scope.ROLE


PERMISSIONS: dict[int, Permission] = {}


def permission(
    id: int, key: str, group: str, description: str, scope: Scope = Scope.ROLE
) -> Permission:
    """Declara un permiso. Falla si el id o la clave ya existen."""
    if id in PERMISSIONS:
        raise RuntimeError(f"El permiso {id} ({key}) ya lo usa {PERMISSIONS[id].key}")
    if any(existing.key == key for existing in PERMISSIONS.values()):
        raise RuntimeError(f"La clave de permiso {key} ya existe")
    declared = Permission(id, key, group, description, scope)
    PERMISSIONS[id] = declared
    return declared


@dataclass(frozen=True, slots=True)
class CrudPermissions:
    """Los siete permisos de un recurso CRUD."""

    list: Permission
    read: Permission
    create: Permission
    update: Permission
    delete: Permission
    restore: Permission
    hard_delete: Permission


def crud_permissions(base: int, key: str, group: str, noun: str) -> CrudPermissions:
    """Siete permisos CRUD con ids base+1 a base+7. `hard_delete` es solo dev."""
    return CrudPermissions(
        list=permission(base + 1, f"{key}.list", group, f"Listar {noun}"),
        read=permission(base + 2, f"{key}.read", group, f"Ver el detalle de {noun}"),
        create=permission(base + 3, f"{key}.create", group, f"Crear {noun}"),
        update=permission(base + 4, f"{key}.update", group, f"Editar {noun}"),
        delete=permission(base + 5, f"{key}.delete", group, f"Eliminar {noun} (reversible)"),
        restore=permission(base + 6, f"{key}.restore", group, f"Restaurar {noun}"),
        hard_delete=permission(
            base + 7, f"{key}.hard_delete", group, f"Borrar {noun} definitivamente", Scope.DEV
        ),
    )


def assignable_ids() -> frozenset[int]:
    """Identificadores que un rol puede contener."""
    return frozenset(item.id for item in PERMISSIONS.values() if item.assignable)


def unknown_permissions(ids: list[int]) -> list[int]:
    """Identificadores que no existen o que no se pueden asignar a un rol."""
    return sorted(set(ids) - assignable_ids())


def _declared_permissions(dependant: Any) -> list[Permission]:
    """Permisos que declara la cadena de dependencias de una ruta."""
    found: list[Permission] = []
    pending = list(dependant.dependencies)
    while pending:
        dependency = pending.pop()
        declared = getattr(dependency.call, "permission", None)
        if isinstance(declared, Permission):
            found.append(declared)
        pending.extend(dependency.dependencies)
    return found


def _endpoints(app: FastAPI) -> Iterator[tuple[str, list[Permission]]]:
    """Cada endpoint de /api como ("GET /api/users/", permisos que declara)."""
    for route in app.routes:
        resolver: Any = getattr(route, "effective_route_contexts", None)
        contexts = list(resolver()) if resolver is not None else []
        if not contexts and isinstance(route, APIRoute):
            contexts = [route]
        for context in contexts:
            if not under_api(str(context.path)):
                continue
            methods = sorted(set(context.methods or ()) - {"HEAD", "OPTIONS"})
            label = f"{methods[0] if methods else 'GET'} {context.path}"
            yield label, _declared_permissions(context.dependant)


def verify_route_permissions(app: FastAPI) -> dict[int, str]:
    """Exige un permiso propio por ruta; devuelve {permiso: endpoint}."""
    problems: list[str] = []
    route_map: dict[int, str] = {}

    for endpoint, declared in _endpoints(app):
        if not declared:
            problems.append(f"{endpoint}: no declara permiso. Añade `requires(...)` a la firma.")
        elif len(declared) > 1:
            keys = ", ".join(item.key for item in declared)
            problems.append(f"{endpoint}: declara varios permisos ({keys}); debe ser uno solo.")
        elif declared[0].id in route_map:
            problems.append(
                f"{endpoint}: usa el permiso {declared[0].key}, "
                f"que ya usa {route_map[declared[0].id]}."
            )
        else:
            route_map[declared[0].id] = endpoint

    if problems:
        raise RuntimeError("Rutas mal declaradas:\n  - " + "\n  - ".join(problems))

    if not route_map:
        raise RuntimeError(
            "No se encontró ningún endpoint con permiso: ¿cambió la API interna de FastAPI?"
        )

    unused = sorted(set(PERMISSIONS) - set(route_map))
    if unused:
        logger.warning("Permisos del catálogo sin endpoint asociado: %s", unused)
    return route_map
