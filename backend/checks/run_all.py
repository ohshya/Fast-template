import os
import subprocess
import sys
import time

from checks.common import execute

MODULES = (
    "smoke",
    "filters",
    "login",
    "idempotency",
    "hardening",
    "chain",
    "attack",
    "attack_session",
    "api_docs",
)


def main() -> None:
    """Ejecuta las comprobaciones en orden y resume el resultado; sale con 1 si alguna falla."""
    selected = sys.argv[1:] or list(MODULES)
    unknown = [name for name in selected if name not in MODULES]
    if unknown:
        sys.exit(
            f"Comprobaciones desconocidas: {', '.join(unknown)}. Disponibles: {', '.join(MODULES)}"
        )
    results: list[tuple[str, bool, float]] = []
    for name in selected:
        execute("DELETE FROM login_attempts")
        execute("DELETE FROM fastapi_idempotency_requests")
        print(f"\n{'=' * 70}\n{name}\n{'=' * 70}", flush=True)
        started = time.perf_counter()
        done = subprocess.run([sys.executable, "-m", f"checks.{name}"], env=os.environ.copy())
        results.append((name, done.returncode == 0, time.perf_counter() - started))
    print(f"\n{'=' * 70}\nResumen\n{'=' * 70}")
    for name, passed, seconds in results:
        print(f"{'OK   ' if passed else 'FALLA'} {name:16} {seconds:6.1f} s")
    if not all(passed for _, passed, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
