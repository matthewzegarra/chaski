# infra/

Infraestructura como código (Bicep) para Azure: Container Apps (scale-to-zero), PostgreSQL Flexible Server, Azure SQL, Key Vault, Managed Identities, Application Insights, Storage, Azure OpenAI, Content Safety y Document Intelligence.

**Fuera del alcance de este prompt**: se construye con otro prompt. Las apps ya leen toda su configuración de variables de entorno (ver `.env.example`), así que la infraestructura solo tiene que inyectarlas como referencias a Key Vault.
