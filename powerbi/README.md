# Power BI · Chaski Insights (Fase 8)

Informe de toma de decisiones para **Dirección, Riesgos y Marketing**, con un **Simulador de Decisiones** (escenarios what-if). Se conecta al DW en Azure SQL que carga el pipeline (`caj-pipeline`, cada noche a las 22:00 Lima, o con el botón "Ejecutar pipeline" de la consola).

Cubre del PDF: *"Presentación de Reportes en Power BI para la simulación de toma de decisiones"* y la capa b) *"dashboards de negocio (dirección, riesgos, marketing)"*.

| Archivo | Uso |
|---|---|
| `README.md` | Esta guía |
| `medidas.dax` | Todas las medidas y el simulador |
| `chaski-theme.json` | Tema visual CHASKI |
| `chaski.pbix` | Informe final (se genera en Desktop) |
| `chaski.pdf` | Export del informe como evidencia |

Tiempo estimado: 2 a 3 horas.

---

## 1. Conexión

| Dato | Valor |
|---|---|
| Servidor | `sql-chaski-xrghkf.database.windows.net` |
| Base de datos | `sqldb-chaski-dw` |
| Esquema | `dw` |
| Autenticación | **Cuenta de Microsoft** (Entra ID) con `U21200917@utp.edu.pe`, admin de Entra del servidor. **No existen usuarios con contraseña** (solo Entra). |
| Red | El firewall acepta la IP del admin (variable `INFRA_ADMIN_IP` de GitHub). Si cambias de red, actualízala y corre el workflow `infra (Bicep)`. |

> Azure SQL usa la oferta gratuita con **pausa automática**: la primera conexión del día puede tardar hasta 1 minuto mientras despierta. Es normal.

1. Power BI Desktop → *Obtener datos* → **Azure SQL Database** → servidor y base de la tabla → modo **Importar** (no DirectQuery: no despierta la base en cada clic y la demo va más rápida).
2. Credenciales: **Cuenta de Microsoft** → *Iniciar sesión* con la cuenta UTP.
3. Selecciona: `dw.dim_date`, `dw.dim_region`, `dw.dim_product`, `dw.dim_customer`, `dw.dim_delinquency_bucket`, `dw.fact_profitability_monthly`, `dw.fact_portfolio_daily` y la vista `dw.v_rentabilidad_rollup`.
4. *Vista* → *Temas* → *Examinar temas* → `chaski-theme.json`.

---

## 2. Modelo estrella (vista *Modelo*)

| Desde (hechos) | Hacia (dimensión) | Columnas | Cardinalidad |
|---|---|---|---|
| `fact_portfolio_daily[date]` | `dim_date[date]` | fecha | Varios a uno |
| `fact_profitability_monthly[month]` | `dim_date[date]` | primer día del mes | Varios a uno |
| `fact_portfolio_daily[region]` | `dim_region[name]` | región | Varios a uno |
| `fact_profitability_monthly[region]` | `dim_region[name]` | región | Varios a uno |
| `fact_profitability_monthly[product]` | `dim_product[code]` | producto | Varios a uno |
| `fact_portfolio_daily[bucket]` | `dim_delinquency_bucket[name]` | bucket SBS | Varios a uno |

- `dim_customer` es **SCD2**: filas antiguas guardan la historia de segmento y región. Las medidas de clientes filtran `is_current = 1` (no hace falta filtrar en Power Query, así la historia queda disponible).
- `dim_customer` **no se relaciona** con los hechos; sus medidas usan `created_month` y `active_loans` directamente.
- Marca `dim_date` como **tabla de fechas** (columna `date`). Si no tiene columnas de mes, agrégalas (sección 0 de `medidas.dax`).
- Ordena `dim_delinquency_bucket[name]` por su columna de orden (Normal, CPP, Deficiente, Dudoso, Pérdida).
- Oculta en la vista de informe las columnas de unión de los hechos (`region`, `product`, `bucket`, `date`, `month`) para usar siempre las de las dimensiones.

---

## 3. Medidas y parámetros

1. *Inicio* → *Especificar datos* → tabla vacía `_Medidas`.
2. Copia todas las medidas de `medidas.dax` con el formato indicado en cada comentario: moneda **S/** con 0 decimales para montos y porcentaje con 1 decimal para ratios.
3. Crea los 4 parámetros what-if (*Modelado* → *Nuevo parámetro* → *Rango numérico*): **Shock Mora**, **Variación Tasa**, **Umbral Mora**, **LGD**, con los rangos de la sección 4 de `medidas.dax`.

> **Regla clave:** `fact_portfolio_daily` es un snapshot diario. Todas las medidas de cartera leen la **fecha de corte** (último día con datos del filtro). Sumar todos los días infla la cartera unas 30 veces al ver un mes.

### Validación contra el DW
Antes de armar visuales, compara en Azure SQL:

```sql
DECLARE @corte date = (SELECT MAX([date]) FROM dw.fact_portfolio_daily);
SELECT
    @corte AS fecha_corte,
    SUM(outstanding_balance) AS cartera_total,
    SUM(CASE WHEN days_past_due > 30 THEN outstanding_balance ELSE 0 END)
        * 1.0 / NULLIF(SUM(outstanding_balance), 0) AS ratio_mora
FROM dw.fact_portfolio_daily
WHERE [date] = @corte;
```

Una tarjeta sin filtros con `Cartera Total` y `Ratio Mora` debe dar los mismos valores. Anótalos aquí:

| Fecha de corte | Cartera Total | Ratio Mora |
|---|---|---|
| | | |

---

## 4. Páginas

Encabezado común: logo CHASKI, título y segmentadores de **Mes** y **Región** sincronizados entre páginas (*Vista* → *Sincronizar segmentaciones*). Colores: verde `#00A94F` (positivo/vigente), azul `#003B7A` (serie principal), rojo solo para mora.

### Página 1 · Resumen Ejecutivo
| Visual | Contenido |
|---|---|
| 6 tarjetas | Ingresos, Margen, Margen %, Cartera Total, Ratio Mora, Clientes |
| Líneas | Margen y Margen YTD por mes |
| Columnas + línea | Cartera Total por mes, Ratio Mora en eje secundario |
| Tarjetas de texto | Producto Más Rentable, Región con Mayor Mora |
| Narrativa inteligente | Resumen automático de los KPIs |

### Página 2 · Dirección · Rentabilidad
| Visual | Contenido |
|---|---|
| Tarjetas | Margen, Ingresos, Margen %, Var. Margen MoM % |
| Cascada | Ingresos por Intereses + Comisiones − Costo de Fondeo − Provisiones = Margen |
| Barras | Margen por producto (`dim_product[code]`) |
| Líneas | Margen por mes |
| Barras | Top 5 regiones por margen (filtro Top N) |
| Tabla | `v_rentabilidad_rollup` (subtotales y total con `ROLLUP`, evidencia de SQL analítico) |
| Segmentador | Segmento |

**Pregunta de negocio:** *¿Qué producto y segmento generan más margen y dónde crecer?*

### Página 3 · Riesgos · Morosidad
| Visual | Contenido |
|---|---|
| Título dinámico | Medida `Título Riesgos` |
| Tarjetas | Ratio Mora, Var. Mora (pb), Ratio Alto Riesgo, Cartera Atrasada |
| Columnas apiladas 100% | Cartera Total por mes y bucket SBS |
| Barras | Ratio Mora por región, color con `Color Mora` + línea constante del umbral |
| Líneas | Cartera Total y Cartera Vigente por mes |
| Mapa coroplético | Ratio Mora por región |
| Árbol de descomposición | Cartera Atrasada por región → bucket |
| Segmentador | Bucket |

Configura **obtención de detalles** hacia una página oculta **Detalle Región**: tendencia de Ratio Mora, cartera por bucket y margen de esa región.

**Pregunta de negocio:** *¿Dónde se deteriora la cartera y qué tan grave es?*

### Página 4 · Marketing · Clientes
| Visual | Contenido |
|---|---|
| Tarjetas | Clientes, Clientes con Préstamo, Penetración Préstamos, Margen por Cliente |
| Anillo | Clientes por segmento (`dim_customer[segment]`) |
| Barras | Clientes por región (`dim_customer[region]`) |
| Columnas | Clientes Nuevos (mes) por mes |
| Barras | Penetración Préstamos por segmento |

**Pregunta de negocio:** *¿Qué segmento tiene muchos clientes pero baja penetración de préstamos?* Ahí va la campaña.

### Página 5 · Simulador de Decisiones
| Visual | Contenido |
|---|---|
| 4 segmentadores de parámetro | Shock Mora, Variación Tasa, Umbral Mora, LGD |
| Segmentador de mes | Selección única, por defecto el último mes |
| Tarjetas comparativas | Ratio Mora vs. Mora Simulada · Margen vs. Margen Simulado · Var. Margen Simulado % · Pérdida Esperada Adicional |
| Columnas agrupadas | Por región: Ratio Mora vs. Mora Simulada, con línea del umbral |
| Tabla | Regiones con Mora Simulada mayor al umbral |
| Tarjeta grande | **Decisión Sugerida** |

**Marcadores** (con botones en la página):
- **Escenario base:** todo en 0.
- **Estrés moderado:** shock 30%, tasa +10%.
- **Estrés severo:** shock 80%, tasa +20%.

Supuestos del simulador (decirlos en la exposición): la mora sube con sensibilidad 0.5 ante alzas de tasa; la pérdida esperada es cartera × aumento de mora × LGD; el impacto se lee sobre un mes.

---

## 5. Seguridad a nivel de fila (RLS)

*Modelado* → **Administrar roles**:

| Rol | Tabla | Filtro DAX |
|---|---|---|
| Direccion | (sin filtro) | Ve todo |
| Riesgos Norte | `dim_region` | `[name] IN { "La Libertad", "Piura", "Lambayeque" }` |
| Riesgos Sur | `dim_region` | `[name] IN { "Arequipa", "Cusco" }` |

Las relaciones propagan el filtro a ambos hechos. Prueba con *Ver como* → `Riesgos Norte`: solo ve las 3 regiones del norte. Toma captura para la PPT.

**Para la defensa:** RLS en Power BI se suma al RBAC de la consola, a la autenticación solo Entra y al firewall de Azure SQL: seguridad en cada capa.

---

## 6. Escenarios de decisión para la exposición

| # | Área | Pregunta | Dónde se responde | Decisión |
|---|---|---|---|---|
| 1 | Dirección | ¿Qué producto impulsar? | Cascada y Margen por producto (pág. 2) | Priorizar el producto con mayor Margen % |
| 2 | Riesgos | ¿Qué región frenar? | Barras con Color Mora + Detalle Región (pág. 3) | Endurecer políticas en la región en rojo |
| 3 | Marketing | ¿A quién dirigir la campaña? | Penetración por segmento (pág. 4) | Segmento con más clientes y menor penetración |
| 4 | Comité | ¿Qué pasa si la mora sube 30% y las tasas 10%? | Simulador, marcador "Estrés moderado" | Lo que indique Decisión Sugerida, con la pérdida cuantificada |

Guion en la demo (2 minutos): Resumen → Riesgos (región en rojo y drillthrough) → Simulador (cambiar de marcador en vivo y leer la decisión).

---

## 7. Publicar y embeber

- **Con Power BI Pro** (o la prueba de 60 días): *Publicar* → workspace `CHASKI` → *Archivo* → *Insertar informe* → **Sitio web o portal** (embed seguro: pide inicio de sesión) → copia la URL.
- Pásala a la consola en la variable `CHASKI_POWERBI_EMBED_URL` de `ca-consola`. Es una línea en `infra/modules/containerapps.bicep` (env de las webs) que se aplica con el workflow de infraestructura. La CSP de las webs ya permite `https://app.powerbi.com`. Aparece como pestaña **Power BI** en Chaski Insights.
- **Sin licencia:** demo desde Power BI Desktop (pantalla compartida). La consola ya muestra los mismos indicadores con sus propios gráficos.

> `Publish to web` (público) solo es aceptable porque los datos son **simulados**. Con datos reales de un banco, nunca: se usa el embed seguro con Entra ID.

---

## 8. Checklist

- [ ] Conexión en modo Importar con cuenta UTP
- [ ] Relaciones y `dim_date` marcada como tabla de fechas
- [ ] Medidas de `medidas.dax` y 4 parámetros what-if
- [ ] Validación SQL vs. tarjetas anotada en la sección 3
- [ ] 5 páginas + Detalle Región (drillthrough)
- [ ] 3 marcadores de escenarios con botones
- [ ] RLS probado con *Ver como*
- [ ] `chaski.pbix` y `chaski.pdf` en `powerbi/`
- [ ] Capturas en la PPT
