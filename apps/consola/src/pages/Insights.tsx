/** Chaski Insights: profitability, delinquency, "Pregúntale al banco" (NL2SQL) and executive summary. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  config,
  EmptyState,
  errorMessage,
  formatCompactMoney,
  formatDate,
  formatMoney,
  formatPercent,
  Input,
  Select,
  Skeleton,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  TBody,
  TD,
  TH,
  THead,
  TR,
  useApi,
} from '@chaski/shared'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CircleAlert, CircleCheck, Sparkles } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AXIS, ChartFrame, ChartTooltip, CURSOR, GRID, Legend, SERIES } from '../components/charts'
import { PageHeader } from '../components/Layout'
import type { AskResult, Delinquency, ExecutiveSummary, Profitability } from '../types'

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic']
const monthLabel = (iso: string | number) => {
  const [y, m] = String(iso).split('-')
  return `${MONTHS[Number(m) - 1]} ${y?.slice(2)}`
}
const PRODUCT_LABELS: Record<string, string> = {
  AHORRO_SOLES: 'Ahorro S/',
  AHORRO_DOLARES: 'Ahorro US$',
  PRESTAMO_CONSUMO: 'Préstamo consumo',
  TARJETA_CREDITO: 'Tarjeta crédito',
}
const DIMENSION_LABELS = { product: 'Producto', segment: 'Segmento', region: 'Región' } as const

// ------------------------------------------------------------------ profitability

function ProfitabilitySection() {
  const api = useApi()
  const [dimension, setDimension] = useState<keyof typeof DIMENSION_LABELS>('product')
  const q = useQuery({
    queryKey: ['profitability', dimension],
    queryFn: () =>
      api.get<Profitability>('core', '/analytics/profitability', { dimension, months: 6 }),
  })
  const rows =
    q.data?.by_dimension.map((r) => ({
      ...r,
      label: dimension === 'product' ? (PRODUCT_LABELS[r.dimension] ?? r.dimension) : r.dimension,
    })) ?? []
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Margen por {DIMENSION_LABELS[dimension].toLowerCase()}</CardTitle>
            <CardDescription>Últimos 6 meses, en soles</CardDescription>
          </div>
          <label htmlFor="dim" className="sr-only">
            Dimensión
          </label>
          <Select
            id="dim"
            className="h-9 w-36"
            value={dimension}
            onChange={(e) => setDimension(e.target.value as keyof typeof DIMENSION_LABELS)}
          >
            {Object.entries(DIMENSION_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </CardHeader>
        <CardContent>
          {q.isPending ? (
            <Skeleton className="h-64" />
          ) : q.isError ? (
            <Alert variant="danger">{errorMessage(q.error)}</Alert>
          ) : (
            <ChartFrame
              label={`Margen por ${DIMENSION_LABELS[dimension]}`}
              table={{
                headers: ['Dimensión', 'Margen'],
                rows: rows.map((r) => [r.label, formatMoney(r.margen)]),
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={rows}
                  layout="vertical"
                  margin={{ top: 4, right: 64, left: 8, bottom: 0 }}
                >
                  <CartesianGrid horizontal={false} stroke="var(--border)" />
                  <XAxis
                    type="number"
                    {...AXIS}
                    tickFormatter={(v: number) => formatCompactMoney(v)}
                  />
                  <YAxis type="category" dataKey="label" width={110} {...AXIS} />
                  <Tooltip
                    cursor={CURSOR}
                    content={<ChartTooltip format={(v) => formatMoney(v)} />}
                  />
                  <Bar
                    isAnimationActive={false}
                    dataKey="margen"
                    name="Margen"
                    fill={SERIES[1]}
                    radius={[0, 4, 4, 0]}
                    maxBarSize={22}
                  >
                    <LabelList
                      dataKey="margen"
                      position="right"
                      formatter={(v: unknown) => formatCompactMoney(Number(v))}
                      style={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Evolución mensual</CardTitle>
          <CardDescription>Ingresos (intereses + comisiones) y margen</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Legend
            items={[
              { label: 'Ingresos', color: SERIES[0] },
              { label: 'Margen', color: SERIES[1] },
            ]}
          />
          {q.isPending ? (
            <Skeleton className="h-60" />
          ) : (
            <ChartFrame
              label="Ingresos y margen mensual"
              height="h-60"
              table={{
                headers: ['Mes', 'Ingresos', 'Margen'],
                rows: (q.data?.monthly ?? []).map((m) => [
                  monthLabel(m.mes),
                  formatMoney(m.ingresos),
                  formatMoney(m.margen),
                ]),
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={q.data?.monthly}
                  margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
                >
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="mes" {...AXIS} tickFormatter={monthLabel} />
                  <YAxis
                    {...AXIS}
                    width={70}
                    tickFormatter={(v: number) => formatCompactMoney(v)}
                  />
                  <Tooltip
                    content={
                      <ChartTooltip format={(v) => formatMoney(v)} labelFormat={monthLabel} />
                    }
                  />
                  <Line
                    isAnimationActive={false}
                    dataKey="ingresos"
                    name="Ingresos"
                    stroke={SERIES[0]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                  <Line
                    isAnimationActive={false}
                    dataKey="margen"
                    name="Margen"
                    stroke={SERIES[1]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </ChartFrame>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ delinquency

function DelinquencySection() {
  const api = useApi()
  const q = useQuery({
    queryKey: ['delinquency'],
    queryFn: () => api.get<Delinquency>('core', '/analytics/delinquency', { days: 90 }),
  })
  if (q.isPending) return <Skeleton className="h-72" />
  if (q.isError) return <Alert variant="danger">{errorMessage(q.error)}</Alert>
  const d = q.data
  const regions = [...d.by_region].sort((a, b) => b.mora_pct - a.mora_pct)
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Cartera por calificación</CardTitle>
          <CardDescription>
            Saldo por bucket SBS al {formatDate(d.fecha)} · etiqueta: n.º de préstamos
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartFrame
            label="Saldo por bucket de morosidad"
            table={{
              headers: ['Bucket', 'Préstamos', 'Saldo'],
              rows: d.by_bucket.map((b) => [b.bucket, b.prestamos, formatMoney(b.saldo)]),
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.by_bucket} margin={{ top: 24, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="bucket" {...AXIS} />
                <YAxis {...AXIS} width={64} tickFormatter={(v: number) => formatCompactMoney(v)} />
                <Tooltip
                  cursor={CURSOR}
                  content={<ChartTooltip format={(v) => formatMoney(v)} />}
                />
                <Bar
                  isAnimationActive={false}
                  dataKey="saldo"
                  name="Saldo"
                  fill={SERIES[0]}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={36}
                >
                  <LabelList
                    dataKey="prestamos"
                    position="top"
                    formatter={(v: unknown) => String(v)}
                    style={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Mora por región</CardTitle>
          <CardDescription>Saldo con más de 30 días de atraso / saldo total</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartFrame
            label="Mora por región"
            table={{
              headers: ['Región', 'Mora'],
              rows: regions.map((r) => [r.region, formatPercent(r.mora_pct, 2)]),
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={regions}
                layout="vertical"
                margin={{ top: 0, right: 48, left: 8, bottom: 0 }}
              >
                <CartesianGrid horizontal={false} stroke="var(--border)" />
                <XAxis type="number" {...AXIS} tickFormatter={(v: number) => `${v} %`} />
                <YAxis type="category" dataKey="region" width={86} {...AXIS} />
                <Tooltip
                  cursor={CURSOR}
                  content={<ChartTooltip format={(v) => formatPercent(v, 2)} />}
                />
                <Bar
                  isAnimationActive={false}
                  dataKey="mora_pct"
                  name="Mora"
                  fill={SERIES[0]}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={16}
                >
                  <LabelList
                    dataKey="mora_pct"
                    position="right"
                    formatter={(v: unknown) => formatPercent(Number(v))}
                    style={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Tendencia de la mora</CardTitle>
          <CardDescription>Últimos 90 días</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartFrame
            label="Tendencia diaria de la mora"
            table={{
              headers: ['Fecha', 'Mora'],
              rows: d.trend.map((t) => [formatDate(t.fecha), formatPercent(t.mora_pct, 2)]),
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={d.trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...GRID} />
                <XAxis
                  dataKey="fecha"
                  {...AXIS}
                  tickFormatter={(f: string) => formatDate(f).slice(0, 6)}
                  minTickGap={24}
                />
                <YAxis
                  {...AXIS}
                  width={44}
                  tickFormatter={(v: number) => `${v} %`}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  content={
                    <ChartTooltip
                      format={(v) => formatPercent(v, 2)}
                      labelFormat={(l) => formatDate(String(l))}
                    />
                  }
                />
                <Line
                  isAnimationActive={false}
                  dataKey="mora_pct"
                  name="Mora"
                  stroke={SERIES[0]}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartFrame>
        </CardContent>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ NL2SQL

const SUGGESTIONS = [
  '¿Cuál es la mora por región?',
  'Margen por producto',
  'Evolución mensual del margen',
  'Clientes por segmento',
]

function AskSection() {
  const api = useApi()
  const [question, setQuestion] = useState('')
  const ask = useMutation({
    mutationFn: (pregunta: string) => api.post<AskResult>('ia', '/analytics/ask', { pregunta }),
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    if (question.trim().length >= 3) ask.mutate(question.trim())
  }
  const r = ask.data
  const numericCol = r?.columnas.find((c) => r.filas.some((f) => typeof f[c] === 'number'))
  const labelCol = r?.columnas.find((c) => c !== numericCol)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-brand-600 dark:text-brand-400" aria-hidden /> Pregúntale
          al banco
        </CardTitle>
        <CardDescription>
          Lenguaje natural → SQL de solo lectura sobre las vistas de gold. Siempre verás la consulta
          ejecutada.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor="ask" className="sr-only">
            Pregunta
          </label>
          <Input
            id="ask"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ej. ¿Qué región tiene la mora más alta?"
            maxLength={500}
          />
          <Button type="submit" loading={ask.isPending}>
            Preguntar
          </Button>
        </form>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <Button
              key={s}
              size="sm"
              variant="outline"
              onClick={() => {
                setQuestion(s)
                ask.mutate(s)
              }}
            >
              {s}
            </Button>
          ))}
        </div>
        {ask.isError && <Alert variant="danger">{errorMessage(ask.error)}</Alert>}
        {r && (
          <div className="flex flex-col gap-3">
            <p className="text-sm">{r.respuesta}</p>
            {r.filas.length > 0 && numericCol && labelCol && r.grafico !== 'table' && (
              <ChartFrame
                label={`Resultado: ${numericCol} por ${labelCol}`}
                height="h-56"
                table={{
                  headers: r.columnas,
                  rows: r.filas.map((f) => r.columnas.map((c) => String(f[c] ?? ''))),
                }}
              >
                <ResponsiveContainer width="100%" height="100%">
                  {r.grafico === 'line' ? (
                    <LineChart data={r.filas} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey={labelCol} {...AXIS} minTickGap={24} />
                      <YAxis {...AXIS} width={64} />
                      <Tooltip
                        content={<ChartTooltip format={(v) => v.toLocaleString('en-US')} />}
                      />
                      <Line
                        isAnimationActive={false}
                        dataKey={numericCol}
                        name={numericCol}
                        stroke={SERIES[0]}
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  ) : (
                    <BarChart data={r.filas} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...GRID} />
                      <XAxis dataKey={labelCol} {...AXIS} />
                      <YAxis {...AXIS} width={64} />
                      <Tooltip
                        cursor={CURSOR}
                        content={<ChartTooltip format={(v) => v.toLocaleString('en-US')} />}
                      />
                      <Bar
                        isAnimationActive={false}
                        dataKey={numericCol}
                        name={numericCol}
                        fill={SERIES[0]}
                        radius={[4, 4, 0, 0]}
                        maxBarSize={36}
                      />
                    </BarChart>
                  )}
                </ResponsiveContainer>
              </ChartFrame>
            )}
            {r.filas.length > 0 && (
              <div className="max-h-64 overflow-auto rounded-lg border">
                <Table>
                  <THead>
                    <tr>
                      {r.columnas.map((c) => (
                        <TH key={c}>{c}</TH>
                      ))}
                    </tr>
                  </THead>
                  <TBody>
                    {r.filas.slice(0, 100).map((f, i) => (
                      <TR key={i}>
                        {r.columnas.map((c) => (
                          <TD
                            key={c}
                            className={typeof f[c] === 'number' ? 'text-right tabular-nums' : ''}
                          >
                            {typeof f[c] === 'number'
                              ? (f[c] as number).toLocaleString('en-US')
                              : String(f[c] ?? '')}
                          </TD>
                        ))}
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            )}
            {r.sql && (
              <details open className="rounded-lg bg-muted/60 p-3 text-xs">
                <summary className="cursor-pointer font-semibold">SQL ejecutada</summary>
                <pre className="mt-2 whitespace-pre-wrap break-all font-mono">{r.sql}</pre>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------ executive summary

function SummarySection() {
  const api = useApi()
  const gen = useMutation({
    mutationFn: () => api.post<ExecutiveSummary>('ia', '/reports/executive-summary'),
  })
  const s = gen.data
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Resumen ejecutivo</CardTitle>
          <CardDescription>
            KPIs calculados con SQL sobre gold; la IA solo redacta. Un validador verifica cada
            cifra.
          </CardDescription>
        </div>
        <Button onClick={() => gen.mutate()} loading={gen.isPending}>
          <Sparkles /> Generar resumen ejecutivo
        </Button>
      </CardHeader>
      <CardContent>
        {gen.isError && <Alert variant="danger">{errorMessage(gen.error)}</Alert>}
        {!s && !gen.isError && (
          <EmptyState
            title="Aún no se generó el resumen"
            description="Se calcula sobre el último mes cerrado."
          />
        )}
        {s && (
          <div className="flex flex-col gap-3">
            {s.valido ? (
              <Badge variant="success" className="self-start">
                <CircleCheck className="size-3" aria-hidden /> Cifras validadas · publicado
              </Badge>
            ) : (
              <Alert variant="warning">
                <span className="flex items-center gap-1 font-semibold">
                  <CircleAlert className="size-4" aria-hidden /> Requiere revisión: no se publica
                </span>
                Cifras sin respaldo en los KPIs: {s.numeros_no_validados.join(', ')}
              </Alert>
            )}
            <p className="leading-relaxed">{s.resumen}</p>
            <dl className="grid grid-cols-2 gap-2 rounded-lg bg-muted/60 p-3 text-xs sm:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">Periodo</dt>
                <dd className="font-medium">{s.kpis.periodo}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Margen</dt>
                <dd className="font-medium">{formatMoney(s.kpis.margen_mes)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Variación</dt>
                <dd className="font-medium">{formatPercent(s.kpis.variacion_margen_pct)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Mora</dt>
                <dd className="font-medium">{formatPercent(s.kpis.mora_pct, 2)}</dd>
              </div>
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function InsightsPage() {
  return (
    <div>
      <PageHeader
        title="Chaski Insights"
        description="Rentabilidad, morosidad y analítica asistida por IA"
      />
      <Tabs defaultValue="tablero">
        <TabsList className="mb-4">
          <TabsTrigger value="tablero">Tablero</TabsTrigger>
          <TabsTrigger value="preguntar">Pregúntale al banco</TabsTrigger>
          <TabsTrigger value="resumen">Resumen ejecutivo</TabsTrigger>
          {config.powerbiEmbedUrl && <TabsTrigger value="powerbi">Power BI</TabsTrigger>}
        </TabsList>
        <TabsContent value="tablero" className="flex flex-col gap-4">
          <ProfitabilitySection />
          <DelinquencySection />
        </TabsContent>
        <TabsContent value="preguntar">
          <AskSection />
        </TabsContent>
        <TabsContent value="resumen">
          <SummarySection />
        </TabsContent>
        {config.powerbiEmbedUrl && (
          <TabsContent value="powerbi">
            <iframe
              title="Reporte Power BI"
              src={config.powerbiEmbedUrl}
              className="h-[75vh] w-full rounded-xl border"
              allowFullScreen
            />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
