"""Generates docs/API.md from the OpenAPI/route metadata of the three services.

The "Roles" column is read from the auth dependencies actually attached to each route
(`require_roles`, `require_customer`, `get_current_user`), so the document cannot drift
from what the code enforces. Run: `uv run python scripts/gen_api_docs.py` (or `make docs`).
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Settings validation needs a dev secret to import the apps; nothing is started.
os.environ.setdefault("DEV_JWT_SECRET", "docs-only-secret-0123456789abcdef0123")
os.environ.setdefault("AUTH_MODE", "dev")

from api_descriptions import DESCRIPTIONS  # noqa: E402
from chaski_common.app import API_PREFIX  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

SERVICES = [
    ("cuentas-api", "cuentas_api.main", "8001", "Saldo, movimientos, transferencias y pagos con tarjeta. Servicio crítico con CI/CD completo."),
    ("core-api", "core_api.main", "8002", "Clientes, onboarding/KYC, tarjetas, préstamos, quejas, fraude, operación, pipelines, analítica, seguridad, DevOps y demo."),
    ("ia-api", "ia_api.main", "8003", "Casos de uso de IA: clasificador de quejas, scoring, asistente, resumen ejecutivo, NL2SQL, KYC y métricas."),
]  # fmt: skip


def api_routes(routes: list[Any], prefix: str = "") -> list[tuple[str, APIRoute]]:
    """(full_path, route) pairs. FastAPI >= 0.140 keeps included routers nested
    (`_IncludedRouter.original_router`) instead of flattening them into app.routes."""
    out: list[tuple[str, APIRoute]] = []
    for r in routes:
        if isinstance(r, APIRoute):
            out.append((prefix + r.path, r))
        elif hasattr(r, "original_router"):
            ctx = getattr(r, "include_context", None)
            inner = getattr(ctx, "prefix", None) if ctx is not None else None
            out += api_routes(
                r.original_router.routes, prefix + (inner if inner is not None else API_PREFIX)
            )
    return out


def roles_of(route: APIRoute) -> str:
    found: list[str] = []

    def walk(dep: Any) -> None:
        call = getattr(dep, "call", None)
        roles = getattr(call, "__chaski_roles__", None)
        if roles:
            found.extend(r for r in roles if r not in found)
        for sub in getattr(dep, "dependencies", []):
            walk(sub)

    walk(route.dependant)
    if "Cualquier usuario autenticado" in found and len(found) > 1:
        found.remove("Cualquier usuario autenticado")
    if found:
        return ", ".join(found)
    if route.path.endswith("/webhook"):
        return "Firma HMAC `X-Chaski-Signature` (Fabric Activator)"
    if "/dev/" in route.path:
        return "Público, solo con `AUTH_MODE=dev`"
    return "Público"


def summary_of(route: APIRoute) -> str:
    if route.summary:
        return route.summary
    doc = (route.endpoint.__doc__ or "").strip().splitlines()
    if doc and doc[0]:
        return doc[0].strip()
    return route.name.replace("_", " ").capitalize()


def main() -> None:
    lines = [
        "# API de CHASKI",
        "",
        "> Documento **generado** con `scripts/gen_api_docs.py` a partir de las rutas reales de cada servicio",
        "> (la columna *Roles* se lee de las dependencias de autorización del código). No editar a mano.",
        "",
        "## Convenciones",
        "",
        "- Prefijo `/api/v1`. OpenAPI interactivo en `http://localhost:<puerto>/docs` de cada servicio.",
        "- `GET /health` (liveness) y `GET /ready` (verifica la base de datos) en los tres servicios, sin autenticación.",
        "- Autenticación: `Authorization: Bearer <JWT>` de Entra ID (`AUTH_MODE=entra`) o el emitido por `POST /api/v1/dev/token` en local (`AUTH_MODE=dev`).",
        "- Los roles salen del claim `roles` (App Roles). Un cliente solo accede a sus datos: el `customer_id` sale del token, nunca del body.",
        '- Todo 403 y todo acceso a PII queda en `ops.audit_log`. Los errores tienen la forma `{"detail": "..."}`; los 500 incluyen `correlation_id`.',
        "- `X-Correlation-ID`: se acepta y se devuelve en cada respuesta, y aparece en los logs JSON.",
        "- `POST /transfers` exige `Idempotency-Key` (misma key y mismo body → misma respuesta; key con otro body → 409).",
        "- Montos: números en soles o dólares con 2 decimales. Fechas: ISO 8601 en UTC.",
        "",
    ]
    missing: list[str] = []
    for name, module, port, description in SERVICES:
        sys.path.insert(0, str(ROOT / "services" / name / "src"))
        app = __import__(module, fromlist=["app"]).app
        groups: dict[str, list[tuple[str, APIRoute]]] = defaultdict(list)
        for full_path, route in api_routes(app.routes):
            if full_path.startswith(API_PREFIX):
                groups[(route.tags or ["otros"])[0]].append((full_path, route))
        lines += [f"## {name} (`:{port}`)", "", description, ""]
        for tag in sorted(groups):
            lines += [
                f"### {tag.capitalize()}",
                "",
                "| Método | Ruta | Descripción | Roles |",
                "|---|---|---|---|",
            ]
            for full_path, route in sorted(groups[tag], key=lambda x: (x[0], sorted(x[1].methods))):
                for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                    path = full_path.removeprefix(API_PREFIX)
                    key = f"{method} {path}"
                    if key not in DESCRIPTIONS:
                        missing.append(key)
                    text = DESCRIPTIONS.get(key, summary_of(route))
                    lines.append(f"| `{method}` | `{path}` | {text} | {roles_of(route)} |")
            lines.append("")
    if missing:
        raise SystemExit(
            "Endpoints sin descripción en scripts/api_descriptions.py: " + ", ".join(missing)
        )
    out = ROOT / "docs" / "API.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {out.relative_to(ROOT)} ({sum(1 for line in lines if line.startswith('| `'))} endpoints)"
    )


if __name__ == "__main__":
    main()
