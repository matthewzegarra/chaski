# .github/workflows/

Pipelines de GitHub Actions (CI/CD completo para `cuentas-api`: lint, mypy, tests con cobertura >= 70 %, build de imagen, despliegue a Container Apps por entorno).

**Fuera del alcance de este prompt**: se construye con otro prompt. Comandos que el CI debe reutilizar: `uv run ruff check .`, `uv run mypy ...`, `uv run pytest services/cuentas-api --cov=cuentas_api --cov-fail-under=70`.
