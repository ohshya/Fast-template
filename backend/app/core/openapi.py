from fastapi import FastAPI

from app.core.permissions import PERMISSIONS, Scope


def document_permissions(app: FastAPI, route_map: dict[int, str]) -> None:
    """Pone en OpenAPI el resumen y el permiso de cada endpoint, tomados del catálogo."""
    scopes = {
        Scope.PUBLIC: "público, sin sesión",
        Scope.AUTHENTICATED: "cualquier usuario con sesión",
        Scope.ROLE: "usuarios cuyo rol lo incluya (y los dev)",
        Scope.DEV: "solo usuarios dev",
    }
    schema = app.openapi()
    for permission_id, endpoint in route_map.items():
        method, path = endpoint.split(" ", 1)
        operation = schema["paths"].get(path, {}).get(method.lower())
        if operation is None:
            continue
        declared = PERMISSIONS[permission_id]
        operation["summary"] = declared.description
        operation["x-permission"] = {
            "id": declared.id,
            "key": declared.key,
            "scope": declared.scope.value,
        }
        note = (
            f"**Permiso:** `{declared.key}` (id {declared.id}). Acceso: {scopes[declared.scope]}."
        )
        operation["description"] = f"{operation.get('description', '')}\n\n{note}".strip()
