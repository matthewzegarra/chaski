# .github/workflows/

| Workflow | Qué hace |
|---|---|
| [`cuentas-api.yml`](cuentas-api.yml) · **cuentas-api CI/CD** | CI en cada PR (lint, tipos, tests con cobertura ≥ 70 %, build y Trivy) y CD por entorno: `develop` → DEV, `release/*` → TEST, promoción manual a PROD. |

La action compuesta [`../actions/deploy-containerapp`](../actions/deploy-containerapp/action.yml) despliega en Azure Container Apps, prueba `/health` y `/ready` y vuelve a la imagen anterior si el smoke test falla.

Guía completa (ramas, OIDC, environments, rollback, solución de problemas): [`docs/CICD.md`](../../docs/CICD.md).

> El workflow debe llamarse exactamente `cuentas-api CI/CD`: el módulo DevOps de la consola lo lee de la API de GitHub y deduce el entorno por la rama.
