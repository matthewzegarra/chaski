# infra/

Infraestructura como código (Bicep) de CHASKI para la suscripción **Azure for Students**. Todo vive en el grupo de recursos `rg-chaski`, en la región **`westus`**: es una de las permitidas por la policy de la universidad y la única con cuota de `gpt-5-mini` en esta suscripción.

## Estructura

| Archivo | Contenido |
|---|---|
| `main.bicep` | Alcance de suscripción: crea `rg-chaski` y orquesta los módulos en dos etapas |
| `main.bicepparam` | Parámetros sin secretos (región, tags, IDs de Entra ID) |
| `modules/network.bicep` | VNet `10.40.0.0/16`, subredes `snet-aca` (Container Apps) y `snet-pg` (PostgreSQL), NSG y DNS privado de PG |
| `modules/monitoring.bicep` | Log Analytics (30 días, tope diario de ingesta) y Application Insights |
| `modules/identities.bicep` | Una UAMI por workload y `id-chaski-github` con credenciales federadas (OIDC) por entorno |
| `modules/keyvault.bicep` | Key Vault con RBAC, purge protection y red denegada por defecto |
| `modules/storage.bicep` | ADLS Gen2 (bronze/silver/gold/quarantine/kyc), solo Entra ID, TLS 1.2 |
| `modules/acr.bicep` | ACR Basic sin usuario admin (AcrPull para workloads, AcrPush para GitHub) |
| `modules/ai.bicep` | Azure OpenAI (`gpt-5-mini`), Content Safety F0 y Document Intelligence F0, sin claves |
| `modules/postgres.bicep` | PostgreSQL Flexible B1ms, solo acceso por VNet |
| `modules/sql.bicep` | Azure SQL con oferta gratuita (auto-pausa al llegar al límite) y solo autenticación Entra |
| `modules/containerapps.bicep` | Entorno Consumption con VNet, 7 apps (escala a cero), jobs `caj-migrate` y `caj-pipeline` |
| `modules/apim.bicep` | API Management Consumption |
| `scripts/deploy.ps1` | What-if, despliegue por etapas y siembra de secretos en Key Vault |

## Despliegue

```powershell
az login --use-device-code
az account set -s "Azure for Students"
./infra/scripts/deploy.ps1 -Stage whatif1   # vista previa, no cambia nada
./infra/scripts/deploy.ps1 -Stage 1         # red, monitoreo, identidades, KV, storage, ACR, IA
./infra/scripts/deploy.ps1 -Stage seed      # genera los secretos que falten en Key Vault
./infra/scripts/deploy.ps1 -Stage 2         # PostgreSQL, SQL, Container Apps, APIM
./infra/scripts/deploy.ps1 -Stage 2 -RealImages -ImageTag dev   # cuando el CI/CD ya publicó imágenes
```

El script se niega a correr si la suscripción activa no es "Azure for Students".

## Decisiones de costo y seguridad

- **Service endpoints en vez de Private Endpoints** para Key Vault, Storage, SQL y AI: son gratis; cada Private Endpoint cuesta ~USD 7 al mes. El acceso se limita a la subred de Container Apps más la IP de quien despliega. Los Private Endpoints quedan como diseño de producción.
- **Sin secretos de larga vida:** los workloads usan identidades administradas (Key Vault, ACR, Storage, Azure OpenAI). GitHub Actions entra por OIDC. Las contraseñas de PostgreSQL las genera `deploy.ps1`, van directo a Key Vault con fecha de vencimiento y las apps las leen como referencias de Key Vault.
- **Escala a cero:** todas las Container Apps usan `minReplicas: 0`. Azure SQL usa la oferta gratuita con auto-pausa. Log Analytics tiene un tope de ingesta diario.
- **Ahorro diario:** `az postgres flexible-server stop -g rg-chaski -n psql-chaski-<sufijo>`.
- **Identidad:** las APIs validan tokens del tenant de identidad de CHASKI (ver `infra/entra/`), que es distinto del tenant de la suscripción.
