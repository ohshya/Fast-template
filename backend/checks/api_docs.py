import re
from pathlib import Path

from checks.common import Checker, dev_client

ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[A-Za-z0-9_{}/-]+)")
HEADING = re.compile(r"^#{3,4} .*$", re.MULTILINE)


def normalize(path: str) -> str:
    """Ruta sin nombres de parámetros ni barra final, para comparar documento y OpenAPI."""
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/")


def main() -> None:
    """Comprueba que backend/API.md documenta cada endpoint, permiso y código de error reales."""
    checker = Checker("api_docs")
    document = (Path(__file__).resolve().parents[1] / "API.md").read_text(encoding="utf-8")
    mentioned = {(method, normalize(path)) for method, path in ENDPOINT.findall(document)}
    headings = {
        (method, normalize(path))
        for heading in HEADING.findall(document)
        for method, path in ENDPOINT.findall(heading)
    }
    session = dev_client()

    checker.section("endpoints")
    spec = session.get("/openapi.json").json()
    real = {
        (method.upper(), normalize(path))
        for path, operations in spec["paths"].items()
        for method in operations
    }
    for method, path in sorted(real):
        checker.check(f"{method} {path} está en API.md", (method, path) in mentioned, "falta")
    for method, path in sorted(headings - real):
        checker.check(
            f"{method} {path} existe",
            False,
            "un encabezado de API.md nombra un endpoint que no existe",
        )

    checker.section("permisos")
    for item in session.get("/api/system/permissions").json():
        checker.check(f"permiso {item['key']} está en API.md", item["key"] in document, "falta")

    checker.section("códigos de error")
    for entry in session.get("/api/system/errors").json():
        checker.check(f"código {entry['code']} está en API.md", entry["code"] in document, "falta")
    checker.finish()


if __name__ == "__main__":
    main()
