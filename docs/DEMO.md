# Guion de demo · Interbank CHASKI

Duración sugerida: **15 minutos**. Todo funciona en local, sin Azure (`AI_MODE=mock`, `AUTH_MODE=dev`). En Azure el guion es el mismo; solo cambia el inicio de sesión (Entra ID).

## Antes de empezar (5 min antes)

```bash
docker compose up -d --build          # si aún no está levantado
docker compose run --rm seed          # datos frescos: 1,000 clientes, ~60,000 transacciones
docker compose run --rm live          # (opcional, en otra terminal) tráfico continuo cada ~3 s
```

Abre dos ventanas del navegador, una al lado de la otra:

| Ventana | URL | Para qué |
|---|---|---|
| A · Chaski App | http://localhost:3000 (vista móvil: DevTools → modo dispositivo) | El cliente |
| B · Control Center | http://localhost:3001 | El banco |

Ten a mano la imagen `docs/samples/dni_demo.png` para el onboarding.

---

## Acto 1 · El cliente (Chaski App) · 5 min

1. **Bienvenida** (A). Explica la propuesta: banco 100 % digital, PWA instalable.
2. **Onboarding en 3 pasos.** Clic en *Abrir mi cuenta*:
   - Paso 1: completa los datos (DNI de 8 dígitos y una región).
   - Paso 2: sube `docs/samples/dni_demo.png` (en el celular, el botón abre la cámara).
   - Paso 3: el cliente valida lo que la IA leyó del DNI. Si algún dato no coincide aparece la alerta, y la solicitud queda **"En revisión"**.
   - Clic en *Ingresar a mi cuenta*: la app bloquea las operaciones hasta la aprobación KYC.
3. **Aprobación KYC** (B). Ingresa como **Atención al cliente** → *Clientes y KYC* → *Bandeja de onboarding*.
   - Muestra los datos extraídos, la confianza y las validaciones cruzadas ("DNI no coincide", etc.).
   - *Aprobar*: se abren automáticamente una cuenta de ahorros y una tarjeta de débito (solo token + últimos 4 dígitos, nunca el PAN).
4. **Inicio** (A, recargar): saldo S/ 0.00, tarjeta activa, accesos rápidos.
5. **Préstamo**: el simulador trae la TEA real del cliente. Solicita **S/ 5,000 a 24 meses**.
6. **Decisión de Riesgos** (B). Ingresa como **Riesgos** → *Préstamos* → *Solicitudes*:
   - Score sugerido por la IA (reglas + explicación en lenguaje simple) y relación cuota/ingreso.
   - Mensaje clave: **la IA sugiere, el humano decide**. *Aprobar y desembolsar*.
7. **Transferencia** (A): S/ 350.75 a un CCI de 20 dígitos → confirmación → comprobante con el saldo nuevo.
8. **Chaski Asistente** (botón flotante):
   - "¿Cuál es mi saldo?" → responde con datos reales (nunca inventa cifras).
   - "Quiero bloquear mi tarjeta" → **no ejecuta**: muestra una tarjeta con *Confirmar*.
   - "¿Quién ganó el mundial?" → responde que no puede ayudar con eso.
9. **Reclamo** (A): "Me cobraron una comisión de mantenimiento que no me informaron". Indica el plazo de 15 días hábiles.

## Acto 2 · El banco (Control Center) · 6 min

10. **Cada rol ve solo lo suyo.** Cambia entre Marketing, Fraude y TI y muestra cómo cambia el menú.
    - Como **Marketing**, escribe `/prestamos` en la URL → **"Acceso restringido"** (y queda auditado).
11. **Centro de Operaciones**: KPIs en vivo (se refrescan cada 15 s), transacciones por hora y salud de las 3 APIs.
12. **Centro de Quejas IA** (Atención): el reclamo del acto 1 ya está clasificado (categoría, urgencia, confianza).
    - Cola de revisión obligatoria: FRAUDE, confianza < 80 % o sospechosas.
    - Corrige una etiqueta: la corrección alimenta la métrica de precisión de la IA.
13. **Chaski Insights** (Dirección):
    - Rentabilidad por producto, segmento y región; morosidad por bucket SBS y por región.
    - *Pregúntale al banco*: "¿Cuál es la mora por región?" → gráfico, tabla y **la SQL ejecutada** (solo lectura, `LIMIT 500`).
    - *Resumen ejecutivo*: la IA redacta y un validador verifica cada cifra contra los KPIs ("Cifras validadas · publicado").

## Acto 3 · Modo Demo: seguridad y gobierno · 4 min

Ingresa como **Administrador** → *Modo Demo*.

14. **Simular ataque de fraude** → 8 transferencias en 60 s → regla **R1_VELOCIDAD**.
    - En otra pestaña como **Fraude** → *Chaski Guard*: la alerta llega sola (refresco cada 5 s) con la etiqueta "Nueva".
    - *Resolver → Confirmar fraude* (con bloqueo de tarjeta si la transacción usó una).
15. **Inyectar dato corrupto** → el pipeline corre y el registro va a **cuarentena** (monto negativo, moneda inválida, fecha futura, cuenta inexistente).
    - Como **TI** → *Data Pipelines*: checks fallidos y registro en cuarentena.
16. **Probar acceso indebido** → Marketing intenta revelar datos personales → **403** y la fila exacta en la auditoría.
    - Como **Admin** → *Seguridad y Auditoría* → filtro *Denegados (403)*.
    - En la pestaña *Secretos*: solo metadatos de Key Vault y estado de rotación (nunca valores).
17. **Probar prompt injection** → Prompt Shields detecta el ataque y **el texto no llega al modelo**; la queja queda como sospechosa y va a revisión humana.
    - Como **TI** → *Salud de IA*: inyecciones bloqueadas, precisión IA vs humano, latencia y versión de prompt por caso de uso.

## Cierre · 30 s

- Arquitectura: tres APIs FastAPI en Container Apps (escalan a cero), PostgreSQL + Azure SQL (gold), Azure OpenAI + Content Safety + Document Intelligence, Entra ID con App Roles, Key Vault con Managed Identity y Application Insights.
- Reglas que no se rompen: cero secretos en el código, cero PII en logs, la IA nunca decide (sugiere) y las cifras siempre vienen de los datos.

---

## Plan B (si algo falla en vivo)

| Problema | Qué hacer |
|---|---|
| Una API no responde | `docker compose ps`, luego `docker compose restart core-api` (o la API caída). El panel *Salud de las APIs* muestra cuál falla. |
| Datos "gastados" (sin cuentas con saldo para la ráfaga) | `docker compose run --rm seed` (30 s) |
| Sesión vencida o rol incorrecto | Botón de cerrar sesión (arriba a la derecha) y volver a elegir el rol |
| La alerta no aparece en Chaski Guard | Verifica el filtro *Abiertas* / *Toda fuente*; se refresca cada 5 s |
| Sin internet | No hace falta: todo corre en local con IA mock |
