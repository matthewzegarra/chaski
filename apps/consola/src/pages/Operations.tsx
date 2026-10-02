/** Centro de Operaciones: live KPIs (15 s), transactions per hour and API health. */
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  errorMessage,
  formatCompactMoney,
  formatDateTime,
  formatNumber,
  formatPercent,
  type Service,
  serviceUrl,
  Skeleton,
  useApi,
} from '@chaski/shared'
import { useQuery } from '@tanstack/react-query'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { PageHeader } from '../components/Layout'
import type { HourPoint, Kpis } from '../types'

const REFRESH_MS = 15_000

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'warning' | 'danger'
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p
          className={`mt-1 text-2xl font-bold tabular-nums ${
            tone === 'danger' ? 'text-destructive' : tone === 'warning' ? 'text-warning' : ''
          }`}
        >
          {value}
        </p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

const SERVICES: { id: Service; label: string }[] = [
  { id: 'cuentas', label: 'cuentas-api' },
  { id: 'core', label: 'core-api' },
  { id: 'ia', label: 'ia-api' },
]

interface Health {
  id: Service
  label: string
  ok: boolean
  latencyMs: number | null
  version: string | null
}

async function checkHealth(id: Service, label: string): Promise<Health> {
  const start = performance.now()
  try {
    const resp = await fetch(`${serviceUrl(id)}/health`, { signal: AbortSignal.timeout(5000) })
    const body = (await resp.json()) as { version?: string }
    return {
      id,
      label,
      ok: resp.ok,
      latencyMs: Math.round(performance.now() - start),
      version: body.version ?? null,
    }
  } catch {
    return { id, label, ok: false, latencyMs: null, version: null }
  }
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { payload: HourPoint }[]
  label?: number
}) {
  if (!active || !payload?.[0]) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-xs shadow-md">
      <p className="font-semibold">
        {String(label).padStart(2, '0')}:00 – {String(label).padStart(2, '0')}:59
      </p>
      <p>{formatNumber(p.cantidad)} transacciones</p>
      <p className="text-muted-foreground">{formatCompactMoney(p.monto)}</p>
    </div>
  )
}

export function OperationsPage() {
  const api = useApi()
  const kpis = useQuery({
    queryKey: ['kpis'],
    queryFn: () => api.get<Kpis>('core', '/ops/kpis'),
    refetchInterval: REFRESH_MS,
  })
  const hours = useQuery({
    queryKey: ['tx-by-hour'],
    queryFn: () => api.get<HourPoint[]>('core', '/ops/transactions-by-hour'),
    refetchInterval: REFRESH_MS,
  })
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => Promise.all(SERVICES.map((s) => checkHealth(s.id, s.label))),
    refetchInterval: REFRESH_MS,
  })
  const k = kpis.data

  return (
    <div>
      <PageHeader
        title="Centro de Operaciones"
        description={
          k ? `Actualizado ${formatDateTime(k.generado_en)} · se refresca cada 15 s` : 'Cargando…'
        }
      />
      {kpis.isError && <p className="mb-4 text-sm text-destructive">{errorMessage(kpis.error)}</p>}
      <section
        aria-label="Indicadores"
        className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
      >
        {!k
          ? Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          : [
              <Stat
                key="tx"
                label="Transacciones hoy"
                value={formatNumber(k.transacciones_hoy)}
                hint={formatCompactMoney(k.monto_transado_hoy)}
              />,
              <Stat
                key="new"
                label="Clientes nuevos hoy"
                value={formatNumber(k.clientes_nuevos_hoy)}
              />,
              <Stat
                key="port"
                label="Cartera de préstamos"
                value={formatCompactMoney(k.cartera_total)}
              />,
              <Stat
                key="mora"
                label="Mora (> 30 días)"
                value={formatPercent(k.mora_pct)}
                tone={k.mora_pct > 8 ? 'danger' : k.mora_pct > 5 ? 'warning' : undefined}
              />,
              <Stat
                key="alerts"
                label="Alertas de fraude abiertas"
                value={formatNumber(k.alertas_abiertas)}
                tone={k.alertas_abiertas > 0 ? 'danger' : undefined}
              />,
              <Stat key="cq" label="Quejas abiertas" value={formatNumber(k.quejas_abiertas)} />,
              <Stat
                key="due"
                label="Quejas por vencer (3 días)"
                value={formatNumber(k.quejas_por_vencer)}
                tone={k.quejas_por_vencer > 0 ? 'warning' : undefined}
              />,
              <Stat
                key="loans"
                label="Préstamos por evaluar"
                value={formatNumber(k.prestamos_por_revisar)}
              />,
              <Stat
                key="kyc"
                label="Onboarding pendiente"
                value={formatNumber(k.onboarding_pendiente)}
              />,
            ]}
      </section>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Transacciones por hora (hoy)</CardTitle>
            <CardDescription>Hora de Lima</CardDescription>
          </CardHeader>
          <CardContent>
            {hours.isPending ? (
              <Skeleton className="h-64" />
            ) : (
              <div
                className="h-64"
                role="img"
                aria-label="Gráfico de barras de transacciones por hora"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hours.data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis
                      dataKey="hora"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      tickFormatter={(h: number) => `${h}h`}
                      interval={1}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                    />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--muted)' }} />
                    <Bar
                      dataKey="cantidad"
                      fill="var(--color-brand-500)"
                      radius={[4, 4, 0, 0]}
                      maxBarSize={22}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Salud de las APIs</CardTitle>
            <CardDescription>GET /health de cada servicio</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {(
                health.data ??
                SERVICES.map((s) => ({ ...s, ok: null, latencyMs: null, version: null }))
              ).map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 py-3">
                  <span className="flex items-center gap-2 font-medium">
                    {s.ok === null ? (
                      <Skeleton className="size-4 rounded-full" />
                    ) : s.ok ? (
                      <CircleCheck
                        className="size-4 text-brand-600 dark:text-brand-400"
                        aria-hidden
                      />
                    ) : (
                      <CircleAlert className="size-4 text-destructive" aria-hidden />
                    )}
                    {s.label}
                  </span>
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    {s.latencyMs !== null && `${s.latencyMs} ms`}
                    {s.version && `· v${s.version}`}
                    {s.ok !== null && (
                      <Badge variant={s.ok ? 'success' : 'danger'}>
                        {s.ok ? 'Operativo' : 'Caído'}
                      </Badge>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
