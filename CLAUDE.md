# PROMPT PARA CLAUDE CODE · Interbank CHASKI (Web + APIs)

> Copia este archivo en la raíz del repo como `CLAUDE.md` o pásalo como primer mensaje a Claude Code.

---

## 0. Rol y forma de trabajo

Eres un **Senior Full-Stack Engineer y Cloud Architect** especializado en banca digital y Azure. Vas a construir el código de **Interbank CHASKI · Banca Inteligente en Tiempo Real**, proyecto final del curso IT for Banking (UTP + Interbank).

Reglas de trabajo:
1. Trabaja **por fases** (sección 15). Al terminar cada fase: corre los tests, muestra un resumen de lo hecho y **detente para que confirme** antes de seguir.
2. Antes de escribir código de una fase, muestra un plan corto (archivos a crear y decisiones).
3. Todo debe correr **en local con Docker Compose** sin Azure (modo mock) y luego en Azure solo cambiando variables de entorno.
4. UI 100% en **español**. Código, nombres de variables y commits en inglés.
5. Si algo de este documento es ambiguo, elige la opción más simple que cumpla el criterio de aceptación y anótala en `docs/DECISIONS.md`.

---

## 1. Contexto del negocio

CHASKI es la plataforma de un banco 100% digital de Interbank, construida en Azure:
- **Chaski App:** lo que usa el cliente (onboarding, saldo, movimientos, pagos, préstamos, quejas, asistente IA).
- **Chaski Control Center:** consola web del banco, cada rol ve solo sus módulos.
- **Chaski Core:** microservicios del negocio.
- **Chaski Insights:** datos, DW, analítica, IA (el pipeline de datos y Fabric se construyen aparte; aquí solo se consumen sus tablas).
- **Chaski Guard:** detección de fraude (aquí se implementa un motor de reglas local + un webhook para recibir alertas de Fabric).

Presupuesto Azure: USD 100 (Azure for Students). Todo debe ser liviano y escalar a cero.

---

## 2. Alcance de este prompt

Incluye:
- `apps/cliente` (Chaski App, PWA)
- `apps/consola` (Chaski Control Center)
- `services/cuentas-api`, `services/core-api`, `services/ia-api` (FastAPI)
- `simulator/` (generador de datos)
- `db/` (migraciones)
- `docker-compose.yml`, Dockerfiles, tests

No incluye (se hará con otros prompts): Bicep, GitHub Actions, flujos Prefect, Power BI, Fabric. Deja carpetas vacías con README: `infra/`, `.github/workflows/`, `data/`, `powerbi/`, `fabric/`.

---

## 3. Stack obligatorio

| Capa | Tecnología |
|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Router, Recharts, lucide-react |
| Auth frontend | MSAL React (`@azure/msal-react`) con App Roles de Entra ID |
| Monorepo front | pnpm workspaces (`apps/*`, `packages/shared`) |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, httpx, structlog |
| BD core | PostgreSQL 16 |
| BD analítica | Azure SQL en Azure; en local un esquema `gold` dentro del mismo Postgres |
| IA | SDK `openai` (cliente `AzureOpenAI`) + Azure AI Content Safety + Azure AI Document Intelligence, todo detrás de interfaces con implementación **Mock** |
| Observabilidad | OpenTelemetry → Application Insights (`azure-monitor-opentelemetry`), deshabilitado en local |
| Tests | pytest + httpx (backend), Vitest + Testing Library (frontend) |
| Calidad | ruff, mypy (backend); eslint, prettier (frontend) |

---

## 4. Estructura del repo

```
chaski/
├── apps/
│   ├── cliente/            # Chaski App (PWA)
│   └── consola/            # Chaski Control Center
├── packages/shared/        # tipos TS, cliente API, formateadores (PEN, fechas)
├── services/
│   ├── cuentas-api/        # saldo, movimientos, transferencias, pagos con tarjeta
│   ├── core-api/           # clientes, onboarding, tarjetas, préstamos, quejas, consola, analítica, auditoría
│   └── ia-api/             # clasificador de quejas, scoring, asistente, resumen ejecutivo, NL2SQL
├── libs/chaski_common/     # paquete Python compartido: auth JWT, roles, auditoría, masking, logging, settings
├── genai/prompts/          # prompts versionados (.md con front-matter: id, version, owner)
├── db/migrations/          # Alembic
├── simulator/              # Faker: clientes, cuentas, tarjetas, préstamos, transacciones, quejas
├── docs/                   # DECISIONS.md, API.md, DEMO.md
├── infra/ .github/workflows/ data/ powerbi/ fabric/   # vacíos con README
└── docker-compose.yml
```

---

## 5. Modelo de datos (PostgreSQL, esquema `core`)

Tablas mínimas (agrega índices y FKs):
- `customers` (id uuid, document_type, document_number, first_name, last_name, email, phone, birth_date, segment [MASIVO, PREFERENTE, PYME], region, kyc_status [PENDIENTE, APROBADO, RECHAZADO], risk_level, created_at)
- `accounts` (id, customer_id, product [AHORRO_SOLES, AHORRO_DOLARES], currency [PEN, USD], balance numeric(14,2), status, opened_at)
- `cards` (id, customer_id, account_id null, type [DEBITO, CREDITO], **token** (nunca PAN), last4, brand, credit_limit, status [ACTIVA, BLOQUEADA], created_at)
- `loans` (id, customer_id, product [CONSUMO], amount, term_months, rate_tea, status [SOLICITADO, APROBADO, RECHAZADO, DESEMBOLSADO, CANCELADO], days_past_due, outstanding_balance, ai_score, ai_explanation, decided_by, decided_at, created_at)
- `loan_installments` (loan_id, number, due_date, amount, paid_at)
- `transactions` (id, account_id, card_id null, type [DEPOSITO, RETIRO, TRANSFERENCIA_IN, TRANSFERENCIA_OUT, PAGO_TARJETA, PAGO_SERVICIO, COMISION, INTERES], amount, currency, channel [APP, WEB, POS, ATM], merchant, city, created_at)
- `complaints` (id, customer_id, subject, body, channel, status [NUEVA, EN_REVISION, RESUELTA], ai_category, ai_urgency, ai_confidence, ai_reason, ai_suspicious bool, final_category, reviewed_by, created_at, due_at)
- `kyc_documents` (id, customer_id, blob_path, extracted_json, extraction_confidence, created_at)

Esquema `ops`:
- `audit_log` (id, actor_id, actor_role, action, resource, resource_id, pii_accessed bool, allowed bool, ip, created_at)
- `fraud_alerts` (id, transaction_id, customer_id, rule, score, source [RULES, FABRIC], status [ABIERTA, CONFIRMADA, DESCARTADA], created_at)
- `pipeline_runs` (id, flow_name, status, started_at, finished_at, rows_in, rows_ok, rows_quarantined, error)
- `quality_checks` (run_id, check_name, table_name, passed bool, failed_count)
- `ai_interactions` (id, use_case, prompt_id, prompt_version, input_redacted, output, latency_ms, tokens_in, tokens_out, confidence, human_override, created_at)

Esquema `gold` (en local lo llena el simulador; en Azure vive en Azure SQL):
- `dim_customer`, `dim_product`, `dim_region`, `dim_date`, `dim_delinquency_bucket` (Normal, CPP, Deficiente, Dudoso, Pérdida)
- `fact_profitability_monthly` (product, segment, region, month, interest_income, fees, funding_cost, provisions, margin)
- `fact_portfolio_daily` (loan_id, date, outstanding_balance, days_past_due, bucket, region, segment)
- Vistas permitidas para NL2SQL: `gold.v_rentabilidad`, `gold.v_morosidad`, `gold.v_clientes_resumen`

---

## 6. Servicios y endpoints

Todas las APIs: prefijo `/api/v1`, OpenAPI habilitado, `GET /health` (liveness) y `GET /ready` (verifica BD), logs JSON con `correlation_id`.

### cuentas-api (servicio crítico, es el que tendrá CI/CD completo)
- `GET /accounts/me` · `GET /accounts/{id}/balance` · `GET /accounts/{id}/movements?from&to&page`
- `POST /transfers` (valida saldo, idempotency-key obligatorio)
- `POST /card-payments` (simula pago POS/online)
- Cada transacción: (1) guarda en BD, (2) evalúa **motor de reglas de fraude** (ver 8.6), (3) si `EVENTSTREAM_CONNECTION_STRING` existe, publica el evento JSON a Fabric Eventstream (endpoint compatible con Event Hubs, SDK `azure-eventhub`).

### core-api
- Clientes: `GET /customers` (filtros, paginado), `GET /customers/{id}` (con masking según rol), `POST /customers/{id}/reveal-pii` (requiere motivo, se audita)
- Onboarding: `POST /onboarding` (datos + imagen DNI) → llama a ia-api `/kyc/extract` → crea cliente `PENDIENTE`; `POST /onboarding/{id}/decision`
- Tarjetas: `GET /cards/me`, `POST /cards/{id}/block`, `POST /cards/{id}/unblock`
- Préstamos: `POST /loans` (cliente), `GET /loans` (consola), `POST /loans/{id}/decision` (solo Riesgos)
- Quejas: `POST /complaints` (cliente) → llama a ia-api `/complaints/classify`; `GET /complaints`; `POST /complaints/{id}/review`
- Fraude: `GET /fraud/alerts`, `POST /fraud/alerts/{id}/resolve`, `POST /fraud/webhook` (para Fabric Activator, autenticado con header `X-Chaski-Signature` HMAC usando secreto de Key Vault)
- Operación: `GET /ops/kpis` (transacciones hoy, clientes nuevos, cartera, % mora, alertas abiertas)
- Pipelines: `GET /ops/pipelines`, `GET /ops/pipelines/{id}/checks`, `GET /ops/quarantine`, `POST /ops/pipelines/run` (en Azure inicia el Container Apps Job vía REST de ARM con Managed Identity; en local simula una corrida)
- Analítica: `GET /analytics/profitability`, `GET /analytics/delinquency` (lee de `ANALYTICS_DB_URL`)
- Seguridad: `GET /security/audit`, `GET /security/secrets-metadata` (lista nombre, fecha de creación, expiración y versión de secretos en Key Vault, **nunca el valor**; en local devuelve mock)
- DevOps: `GET /devops/deployments` (últimas ejecuciones de GitHub Actions vía API con token de solo lectura; en local mock)
- Demo: `POST /demo/inject-bad-record` (inserta un registro corrupto que el pipeline mandará a cuarentena), `POST /demo/fraud-burst` (genera 8 transferencias en 60 s para disparar fraude). Solo habilitados si `DEMO_MODE=true` y rol Admin.

### ia-api
- `POST /kyc/extract` (Document Intelligence `prebuilt-idDocument`; si falla, `prebuilt-read` + regex de DNI de 8 dígitos)
- `POST /complaints/classify`
- `POST /loans/score`
- `POST /assistant/chat` (Chaski Asistente)
- `POST /reports/executive-summary`
- `POST /analytics/ask` (NL2SQL)
- `GET /ai/health-metrics` (precisión IA vs humano, tasa de revisión manual, latencia, bloqueos por Prompt Shields)

---

## 7. Seguridad (no negociable)

1. **Autenticación:** JWT de Entra ID validado en cada servicio (issuer, audience, firma con JWKS). Variable `AUTH_MODE=entra|dev`. En `dev` existe un selector de usuario/rol en el frontend que emite un token firmado localmente (solo local).
2. **Roles (App Roles):** `Admin`, `Operaciones`, `Atencion`, `Riesgos`, `Fraude`, `Direccion`, `Marketing`, `TI`. Clientes: rol `Cliente` con `customer_id` en el claim (en dev se mapea).
3. **Autorización:** decorador `require_roles(...)` en cada endpoint. Un cliente solo accede a sus propios recursos (el `customer_id` sale del token, jamás del body).
4. **Masking de PII:** DNI `****5678`, email `m***@dominio.com`, teléfono `***-***-123`. Solo `Atencion` y `Admin` pueden revelar con `reveal-pii` + motivo. Todo acceso a PII y todo 403 se registra en `ops.audit_log`.
5. **Tarjetas:** nunca almacenar ni loguear PAN. Solo token + last4.
6. **Secretos:** solo por variables de entorno. En Azure, las variables apuntan a Key Vault (referencias de Container Apps) y se usa **Managed Identity** (`DefaultAzureCredential`). Prohibido hardcodear.
7. **Logs:** sin PII. Middleware que redacta DNI, emails, teléfonos y números de 13-19 dígitos.
8. Headers de seguridad, CORS restringido a los dominios de las apps, rate limiting básico en memoria.

---

## 8. IA generativa

Interfaz `LLMProvider` con `AzureOpenAIProvider` y `MockProvider` (`AI_MODE=azure|mock`). Todos los prompts se cargan desde `genai/prompts/*.md`, con `id` y `version` registrados en `ops.ai_interactions`.

Pipeline común para toda llamada:
`redactar PII` → `Prompt Shields (Content Safety)` → `LLM (temperature 0, salida JSON con schema)` → `validar schema` → `registrar en ai_interactions`.

### 8.1 Clasificador de quejas
- Categorías: `FRAUDE, COBRO_INDEBIDO, TARJETA, PRESTAMO, CANAL_DIGITAL, OTRO`. Urgencia: `ALTA, MEDIA, BAJA`.
- Few-shot con 3 ejemplos. Salida: `{categoria, urgencia, confianza, motivo, sospechosa}`.
- `sospechosa=true` si Prompt Shields detecta inyección o el texto intenta dar instrucciones al sistema.
- Regla: `FRAUDE` o `confianza < 0.8` o `sospechosa` → cola de revisión humana obligatoria. `due_at` = fecha + 15 días hábiles (plazo regulatorio de respuesta).

### 8.2 Scoring de préstamo
- Score base por reglas (ingresos, endeudamiento, historial, mora previa) + explicación del LLM en lenguaje simple. La IA **sugiere**; la decisión final siempre es de un usuario `Riesgos` en la consola.

### 8.3 Chaski Asistente (cliente)
- Function calling con herramientas: `get_balance`, `list_movements`, `explain_charge`, `block_card`, `create_complaint`.
- El `customer_id` se inyecta desde el token en el backend; el modelo nunca lo elige.
- `block_card` y `create_complaint` requieren confirmación explícita del cliente en la UI (botón "Confirmar") antes de ejecutarse.
- Si la pregunta no es bancaria o no hay datos, responde que no puede ayudar con eso. Nunca inventa saldos: todo número viene de una herramienta.

### 8.4 Resumen ejecutivo
- Calcula KPIs con SQL sobre `gold`, los pasa al LLM para redactar. **Validador:** extrae todos los números del texto y verifica que existan en los KPIs (tolerancia de redondeo). Si falla, marca `requiere_revision` y no lo publica.

### 8.5 NL2SQL ("Pregúntale al banco")
- Solo `SELECT` sobre las vistas permitidas. Validar con `sqlglot`: una sola sentencia, sin DML/DDL, solo tablas de la allowlist, agregar `LIMIT 500`. Ejecutar con usuario de solo lectura y timeout de 10 s. Devolver: respuesta, tabla, sugerencia de gráfico y **la SQL ejecutada**.

### 8.6 Motor de reglas de fraude (Chaski Guard, plan local)
- R1: más de 5 transferencias del mismo cliente en 2 minutos.
- R2: monto > 3 veces el promedio de los últimos 30 días del cliente.
- R3: pago con tarjeta en ciudad distinta a la última transacción en menos de 30 minutos.
- R4: transferencia > S/ 5,000 a beneficiario nuevo.
- Genera `fraud_alerts` con `source=RULES`. Fabric enviará `source=FABRIC` por el webhook.

---

## 9. Chaski App (cliente, PWA móvil primero)

Pantallas:
1. **Bienvenida / login**
2. **Onboarding en 3 pasos:** datos personales → foto del DNI (input file con `capture`) → confirmación (muestra datos extraídos para que el cliente los valide). Estado "en revisión".
3. **Inicio:** saldo de cuentas, tarjetas (con last4), últimos movimientos, accesos rápidos.
4. **Movimientos:** lista con filtros y detalle.
5. **Transferir / Pagar:** formulario con confirmación y comprobante.
6. **Tarjetas:** bloquear / desbloquear.
7. **Préstamo:** simulador (monto, plazo, cuota estimada) → solicitud → seguimiento de estado.
8. **Reclamos:** formulario + historial con estado.
9. **Chaski Asistente:** chat flotante con tarjetas de confirmación para acciones.

---

## 10. Chaski Control Center (consola del banco)

Layout: sidebar con módulos filtrados por rol, header con usuario, rol activo y entorno (DEV/TEST/PROD).

| Módulo | Roles | Contenido |
|---|---|---|
| Centro de Operaciones | Todos | KPIs en vivo (refresco 15 s), gráfico de transacciones por hora, salud de APIs (llama a `/health` de cada servicio) |
| Clientes y KYC | Atencion, Admin | Tabla de clientes con masking, bandeja de onboarding con datos extraídos del DNI, aprobar/rechazar, "Revelar PII" con motivo |
| Préstamos | Riesgos | Solicitudes, score IA + explicación, aprobar/rechazar, cartera con días de atraso |
| Centro de Quejas IA | Atencion | Bandeja con categoría, urgencia, confianza, badge "Sospechosa", cola de revisión, corregir etiqueta, días restantes al vencimiento |
| Chaski Guard (Fraude) | Fraude | Alertas en vivo (refresco 5 s), regla disparada, fuente (RULES/FABRIC), confirmar/descartar, bloquear tarjeta |
| Chaski Insights (Analítica) | Direccion, Riesgos, Marketing | Rentabilidad por producto/segmento, morosidad por bucket y región (Recharts), barra "Pregúntale al banco" (NL2SQL), botón "Generar resumen ejecutivo". Si existe `VITE_POWERBI_EMBED_URL`, pestaña con iframe de Power BI |
| Data Pipelines | TI, Admin | Corridas, checks de calidad pass/fail, cuarentena, botón "Ejecutar pipeline" |
| Salud de IA | TI, Admin | Precisión IA vs humano, % revisión manual, intentos de inyección bloqueados, latencia por caso de uso, versión de prompt |
| Seguridad y Auditoría | Admin, TI | Log de auditoría filtrable, accesos denegados, metadatos de secretos (rotación) |
| DevOps | TI | Últimos despliegues, versión por entorno, estado de tests |
| Modo Demo | Admin | Botones: "Inyectar dato corrupto", "Simular ataque de fraude", "Probar acceso indebido" (llama un endpoint con rol Marketing y muestra el 403 + registro en auditoría), "Probar prompt injection" |

Un usuario sin permiso que entra a una ruta ve una pantalla "Acceso restringido" y el intento se audita.

---

## 11. Diseño visual

- Identidad inspirada en Interbank: **verde** principal (#00A94F aprox.) y **azul profundo** (#003B7A aprox.), fondos claros, sin usar el logo oficial. Logo propio "CHASKI" tipográfico.
- Tipografía: Inter o Plus Jakarta Sans.
- Consola: estilo dashboard profesional, densa pero limpia, modo claro/oscuro.
- App cliente: móvil primero, botones grandes, montos en `S/ 1,234.56`.
- Estados vacíos, skeletons de carga y toasts para cada acción. Accesible (contraste AA, labels, foco visible).

---

## 12. Ejecución local

- `docker compose up` levanta: postgres, cuentas-api, core-api, ia-api, cliente, consola.
- Variables por defecto: `AUTH_MODE=dev`, `AI_MODE=mock`, `DEMO_MODE=true`, `ANALYTICS_DB_URL` = mismo Postgres esquema `gold`.
- `make seed` corre migraciones + simulador.
- `.env.example` documentado con todas las variables (incluidas las de Azure, vacías).

---

## 13. Simulador (`simulator/`)

- Faker `es_ES` adaptado a Perú: nombres, DNI de 8 dígitos, regiones (Lima, Arequipa, La Libertad, Piura, Cusco, Junín, Lambayeque, Loreto).
- 1,000 clientes, ~1,300 cuentas, ~900 tarjetas, ~400 préstamos con distribución de mora realista por región, 6 meses de transacciones (~60,000), 150 quejas variadas (incluye 3 con prompt injection).
- Llena también `gold` (dimensiones, hechos y vistas).
- Semilla fija para reproducibilidad. Modo `--live` que genera transacciones continuas cada pocos segundos (para la demo).

---

## 14. Calidad mínima

- Cobertura de tests ≥ 70% en `cuentas-api` (es el servicio con CI/CD completo); tests clave en los demás.
- Tests obligatorios: autorización por rol, masking de PII, cliente no puede ver datos de otro cliente, idempotencia de transferencias, validador NL2SQL (rechaza `DELETE`, tablas fuera de allowlist, múltiples sentencias), validador de cifras del resumen.
- Dockerfiles multi-stage, usuario no root, `HEALTHCHECK`.
- `docs/API.md` con endpoints y `docs/DEMO.md` con el guion de demo paso a paso.

---

## 15. Fases de entrega

| Fase | Entregable | Criterio de aceptación |
|---|---|---|
| F1 | Monorepo, docker compose, migraciones, `chaski_common`, simulador | `docker compose up` + `make seed` deja BD poblada |
| F2 | cuentas-api + core-api (sin IA) con auth dev, roles, masking, auditoría, reglas de fraude | Tests pasan; 403 auditados |
| F3 | Chaski App completa (IA en mock) | Flujo onboarding → saldo → transferencia → préstamo → reclamo funciona |
| F4 | Consola: layout, roles, Operaciones, Clientes/KYC, Préstamos, Fraude | Cada rol ve solo sus módulos |
| F5 | ia-api con mock y Azure: quejas, scoring, asistente, resumen, NL2SQL, KYC | Con `AI_MODE=azure` y variables configuradas funciona contra Azure |
| F6 | Consola: Insights, Pipelines, Salud de IA, Seguridad, DevOps, Modo Demo | Todos los botones de demo funcionan en local |
| F7 | Pulido: OpenTelemetry, Dockerfiles finales, docs, accesibilidad, README | README permite levantar todo en 5 comandos |

---

## 16. Reglas que no se rompen

- Cero secretos en el código o en el repo.
- Cero PAN o PII en logs.
- La IA nunca toma decisiones finales de crédito, fraude o reclamos: sugiere, el humano decide.
- Los números que muestra la IA siempre vienen de datos, nunca generados por el modelo.
- Todo debe funcionar en mock sin Azure.
