# PROMPT PARA CLAUDE CODE · CI/CD de `cuentas-api` con GitHub Actions

> Pásalo como primer mensaje a Claude Code en la raíz del repo `chaski` (rama `main` ya contiene F1–F7).
> Es la continuación del prompt principal (`CHASKI_CLAUDE_CODE_PROMPT.md`): respeta su `CLAUDE.md` y `docs/DECISIONS.md`.

---

## 0. Rol y forma de trabajo

Eres un **Senior DevOps / Platform Engineer** con experiencia en GitHub Actions y Azure Container Apps. Vas a construir el **CI/CD completo de `cuentas-api`**, el servicio crítico de Interbank CHASKI.

Reglas de trabajo:
1. Antes de escribir el workflow, muestra un plan corto (archivos, jobs, triggers, decisiones) y **espera mi confirmación**.
2. Trabaja por fases (sección 9). Al cerrar cada fase: valida (actionlint y ejecución real) y **detente para que confirme**.
3. Código, nombres de jobs y commits en inglés; documentación en español.
4. **Cero secretos en el repo.** Azure se autentica con **OIDC (federated credentials)**, nunca con contraseñas ni `AZURE_CREDENTIALS`.
5. Si algo es ambiguo, elige la opción más simple que cumpla el criterio de aceptación y anótala en `docs/DECISIONS.md` (continúa la numeración: la última es D52).
6. No toques el código de la aplicación salvo que un test o el pipeline revelen un bug real; si pasa, explícalo y agrégale un test.

---

## 1. Contexto del repo (verificado, no lo cambies)

- Monorepo. Backend en un **workspace de uv** (`pyproject.toml` raíz, `uv.lock`). Python **3.12** en contenedores; uv **0.11**.
- `cuentas-api` vive en `services/cuentas-api/` (paquete `cuentas_api`). Depende de `libs/chaski_common/` (auth, ledger, fraude, auditoría, logging): **un cambio en la librería también debe disparar el pipeline de cuentas-api**.
- Migraciones Alembic en `db/migrations` (un único historial para `core`, `ops` y `gold`).
- Dockerfile: `services/cuentas-api/Dockerfile`, **contexto de build = raíz del repo**. Imagen multi-stage, usuario 10001, `HEALTHCHECK` a `/health`, puerto 8000.
- Endpoints de salud: `GET /health` (liveness) y `GET /ready` (verifica la BD).
- Comandos de calidad que el CI **debe reutilizar tal cual**:
  ```bash
  uv sync --all-packages --frozen
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy libs/chaski_common/src services/cuentas-api/src
  uv run pytest services/cuentas-api libs/chaski_common --cov=cuentas_api --cov=chaski_common --cov-report=xml --cov-fail-under=70
  ```
  Hoy la cobertura de cuentas-api es ~95 %. El umbral mínimo de la consigna es **70 %**.
- **Tests con base de datos real.** `conftest.py` (raíz) se conecta a `localhost:5432` y lee `POSTGRES_PASSWORD`, `CHASKI_APP_DB_PASSWORD` y `CHASKI_READONLY_DB_PASSWORD` del entorno. Necesita:
  - los roles `chaski_app` y `chaski_readonly`;
  - la BD `chaski_test`;
  - todo lo crea `db/init/01-roles.sh` (script de `docker-entrypoint-initdb.d`).

  ⚠️ Un `services: postgres` de GitHub Actions arranca **antes** del checkout, así que no puede montar `db/init`. Resuélvelo con una de estas dos opciones (anota la elegida en DECISIONS):
  - levantar Postgres con `docker run` después del checkout, montando `db/init`; o
  - usar el service container y ejecutar con `psql` el mismo SQL de `db/init/01-roles.sh`.

  Los tests corren las migraciones solos (fixture `migrated_db`). Las contraseñas de CI son valores efímeros generados en el job (p. ej. `openssl rand -hex 16`), nunca secretos reales.
- El módulo **DevOps** de la consola (`services/core-api/src/core_api/routers/devops.py`) lee las ejecuciones de GitHub Actions y deduce el entorno así:
  - rama `main` o nombre con "prod" → **PROD**;
  - rama `release/*` o nombre con "test" → **TEST**;
  - el resto → **DEV**.

  El workflow debe llamarse exactamente **`cuentas-api CI/CD`** y usar estas ramas para que la consola muestre la versión por entorno sin cambios.

---

## 2. Estrategia de ramas y entornos

| Rama | Qué corre | Entorno GitHub | Aprobación |
|---|---|---|---|
| Pull request a `develop`, `release/*` o `main` | Solo CI (lint, tipos, tests, build sin push, escaneo) | — | — |
| push a `develop` | CI + imagen + deploy | `dev` | automática |
| push a `release/*` | CI + imagen + deploy | `test` | automática |
| push a `main` | CI + **promoción de la misma imagen** ya probada en TEST | `prod` | **revisor obligatorio** |

- Crea la rama `develop` desde `main` si no existe.
- **Build once, deploy many:** la imagen se construye una sola vez con tag `sha-<commit>` y se promueve entre entornos; nunca se reconstruye para PROD. Tags adicionales: `dev`, `test`, `prod`.
- `workflow_dispatch` con input `environment` (dev/test/prod) para redeploy manual de un `sha` existente.

---

## 3. Triggers y eficiencia (presupuesto USD 100 + minutos gratis de Actions en repo privado)

- `paths` del workflow: `services/cuentas-api/**`, `libs/chaski_common/**`, `db/**`, `pyproject.toml`, `uv.lock`, `conftest.py`, `.github/workflows/cuentas-api.yml`.
- `concurrency`: un deploy por entorno a la vez; cancela CIs viejos del mismo PR (nunca un deploy en curso).
- Caché de uv (`astral-sh/setup-uv` con `enable-cache`) y caché de capas Docker (`type=gha`).
- `timeout-minutes` en todos los jobs.
- Jobs de CI en paralelo cuando no dependan entre sí (lint/tipos ∥ tests).

---

## 4. Jobs requeridos

1. **lint**: ruff check + ruff format --check + mypy.
2. **test**:
   - Postgres 16 (ver sección 1) + pytest con cobertura ≥ 70 %.
   - Publica `coverage.xml` como artefacto y un resumen en `$GITHUB_STEP_SUMMARY` (tests pasados/fallidos y % de cobertura).
3. **image**:
   - Build con `docker/build-push-action` (Buildx, contexto `.`, `file: services/cuentas-api/Dockerfile`) y labels OCI (`org.opencontainers.image.revision`, `source`, `version`).
   - En PR: build sin push.
   - En push: login a **Azure Container Registry con OIDC** (`azure/login` + `az acr login`) y push `sha-<commit>`.
4. **scan**: Trivy sobre la imagen. Falla con vulnerabilidades **CRITICAL** que tengan fix disponible y sube el SARIF a *Code scanning* si el plan del repo lo permite; si no, solo como artefacto.
5. **deploy-dev / deploy-test / deploy-prod** (uno por GitHub Environment):
   - `azure/login` con OIDC (`client-id`, `tenant-id`, `subscription-id` como **variables** del environment, no secretos).
   - `az containerapp update --name <app> --resource-group <rg> --image <acr>/chaski/cuentas-api:sha-<commit> --revision-suffix <sha-corto>`.
   - **Smoke test** contra el FQDN de la app: `GET /health` y `GET /ready` con reintentos (la app escala a cero y tarda en arrancar).
   - **Rollback automático** si el smoke falla: vuelve el tráfico a la revisión anterior y deja el job en rojo.
   - Resumen en `$GITHUB_STEP_SUMMARY`: entorno, imagen, revisión, URL y resultado del smoke test.
   - PROD exige revisor (GitHub Environment `prod` con *required reviewers*) y solo puede desplegar un `sha` que ya pasó por TEST.

**Migraciones:** no las corre este workflow (son compartidas con core-api). Si el deploy detecta que `/ready` falla por esquema desactualizado, el mensaje debe indicarlo claramente. Anota en DECISIONS cómo se ejecutarán (Container Apps Job con la imagen `tools`, en el prompt de infraestructura).

**Si Azure aún no existe** (el prompt de Bicep va después): los jobs de deploy deben **saltarse limpiamente** cuando falten las variables del environment (`if: vars.ACR_NAME != ''`, etc.), dejando un aviso en el resumen, para que el CI quede verde sin infraestructura.

---

## 5. Seguridad del pipeline (no negociable)

- `permissions` mínimos a nivel de workflow (`contents: read`). Agrega `id-token: write` y `packages`/`security-events` solo en los jobs que los necesiten.
- Actions de terceros **fijadas por SHA** con comentario de versión (`uses: owner/action@<sha> # vX.Y.Z`).
- Nada de `pull_request_target`. Los PR desde forks no reciben credenciales.
- No imprimas valores sensibles; las contraseñas efímeras de Postgres se enmascaran con `::add-mask::`.
- Dependabot (`.github/dependabot.yml`) para `github-actions`, `uv`/`pip` y `docker`, semanal y agrupado.
- Protección de ramas (documentada en `docs/CICD.md`, la aplico yo): `main` y `release/*` exigen PR, el check `cuentas-api CI/CD` en verde y 1 aprobación.

---

## 6. Configuración en GitHub y Azure (documéntala; no la ejecutes sin mi confirmación)

`docs/CICD.md` debe explicar paso a paso, con comandos `az` y `gh`:

1. App registration / Managed Identity para GitHub con **federated credentials** por entorno: `repo:Matthewzegarra0312/chaski:environment:dev|test|prod` y `:pull_request` si aplica.
2. Rol mínimo: `AcrPush` sobre el ACR y `Contributor` **solo sobre la Container App** de cada entorno (no sobre la suscripción).
3. GitHub Environments `dev`, `test` y `prod` con estas **variables**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `RESOURCE_GROUP`, `CONTAINERAPP_NAME`. `prod` lleva *required reviewers*.
4. Costos: ACR Basic (~USD 5/mes) y Container Apps con escala a cero.

---

## 7. Entregables

- `.github/workflows/cuentas-api.yml` (name: `cuentas-api CI/CD`).
- Opcional, si reduce duplicación: un workflow reutilizable `.github/workflows/_python-service.yml` que core-api e ia-api puedan usar más adelante.
- `.github/dependabot.yml`.
- `docs/CICD.md`: diagrama del flujo (mermaid), ramas, entornos, configuración OIDC, cómo hacer rollback manual y cómo leer el resultado en el módulo DevOps.
- Actualizar `.github/workflows/README.md`, `README.md` (badge del workflow) y `docs/DECISIONS.md`.
- Opcional: un `make ci` o script que corra localmente los mismos pasos de CI.

---

## 8. Criterios de aceptación

1. `actionlint` sin errores sobre todos los workflows.
2. Un PR que toque `services/cuentas-api/**` ejecuta lint, tests (cobertura ≥ 70 %), build y escaneo, todo **en verde**.
3. Un PR que rompa un test o baje la cobertura de 70 % deja el check **en rojo**. Demuéstralo con un PR de prueba y luego ciérralo.
4. Un PR que solo toque `apps/**` **no** dispara el pipeline.
5. Push a `develop` sin infraestructura en Azure: CI en verde y deploy **saltado con aviso** (no fallido).
6. Con las variables de Azure configuradas, push a `develop` despliega en DEV, pasa el smoke test y la consola (módulo DevOps, `GITHUB_REPO`/`GITHUB_TOKEN` de solo lectura) muestra la versión en DEV.
7. Un smoke test fallido revierte el tráfico a la revisión anterior.
8. `docs/CICD.md` permite a otra persona configurar OIDC y los entornos sin preguntarme nada.

---

## 9. Fases

| Fase | Entregable | Criterio |
|---|---|---|
| C1 | Plan + `cuentas-api.yml` solo con CI (lint, tipos, tests, build sin push, scan) + dependabot | Criterios 1–4 |
| C2 | Jobs de imagen y deploy por entorno con OIDC, smoke test, rollback y skip sin Azure | Criterio 5 |
| C3 | `docs/CICD.md`, README, DECISIONS; prueba real en Azure cuando yo configure los recursos | Criterios 6–8 |

---

## 10. Reglas que no se rompen

- Cero secretos en el repo y cero credenciales de larga duración: solo OIDC.
- Ninguna imagen llega a PROD sin haber pasado por TEST con el mismo `sha`.
- El umbral de cobertura de cuentas-api nunca baja de 70 % para que el pipeline pase.
- El pipeline nunca imprime PII ni secretos en los logs.
