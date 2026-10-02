/** Salud de IA (TI, Admin): quality, human review, shields blocks and latency per use case. */
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  errorMessage,
  formatNumber,
  formatPercent,
  Skeleton,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
  useApi,
} from '@chaski/shared'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AXIS, ChartFrame, ChartTooltip, CURSOR, SERIES } from '../components/charts'
import { PageHeader } from '../components/Layout'
import type { AiHealthMetrics } from '../types'

const USE_CASE_LABELS: Record<string, string> = {
  complaint_classification: 'Clasificador de quejas',
  loan_explanation: 'Explicación de score',
  assistant: 'Chaski Asistente',
  executive_summary: 'Resumen ejecutivo',
  nl2sql: 'Pregúntale al banco',
  kyc_extraction: 'Lectura de DNI (KYC)',
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

export function AiHealthPage() {
  const api = useApi()
  const m = useQuery({
    queryKey: ['ai-health'],
    queryFn: () => api.get<AiHealthMetrics>('ia', '/ai/health-metrics'),
    refetchInterval: 30_000,
  })
  if (m.isPending) return <Skeleton className="h-96" />
  if (m.isError) return <Alert variant="danger">{errorMessage(m.error)}</Alert>
  const d = m.data
  const latency = d.por_caso_de_uso.map((c) => ({
    ...c,
    label: USE_CASE_LABELS[c.use_case] ?? c.use_case,
    latencia: Number(c.latencia_promedio_ms ?? 0),
  }))
  return (
    <div>
      <PageHeader
        title="Salud de IA"
        description={`Últimos ${d.ventana_dias} días · modo ${d.modo === 'azure' ? 'Azure OpenAI' : 'mock local'}`}
      />
      <section aria-label="Indicadores de IA" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Tile
          label="Precisión IA vs humano"
          value={
            d.precision_ia_vs_humano_pct != null ? formatPercent(d.precision_ia_vs_humano_pct) : '—'
          }
          hint={`${formatNumber(d.quejas_resueltas_evaluadas)} quejas revisadas`}
        />
        <Tile
          label="Revisión manual"
          value={
            d.tasa_revision_manual_pct != null ? formatPercent(d.tasa_revision_manual_pct) : '—'
          }
          hint="FRAUDE, confianza < 80 % o sospechosas"
        />
        <Tile label="Correcciones humanas" value={formatNumber(d.correcciones_humanas)} />
        <Tile label="Quejas sospechosas" value={formatNumber(d.quejas_sospechosas)} />
        <Tile
          label="Inyecciones bloqueadas (7 d)"
          value={formatNumber(d.bloqueos_prompt_shields_7d)}
          hint="Prompt Shields"
        />
      </section>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Latencia promedio por caso de uso</CardTitle>
            <CardDescription>Milisegundos por llamada</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartFrame
              label="Latencia promedio por caso de uso"
              table={{
                headers: ['Caso de uso', 'Latencia (ms)'],
                rows: latency.map((l) => [l.label, l.latencia]),
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={latency}
                  layout="vertical"
                  margin={{ top: 0, right: 56, left: 8, bottom: 0 }}
                >
                  <CartesianGrid horizontal={false} stroke="var(--border)" />
                  <XAxis type="number" {...AXIS} />
                  <YAxis type="category" dataKey="label" width={150} {...AXIS} />
                  <Tooltip
                    cursor={CURSOR}
                    content={<ChartTooltip format={(v) => `${formatNumber(v)} ms`} />}
                  />
                  <Bar
                    isAnimationActive={false}
                    dataKey="latencia"
                    name="Latencia"
                    fill={SERIES[0]}
                    radius={[0, 4, 4, 0]}
                    maxBarSize={18}
                  >
                    <LabelList
                      dataKey="latencia"
                      position="right"
                      formatter={(v: unknown) => `${formatNumber(Number(v))} ms`}
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
            <CardTitle>Detalle por caso de uso</CardTitle>
            <CardDescription>Prompt y versión registrados en cada llamada</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <tr>
                  <TH>Caso de uso</TH>
                  <TH>Prompt</TH>
                  <TH className="text-right">Llamadas</TH>
                  <TH className="text-right">p95</TH>
                  <TH className="text-right">Bloqueos</TH>
                </tr>
              </THead>
              <TBody>
                {d.por_caso_de_uso.map((c) => (
                  <TR key={c.use_case}>
                    <TD>{USE_CASE_LABELS[c.use_case] ?? c.use_case}</TD>
                    <TD>
                      <span className="font-mono text-xs">{c.prompt_id}</span>{' '}
                      <Badge variant="info">v{c.version_prompt}</Badge>
                    </TD>
                    <TD className="text-right tabular-nums">{formatNumber(c.llamadas)}</TD>
                    <TD className="text-right tabular-nums">
                      {formatNumber(Number(c.latencia_p95_ms ?? 0))} ms
                    </TD>
                    <TD className="text-right tabular-nums">{formatNumber(c.bloqueos_shields)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
