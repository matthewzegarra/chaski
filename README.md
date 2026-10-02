# Interbank CHASKI · Banca Inteligente en Tiempo Real

Proyecto final IT for Banking (UTP + Interbank). Monorepo con la Chaski App (cliente), el Chaski Control Center (consola), tres APIs FastAPI, migraciones y un simulador de datos.

> Estado: **F1 (fundaciones)**. El README completo llega en F7.

## Levantar en local

```bash
cp .env.example .env
docker compose up -d --build          # postgres + migraciones + APIs
docker compose run --rm seed          # o `make seed`: datos sintéticos
```

- cuentas-api: http://localhost:8001/docs
- core-api: http://localhost:8002/docs
- ia-api: http://localhost:8003/docs

## Desarrollo

```bash
uv sync --all-packages                # venv del workspace Python
uv run pytest                         # requiere el postgres de compose
uv run ruff check . && uv run mypy libs/chaski_common/src simulator/src
```

Decisiones de diseño: [docs/DECISIONS.md](docs/DECISIONS.md).
