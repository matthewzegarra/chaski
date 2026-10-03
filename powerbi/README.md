# Power BI · Chaski Insights (Fase 8)

Informe de 3 páginas (**Dirección**, **Riesgos** y **Marketing**) sobre el DW en Azure SQL que carga el pipeline (`caj-pipeline`, cada noche a las 22:00 Lima, o con el botón "Ejecutar pipeline" de la consola).

| Dato | Valor |
|---|---|
| Servidor | `sql-chaski-xrghkf.database.windows.net` |
| Base de datos | `sqldb-chaski-dw` |
| Esquema | `dw` |
| Autenticación | **Cuenta de Microsoft** (Entra ID) con `U21200917@utp.edu.pe`, admin de Entra del servidor. **No existen usuarios con contraseña** (solo Entra). |
| Red | El firewall acepta la IP del admin (variable `INFRA_ADMIN_IP` de GitHub). Si cambias de red, actualízala y corre el workflow `infra (Bicep)`. |

> Azure SQL usa la oferta gratuita con **pausa automática**: la primera conexión del día puede tardar hasta 1 minuto mientras despierta. Es normal.

## 1. Conectar (Power BI Desktop)

1. *Obtener datos* → **Azure SQL Database** → servidor y base de la tabla anterior → **Importar**.
2. Credenciales: **Cuenta de Microsoft** → *Iniciar sesión* con la cuenta UTP.
3. Selecciona: `dw.dim_date`, `dw.dim_region`, `dw.dim_product`, `dw.dim_customer`, `dw.dim_delinquency_bucket`, `dw.fact_profitability_monthly`, `dw.fact_portfolio_daily` y la vista `dw.v_rentabilidad_rollup`.

## 2. Modelo estrella (vista *Modelo*)

| Desde (hechos) | Hacia (dimensión) | Columnas | Cardinalidad |
|---|---|---|---|
| `fact_portfolio_daily[date]` | `dim_date[date]` | fecha | Varios a uno |
| `fact_profitability_monthly[month]` | `dim_date[date]` | primer día del mes | Varios a uno |
| `fact_portfolio_daily[region]` | `dim_region[name]` | región | Varios a uno |
| `fact_profitability_monthly[region]` | `dim_region[name]` | región | Varios a uno |
| `fact_profitability_monthly[product]` | `dim_product[code]` | producto | Varios a uno |
| `fact_portfolio_daily[bucket]` | `dim_delinquency_bucket[name]` | bucket SBS | Varios a uno |

- En `dim_customer`, filtra `is_current = 1` (Power Query → *Filtrar filas*). Es una dimensión **SCD2**: las filas antiguas guardan la historia de segmento y región.
- Marca `dim_date` como **tabla de fechas** (columna `date`).

## 3. Medidas DAX

Crea una tabla `_Medidas` (*Especificar datos* vacía) y agrega:

```DAX
Margen = SUM ( fact_profitability_monthly[margin] )

Ingresos = SUM ( fact_profitability_monthly[interest_income] ) + SUM ( fact_profitability_monthly[fees] )

Cartera Total = SUM ( fact_portfolio_daily[outstanding_balance] )

Cartera Vigente =
    CALCULATE ( [Cartera Total], fact_portfolio_daily[days_past_due] = 0 )

Ratio Mora =
    DIVIDE (
        CALCULATE ( [Cartera Total], fact_portfolio_daily[days_past_due] > 30 ),
        [Cartera Total]
    )

Cartera Último Día =
    CALCULATE ( [Cartera Total], LASTDATE ( dim_date[date] ) )

Clientes = CALCULATE ( COUNTROWS ( dim_customer ), dim_customer[is_current] = 1 )

Clientes Nuevos (mes) =
    CALCULATE (
        [Clientes],
        FILTER ( dim_customer, dim_customer[created_month] = MAX ( dim_date[date] ) - DAY ( MAX ( dim_date[date] ) ) + 1 )
    )

Penetración Préstamos = DIVIDE ( SUM ( dim_customer[active_loans] ) , [Clientes] )
```

Formato: `Margen`, `Ingresos` y las medidas de cartera como moneda **S/** con 0 decimales; `Ratio Mora` y `Penetración Préstamos` como porcentaje con 1 decimal.

## 4. Páginas

| Página | Visuales |
|---|---|
| **Dirección** | Tarjetas: Margen, Ingresos, Cartera Último Día, Ratio Mora · Barras: Margen por producto · Líneas: Margen por mes · Barras: Top 5 regiones por margen · Tabla: `v_rentabilidad_rollup` (subtotales y total con `ROLLUP`) · Segmentador: segmento |
| **Riesgos** | Columnas apiladas: Cartera por bucket SBS (Normal, CPP, Deficiente, Dudoso, Pérdida) · Barras: Ratio Mora por región · Líneas: Cartera Total y Cartera Vigente por fecha · Mapa (o mapa coroplético) por región · Segmentador: bucket |
| **Marketing** | Anillo: Clientes por segmento · Barras: Clientes por región · Tarjetas: Clientes, Penetración Préstamos · Columnas: Clientes Nuevos por mes (`created_month`) |

Usa los colores de CHASKI: verde `#00A94F` (positivo / vigente) y azul `#003B7A` (serie principal). Evita el rojo salvo para mora.

## 5. Seguridad a nivel de fila (RLS)

*Modelado* → **Administrar roles** → *Nuevo* → `Riesgos Norte` → tabla `dim_region`:

```DAX
[name] IN { "La Libertad", "Piura", "Lambayeque" }
```

Las relaciones propagan el filtro a ambos hechos. Pruébalo con *Ver como* → `Riesgos Norte`: Riesgos Norte solo ve las 3 regiones del norte. Es la demostración de seguridad a nivel de fila que pide la guía.

## 6. Publicar y embeber

- **Con Power BI Pro** (o la prueba de 60 días): *Publicar* → workspace `CHASKI` → *Archivo* → *Insertar informe* → **Sitio web o portal** (embed seguro: pide inicio de sesión) → copia la URL.
- Pásala a la consola en la variable `CHASKI_POWERBI_EMBED_URL` de `ca-consola`. Es una línea en `infra/modules/containerapps.bicep` (env de las webs) que se aplica con el workflow de infraestructura. La CSP de las webs ya permite `https://app.powerbi.com`. Aparece como pestaña **Power BI** en Chaski Insights.
- **Sin licencia:** demo desde Power BI Desktop (pantalla compartida). La consola ya muestra los mismos indicadores con sus propios gráficos.

> `Publish to web` (público) solo es aceptable porque los datos son **simulados**. Con datos reales de un banco, nunca: se usa el embed seguro con Entra ID.
