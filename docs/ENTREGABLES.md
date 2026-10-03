# CHASKI · Demo y entregables (Fase 12)

## 1. Antes de la demo (15 minutos antes)

1. **PostgreSQL** se enciende solo a las 08:00 (Lima). Fuera de ese horario: GitHub → Actions → *PostgreSQL schedule* → *Run workflow* → `start` (2–5 min).
2. **Despertar las apps** (escalan a cero; ia-api tarda 40–60 s en frío):
   ```bash
   for a in cuentas-dev core ia cliente consola; do curl -s -o /dev/null -w "$a %{http_code}\n" https://ca-$a.redgrass-4e60e60c.westus.azurecontainerapps.io/health; done
   ```
3. Abre en **ventanas privadas distintas**: la consola como `admin@`, la consola como `riesgos@`, la App como `cliente1@` y una cuarta para `marketing@`.
4. Ten a mano `docs/samples/dni_demo_texto.png` (DNI ficticio) y Power BI Desktop con el informe abierto.

URLs: App https://ca-cliente.redgrass-4e60e60c.westus.azurecontainerapps.io · Consola https://ca-consola.redgrass-4e60e60c.westus.azurecontainerapps.io · Gateway https://apim-chaski-xrghkf.azure-api.net

## 2. Guion (10 minutos)

| Min | Qué se muestra | Dónde |
|---|---|---|
| 0–1 | Problema y propuesta: banco 100 % digital, en tiempo real, seguro y con IA supervisada por humanos | PPT |
| 1–3 | Arquitectura: Container Apps detrás de API Management, PostgreSQL privado, Azure SQL DW, Key Vault, Entra ID, IA. Demo vs. objetivo (Front Door + WAF, Private Endpoints, Fabric) | PPT + portal (`rg-chaski`) |
| 3–5 | **End-to-end:** onboarding con DNI (Document Intelligence extrae los datos) → aprobación KYC en la consola (`atencion@`/`admin@`) → transferencia en la App → Modo Demo → *Simular ataque de fraude* → alerta R1 en Chaski Guard → bloquear tarjeta | App + consola |
| 5–7 | **Datos:** *Inyectar dato corrupto* → *Ejecutar pipeline* (job en Azure) → corrida CON_ALERTAS, checks y cuarentena → correo de alerta → Power BI (Dirección, Riesgos con RLS "Riesgos Norte") | Consola + Power BI |
| 7–9 | **IA:** queja con prompt injection marcada **Sospechosa** → asistente: "¿cuánto saldo tengo?" y "bloquea mi tarjeta" (pide confirmación) → *Pregúntale al banco* (muestra la SQL) → resumen ejecutivo con validador de cifras → Salud de IA → evaluación (`caj-ai-evals`) | App + consola |
| 9–10 | **Seguridad y DevOps:** `marketing@` intenta *Clientes* → Acceso restringido + 403 en Auditoría → incidente en Sentinel · CI/CD: PR → DEV → TEST → PROD por digest, rollback automático · Cost Management | Consola + portal + GitHub |

**Plan B si algo falla:** grabar antes un video de la demo completa. Local con `docker compose` (modo mock) como respaldo sin internet.

## 3. Blue-green en vivo (PROD de cuentas-api)

`ca-cuentas-prod` está en modo de **revisiones múltiples**:

```bash
az containerapp revision list -g rg-chaski -n ca-cuentas-prod --query "[].{rev:name, active:properties.active, traffic:properties.trafficWeight}" -o table
az containerapp ingress traffic set -g rg-chaski -n ca-cuentas-prod --revision-weight <rev-nueva>=10 <rev-anterior>=90   # canary 10 %
az containerapp ingress traffic set -g rg-chaski -n ca-cuentas-prod --revision-weight <rev-nueva>=100                   # promover
az containerapp ingress traffic set -g rg-chaski -n ca-cuentas-prod --revision-weight <rev-anterior>=100                # rollback instantáneo
```

## 4. Costo real

| Recurso | Costo mensual estimado |
|---|---|
| PostgreSQL B1ms (08:00–23:00 con el workflow programado) | ~USD 6–7 |
| ACR Basic | USD 5 |
| Azure OpenAI gpt-5-mini (pago por uso) | < USD 1 |
| Container Apps (escala a cero, dentro de la cuota gratuita), APIM Consumption (1 M llamadas gratis), Storage, Key Vault, DNS privado | ~USD 1 |
| Azure SQL (oferta gratuita con pausa), Content Safety F0, Document Intelligence F0, Defender CSPM básico | USD 0 |
| Log Analytics (tope 0.15 GB/día) + 4 alertas | ~USD 1–2 |
| Sentinel (prueba de 31 días, retirado automáticamente el 31/10) | USD 0 |
| **Total** | **≈ USD 14–17 al mes**, de los USD 100 de crédito (presupuesto USD 80 con alertas) |

## 5. Checklist del PDF

- [x] Arquitectura objetivo y de demo por capa: `infra/README.md`, `docs/DECISIONS.md`, Bicep en `infra/`
- [x] Mapa de datos y pipelines con checks de calidad y seguridad: `core_api/etl/` (bronze/silver/DW, 13 checks, cuarentena, minimización de datos)
- [x] Caso end-to-end narrado: este documento y `docs/DEMO.md`
- [x] Caso GenAI: prompts versionados (`genai/prompts/`), revisión humana (FRAUDE, confianza < 0.8 o sospechosa), Prompt Shields, validador de cifras, NL2SQL con allowlist, evaluaciones (`genai/evals/`)
- [x] Seguridad: Entra ID + MFA + App Roles, API Management con `validate-jwt`, Key Vault sin secretos humanos, identidades administradas y OIDC, red privada para PostgreSQL, masking de PII, auditoría, Sentinel y Defender CSPM, gitleaks / pip-audit / Trivy
- [ ] Reportes Power BI (los arma el equipo en Desktop con `powerbi/README.md`)
- [x] Cloud vs. on-premise vs. híbrido (sección 6)
- [ ] Tabla de cobertura del curso C-H-A-S-K-I por semana (completar con el sílabo)

## 6. Preguntas probables del jurado

1. **¿Por qué cloud y no híbrido?** Elasticidad, pago por uso (este banco cuesta < USD 20 al mes en demo), servicios gestionados de IA y seguridad, y tiempo de salida al mercado. Un banco real mantendría el core en un modelo **híbrido** por regulación (SBS, residencia de datos). Nuestra arquitectura lo permite porque todo pasa por APIs y la identidad es central.
2. **¿Si se cae la región?** Hoy es una sola región (costo). El objetivo es una región par con PostgreSQL con réplica geográfica, ACR geo-replicado, Front Door con failover y el Bicep reproducible en minutos en otra región.
3. **¿Cómo evitan que la IA invente cifras?** El asistente solo usa números que devuelven las herramientas, el resumen ejecutivo pasa por un **validador de cifras** contra los KPIs y NL2SQL muestra la SQL ejecutada. Las decisiones de crédito, fraude y reclamos siempre son humanas.
4. **¿PCI-DSS con tarjetas?** Nunca guardamos PAN: solo token y últimos 4 dígitos. Los logs se redactan, hay un check de calidad que busca PAN en textos y el objetivo es una subred CDE aislada con HSM.
5. **¿Datos corruptos en el DW?** Los checks bloqueantes **impiden cargar el DW**. Los registros malos van a cuarentena (base de datos y lake), la corrida queda CON_ALERTAS y salta una alerta por correo. El MERGE es idempotente.
6. **¿Por qué Container Apps y no AKS o Functions?** Escala a cero, revisiones con tráfico dividido (blue-green), jobs, identidades administradas y sin administrar un clúster. AKS sería sobredimensionado para 5 servicios; Functions complica las APIs largas y el streaming.
7. **¿Cómo escala a millones de clientes y cuánto cuesta?** Container Apps escala horizontalmente por demanda; PostgreSQL pasa a General Purpose con réplicas de lectura; el DW a Fabric o Synapse; y la detección de fraude a Fabric Real-Time. El costo crece por uso, con presupuestos y alertas.
8. **¿Ley 29733 con un LLM?** La PII se **redacta antes** de enviar el texto al modelo. Azure OpenAI no entrena con nuestros datos, el lake aplica **minimización de datos** (sin DNI, nombres ni contactos), las interacciones se auditan y la revelación de PII requiere rol y motivo, también auditada.
