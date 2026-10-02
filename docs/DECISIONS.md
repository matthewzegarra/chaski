# Decisiones de diseño

Registro de decisiones tomadas cuando el prompt (`CLAUDE.md`) era ambiguo o requería concretar algo. Regla: la opción más simple que cumple el criterio de aceptación.

| # | Tema | Decisión | Motivo |
|---|---|---|---|
| D1 | Monorepo Python | Workspace de **uv** (`pyproject.toml` raíz). `libs/chaski_common` es dependencia de ruta de cada servicio. Imágenes `python:3.12-slim`. | Un solo lockfile y venv para desarrollo; imágenes reproducibles con `uv sync --frozen`. |
| D2 | Migraciones | Una sola cadena Alembic en `db/migrations` (SQL explícito) para `core`, `ops` y `gold`. Corre el servicio `migrate` en cada `docker compose up`. | El DDL queda legible y revisable; las vistas y los grants son SQL de todas formas. |
| D3 | Roles de BD | `chaski_admin` (dueño, solo migraciones y simulador), `chaski_app` (APIs: CRUD en core/ops, lectura en gold) y `chaski_readonly` (NL2SQL: solo `SELECT` sobre las 3 vistas, `statement_timeout=10s` y transacciones de solo lectura). | Mínimo privilegio; NL2SQL no puede leer PII aunque el validador fallara. |
| D4 | Tablas y columnas extra | `ops.idempotency_keys`, `ops.raw_ingest`, `ops.quarantine_records`; `transactions.counterparty_account` (regla R4), `transactions.description`, `accounts.number`, `customers.monthly_income` (scoring), `customers.kyc_decided_*`, `complaints.requires_review`/`reviewed_at`, `loans.disbursed_at`, `audit_log.reason`/`correlation_id`, `ai_interactions.blocked_by_shields`/`provider`, `fraud_alerts.details`/`resolved_*`. | Son necesarias para cumplir endpoints y reglas del prompt. |
| D5 | Auth dev | Con `AUTH_MODE=dev`, core-api expone `POST /api/v1/dev/token` (devuelve 404 en `entra`) que firma HS256 con `DEV_JWT_SECRET`. El selector del frontend lo llama. `AUTH_MODE=dev` se **rechaza al arrancar** si `CHASKI_ENV=PROD`. | El secreto nunca llega al bundle del navegador. |
| D5b | Auth Entra | RS256 validado con JWKS del tenant (`PyJWKClient`), `aud` = `ENTRA_AUDIENCE`, `iss` v1 o v2 del tenant. Roles del claim `roles`; `customer_id` del claim `customer_id` / `extension_customer_id`. | App Roles estándar de Entra ID. |
| D6 | Auditoría | `chaski_common.audit` escribe en `ops.audit_log` en una transacción propia (sobrevive al rollback del request). Los 403 de `require_roles`/`require_customer`/ownership se auditan automáticamente. | Requisito "todo 403 se registra". |
| D7 | Config del frontend | Imagen nginx sin privilegios que genera `env.js` al arrancar desde variables `CHASKI_*`. | Misma imagen en local y Azure; solo cambian variables. |
| D8 | Analítica | `ANALYTICS_DB_URL` + `ANALYTICS_DIALECT=postgres\|tsql`. NL2SQL valida con sqlglot y transpila a T-SQL para Azure SQL. | Local usa el esquema `gold` del mismo Postgres. |
| D9 | Confirmación del asistente | ia-api nunca ejecuta `block_card`/`create_complaint`: devuelve `pending_action`; la UI confirma y llama al endpoint real de core-api. | Confirmación explícita del cliente sin estado en el servidor. |
| D10 | Herramientas del asistente | ia-api llama a cuentas-api/core-api reenviando el JWT del usuario. | El `customer_id` siempre sale del token, nunca del modelo. |
| D11 | Plazo de quejas | 15 días hábiles = lunes a viernes menos feriados nacionales de Perú (fijos + Jueves/Viernes Santo). | `chaski_common.business_days`. |
| D12 | Simulador | Carga inicial con `COPY` (≈4 s). Fechas relativas a "ahora" con semilla fija (misma estructura en cada corrida). `--live` genera tráfico **vía cuentas-api** para que pase por el motor de fraude y Eventstream. | Reproducible y realista para la demo. |
| D12b | Transferencias del simulador | Las transferencias históricas no generan el movimiento espejo en la cuenta destino. | Simplicidad; no afecta KPIs ni reglas. |
| D13 | Tests de backend | pytest contra la BD `chaski_test` del Postgres de Compose (migrada con Alembic al inicio de la sesión, tablas vaciadas por test). Si Postgres no está disponible, los tests de BD se saltan con un mensaje. | Tests reales contra Postgres sin dependencias extra. |
| D14 | UI compartida | Componentes shadcn/ui, auth, cliente API, tipos y formateadores en `packages/shared`. | Evita duplicar entre cliente y consola. |
| D15 | Rate limit | Ventana fija de 1 minuto por IP en memoria. | Suficiente con 1 réplica (scale-to-zero); con más réplicas se movería a Front Door/APIM. |
| D16 | Paquetes Python | Los paquetes se llaman `cuentas_api`, `core_api`, `ia_api`, `chaski_simulator` (no `app`/`simulator`). | Conviven en un único venv de workspace sin colisiones de nombre. |
| D17 | SQLAlchemy síncrono | Sesiones sync; FastAPI ejecuta los endpoints `def` en su threadpool. | Más simple de testear; la carga esperada es baja. |
| D18 | Logs | structlog JSON a stdout; un procesador redacta DNI, emails, teléfonos y secuencias de 13–19 dígitos en **todos** los campos (también en logs de librerías). Access log propio (método, ruta, status, duración); el de uvicorn se desactiva. | Requisito "cero PII/PAN en logs". |
| D19 | Gold local | Rentabilidad: depósitos con tasa de transferencia interna 6 % anual; préstamos/tarjetas con costo de fondeo 5 %; provisiones según bucket SBS (Normal 1 %, CPP 5 %, Deficiente 25 %, Dudoso 60 %, Pérdida 100 %). | Datos sintéticos coherentes para Insights y NL2SQL. |
