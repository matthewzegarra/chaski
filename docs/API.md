# API de CHASKI

> Documento **generado** con `scripts/gen_api_docs.py` a partir de las rutas reales de cada servicio
> (la columna *Roles* se lee de las dependencias de autorización del código). No editar a mano.

## Convenciones

- Prefijo `/api/v1`. OpenAPI interactivo en `http://localhost:<puerto>/docs` de cada servicio.
- `GET /health` (liveness) y `GET /ready` (verifica la base de datos) en los tres servicios, sin autenticación.
- Autenticación: `Authorization: Bearer <JWT>` de Entra ID (`AUTH_MODE=entra`) o el emitido por `POST /api/v1/dev/token` en local (`AUTH_MODE=dev`).
- Los roles salen del claim `roles` (App Roles). Un cliente solo accede a sus datos: el `customer_id` sale del token, nunca del body.
- Todo 403 y todo acceso a PII queda en `ops.audit_log`. Los errores tienen la forma `{"detail": "..."}`; los 500 incluyen `correlation_id`.
- `X-Correlation-ID`: se acepta y se devuelve en cada respuesta, y aparece en los logs JSON.
- `POST /transfers` exige `Idempotency-Key` (misma key y mismo body → misma respuesta; key con otro body → 409).
- Montos: números en soles o dólares con 2 decimales. Fechas: ISO 8601 en UTC.

## cuentas-api (`:8001`)

Saldo, movimientos, transferencias y pagos con tarjeta. Servicio crítico con CI/CD completo.

### Cuentas

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/accounts/me` | Cuentas del cliente autenticado | Cliente (sus propios datos) |
| `GET` | `/accounts/{account_id}/balance` | Saldo disponible de una cuenta propia | Cliente (sus propios datos) |
| `GET` | `/accounts/{account_id}/movements` | Movimientos paginados con filtros `from`, `to`, `type`, `page`, `page_size` | Cliente (sus propios datos) |

### Pagos

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `POST` | `/card-payments` | Pago con tarjeta de débito (POS/online); `Idempotency-Key` opcional. Evalúa reglas de fraude y publica a Eventstream | Cliente (sus propios datos) |
| `POST` | `/transfers` | Transferencia propia o a CCI; valida saldo; `Idempotency-Key` obligatorio. Evalúa reglas R1–R4 y publica a Eventstream | Cliente (sus propios datos) |

## core-api (`:8002`)

Clientes, onboarding/KYC, tarjetas, préstamos, quejas, fraude, operación, pipelines, analítica, seguridad, DevOps y demo.

### Analítica

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/analytics/delinquency` | Morosidad por bucket SBS, por región y tendencia (vistas gold) | Admin, Direccion, Marketing, Riesgos |
| `GET` | `/analytics/profitability` | Rentabilidad por producto, segmento o región y evolución mensual (vistas gold) | Admin, Direccion, Marketing, Riesgos |

### Clientes

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/customers` | Listado paginado de clientes con PII enmascarada; filtros `q`, `kyc_status`, `segment`, `region` | Admin, Atencion, Fraude, Operaciones, Riesgos |
| `GET` | `/customers/me` | Perfil del cliente autenticado | Cliente (sus propios datos) |
| `GET` | `/customers/{customer_id}` | Detalle de cliente enmascarado con cuentas, tarjetas y préstamos (se audita) | Admin, Atencion, Fraude, Operaciones, Riesgos |
| `POST` | `/customers/{customer_id}/reveal-pii` | Revela DNI, correo, celular y nacimiento; exige `reason` (mínimo 10 caracteres) y se audita como acceso a PII | Admin, Atencion |

### Demo

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `POST` | `/demo/forbidden-access` | Demo: registra el 403 de un usuario Marketing (alternativa para Entra ID). Requiere `DEMO_MODE=true` | Admin |
| `POST` | `/demo/fraud-burst` | Demo: 8 transferencias en 60 s del mismo cliente para disparar R1. Requiere `DEMO_MODE=true` | Admin |
| `POST` | `/demo/inject-bad-record` | Demo: inserta un registro corrupto en la ingesta para enviarlo a cuarentena. Requiere `DEMO_MODE=true` | Admin |

### Dev

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `POST` | `/dev/token` | Emite un JWT de prueba (HS256) para un rol o cliente; 404 si `AUTH_MODE=entra` | Público, solo con `AUTH_MODE=dev` |
| `GET` | `/dev/users` | Personas de prueba para el selector de usuarios; 404 si `AUTH_MODE=entra` | Público, solo con `AUTH_MODE=dev` |

### Devops

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/devops/deployments` | Últimas ejecuciones de GitHub Actions y versión por entorno (mock sin `GITHUB_TOKEN`) | Admin, TI |

### Fraude

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/fraud/alerts` | Alertas de fraude (RULES y FABRIC) con datos de la transacción y la tarjeta; filtros `status`, `source` | Admin, Fraude |
| `POST` | `/fraud/alerts/{alert_id}/resolve` | Confirma o descarta una alerta; opcionalmente bloquea la tarjeta | Admin, Fraude |
| `POST` | `/fraud/webhook` | Recibe alertas de Fabric Activator (`source=FABRIC`), autenticado con HMAC-SHA256 del cuerpo | Firma HMAC `X-Chaski-Signature` (Fabric Activator) |

### Onboarding

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `POST` | `/onboarding` | Alta digital (multipart: datos + foto del DNI); extrae datos con ia-api, consulta DNI y crea el cliente `PENDIENTE` | Público |
| `GET` | `/onboarding/lookup-dni/{dni}` | Consulta de identidad por DNI (ApisPeru o mock); rellena nombres y apellidos. Público, con rate limit | Público |
| `GET` | `/onboarding/pending` | Bandeja KYC: solicitudes pendientes con datos extraídos, confianza y validaciones cruzadas | Admin, Atencion |
| `POST` | `/onboarding/{customer_id}/decision` | Aprueba (abre cuenta y tarjeta) o rechaza un onboarding | Admin, Atencion |

### Operaciones

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/ops/kpis` | KPIs del día (hora de Lima): transacciones, clientes nuevos, cartera, mora, alertas y quejas | Admin, Atencion, Direccion, Fraude, Marketing, Operaciones, Riesgos, TI |
| `GET` | `/ops/pipelines` | Últimas corridas del pipeline de datos | Admin, TI |
| `POST` | `/ops/pipelines/run` | Ejecuta el pipeline: Container Apps Job vía ARM en Azure; simulación local en otro caso | Admin, TI |
| `GET` | `/ops/pipelines/{run_id}/checks` | Checks de calidad de una corrida | Admin, TI |
| `GET` | `/ops/quarantine` | Registros en cuarentena | Admin, TI |
| `GET` | `/ops/transactions-by-hour` | Transacciones por hora del día (hora de Lima) | Admin, Atencion, Direccion, Fraude, Marketing, Operaciones, Riesgos, TI |

### Préstamos

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/loans` | Solicitudes y cartera con score IA, días de atraso y bucket; filtros `status`, `region`, `min_days_past_due` | Admin, Direccion, Riesgos |
| `POST` | `/loans` | Solicitud de préstamo del cliente; calcula la TEA y pide el score sugerido a ia-api | Cliente (sus propios datos) |
| `GET` | `/loans/me` | Préstamos del cliente con su estado | Cliente (sus propios datos) |
| `GET` | `/loans/quote` | Simulación: TEA del cliente, cuota mensual y total a pagar | Cliente (sus propios datos) |
| `GET` | `/loans/{loan_id}` | Detalle con cronograma de cuotas (el cliente dueño o Riesgos, Dirección o Admin) | Cualquier usuario autenticado |
| `POST` | `/loans/{loan_id}/decision` | Decisión final de Riesgos; al aprobar se desembolsa en la cuenta en soles | Riesgos |
| `POST` | `/loans/{loan_id}/rescore` | Vuelve a pedir el score sugerido a ia-api | Riesgos |

### Quejas

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/complaints` | Bandeja de quejas con clasificación IA, revisión obligatoria y días hábiles restantes | Admin, Atencion |
| `POST` | `/complaints` | Registra un reclamo del cliente; la IA lo clasifica y vence en 15 días hábiles | Cliente (sus propios datos) |
| `GET` | `/complaints/me` | Reclamos del cliente con su estado | Cliente (sus propios datos) |
| `POST` | `/complaints/{complaint_id}/review` | Revisión humana: categoría final y estado (alimenta la precisión de la IA) | Admin, Atencion |

### Seguridad

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/security/audit` | Auditoría paginada; filtros `allowed`, `pii_accessed`, `actor`, `action`, `since` | Admin, TI |
| `POST` | `/security/denied-route` | Registra que un usuario abrió en la consola un módulo no permitido | Cualquier usuario autenticado |
| `GET` | `/security/secrets-metadata` | Metadatos de secretos de Key Vault (nunca valores) con estado de rotación | Admin, TI |
| `GET` | `/security/summary` | Denegados, revelados de PII y eventos de las últimas 24 h | Admin, TI |

### Tarjetas

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/cards/me` | Tarjetas del cliente (solo últimos 4 dígitos; nunca el PAN ni el token) | Cliente (sus propios datos) |
| `POST` | `/cards/{card_id}/block` | Bloquea una tarjeta (el cliente dueño o Fraude, Atención o Admin) | Cualquier usuario autenticado |
| `POST` | `/cards/{card_id}/unblock` | Desbloquea una tarjeta (el cliente dueño o Fraude, Atención o Admin) | Cualquier usuario autenticado |

## ia-api (`:8003`)

Casos de uso de IA: clasificador de quejas, scoring, asistente, resumen ejecutivo, NL2SQL, KYC y métricas.

### Ia

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| `GET` | `/ai/health-metrics` | Precisión IA vs humano, revisión manual, bloqueos de Prompt Shields, latencia y versión de prompt | Admin, TI |
| `POST` | `/analytics/ask` | NL2SQL: pregunta en lenguaje natural → SELECT validado (vistas gold, `LIMIT 500`) ejecutado en solo lectura; devuelve la SQL | Admin, Direccion, Marketing, Riesgos |
| `POST` | `/assistant/chat` | Chaski Asistente con herramientas sobre las cuentas del cliente; acciones sensibles como `pending_action` | Cliente (sus propios datos) |
| `POST` | `/complaints/classify` | Clasifica una queja (categoría, urgencia, confianza, sospechosa) con Prompt Shields | Admin, Atencion, Cliente |
| `POST` | `/kyc/extract` | Extrae datos del DNI (Document Intelligence o mock) | Admin, Atencion, Operaciones |
| `POST` | `/loans/score` | Score por reglas (300 a 900) con factores y explicación en lenguaje simple | Cliente, Riesgos |
| `POST` | `/reports/executive-summary` | Resumen ejecutivo sobre KPIs de gold con validador de cifras | Admin, Direccion |

