# Chaski Guard · fraude en tiempo real (Fase 10)

## Estado

| Plan | Qué es | Estado |
|---|---|---|
| **B (activo)** | Motor de reglas R1–R4 dentro de `cuentas-api`: cada transacción se evalúa al registrarse y genera `ops.fraud_alerts` (`source=RULES`), que Chaski Guard muestra cada 5 s. El demo "Simular ataque de fraude" dispara R1. | ✅ En Azure |
| **A (objetivo)** | Microsoft Fabric Real-Time Intelligence: Eventstream → Eventhouse (KQL) → Activator → webhook firmado con HMAC. | ⏳ Requiere la prueba de Fabric de la cuenta UTP |

El código ya está listo para el plan A:
- `cuentas-api` publica cada transacción a Eventstream cuando existe `EVENTSTREAM_CONNECTION_STRING` (endpoint compatible con Event Hubs).
- `core-api` expone `POST /api/v1/fraud/webhook`, validado con **HMAC-SHA256** (`X-Chaski-Signature`, secreto `fraud-webhook-secret` de Key Vault, comparación en tiempo constante). Crea alertas con `source=FABRIC`.

## Plan A paso a paso (cuando la prueba de Fabric esté activa)

1. https://app.fabric.microsoft.com → **Iniciar prueba gratuita** (60 días) → workspace `chaski-guard`.
2. **Eventstream** `es-transacciones` → origen *Custom endpoint* → copia la *connection string* (Event Hubs).
3. Guárdala en Key Vault como **`eventstream-connection-string`** (portal → `kv-chaski-xrghkf` → Secrets). Agrégala a `ca-cuentas-*` como referencia de Key Vault (`EVENTSTREAM_CONNECTION_STRING`) en `infra/modules/containerapps.bicep` y aplica con el workflow de infraestructura.
4. Destino del Eventstream: **Eventhouse** `kqldb-chaski`, tabla `Transacciones`.
5. Reglas KQL en el Eventhouse:

```kql
// R1: ráfaga de transferencias (más de 5 en 2 minutos por cliente)
Transacciones
| where type == "TRANSFERENCIA_OUT" and created_at > ago(2m)
| summarize n = count(), total = sum(amount) by customer_id
| where n > 5

// R2: monto atípico frente al promedio de 30 días del cliente
let base = Transacciones | where created_at > ago(30d)
    | summarize avg_amount = avg(amount) by customer_id;
Transacciones | where created_at > ago(5m)
| join kind=inner base on customer_id
| where amount > 3 * avg_amount
```

6. **Activator** sobre esas consultas → acción → **HTTP POST** a `https://apim-chaski-xrghkf.azure-api.net/core/api/v1/fraud/webhook`. El gateway deja pasar esa ruta sin JWT porque la autenticación es la firma HMAC.
   - Power Automate no calcula HMAC por sí solo: usa una **Logic App** (Consumption, centavos al mes) con la acción *Compose* `hmac-sha256` (expresión `base64ToString`/`hmac`) o un paso de código que firme el cuerpo con el secreto `fraud-webhook-secret`.
7. **Dashboard en tiempo real** de Fabric: transacciones por minuto y alertas por regla, para la PPT.

## Para la exposición

"En la demo, el motor de reglas corre dentro del servicio crítico y detecta en milisegundos. La arquitectura objetivo mueve la detección a Fabric (streaming + KQL + Activator), que escala a millones de eventos y permite reglas por ventana de tiempo sin tocar el código del banco. El webhook ya existe y está firmado con HMAC, así que Fabric solo tiene que llamarlo."
