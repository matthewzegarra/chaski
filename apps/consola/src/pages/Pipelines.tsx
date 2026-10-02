/** Data Pipelines (TI, Admin): runs, quality checks, quarantine and manual run. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  cn,
  EmptyState,
  errorMessage,
  formatDateTime,
  formatNumber,
  Skeleton,
  Table,
  TBody,
  TD,
  TH,
  THead,
  toast,
  TR,
  useApi,
} from '@chaski/shared'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, CircleX, Play } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/Layout'
import type { PipelineRun, QualityCheck, QuarantineRecord } from '../types'

const STATUS_VARIANT = {
  EXITOSO: 'success',
  CON_ALERTAS: 'warning',
  FALLIDO: 'danger',
  EN_CURSO: 'info',
} as const
const STATUS_LABEL = {
  EXITOSO: 'Exitoso',
  CON_ALERTAS: 'Con alertas',
  FALLIDO: 'Fallido',
  EN_CURSO: 'En curso',
}

function Checks({ runId }: { runId: string }) {
  const api = useApi()
  const checks = useQuery({
    queryKey: ['checks', runId],
    queryFn: () => api.get<QualityCheck[]>('core', `/ops/pipelines/${runId}/checks`),
  })
  if (checks.isPending) return <Skeleton className="h-40" />
  if (!checks.data?.length)
    return (
      <p className="text-sm text-muted-foreground">Esta corrida no tiene checks (falló antes).</p>
    )
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {checks.data.map((c) => (
        <li key={c.check_name} className="flex items-center gap-2 rounded-lg border p-2 text-sm">
          {c.passed ? (
            <CircleCheck className="size-4 text-brand-600 dark:text-brand-400" aria-label="Pasó" />
          ) : (
            <CircleX className="size-4 text-destructive" aria-label="Falló" />
          )}
          <span className="font-mono text-xs">{c.check_name}</span>
          <span className="ml-auto text-xs text-muted-foreground">
            {c.passed ? 'OK' : `${c.failed_count} filas`}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function PipelinesPage() {
  const api = useApi()
  const qc = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)
  const runs = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => api.get<PipelineRun[]>('core', '/ops/pipelines', { limit: 20 }),
  })
  const quarantine = useQuery({
    queryKey: ['quarantine'],
    queryFn: () => api.get<QuarantineRecord[]>('core', '/ops/quarantine', { limit: 50 }),
  })
  const run = useMutation({
    mutationFn: () =>
      api.post<{ mode: string; run?: PipelineRun; execution?: string }>(
        'core',
        '/ops/pipelines/run',
      ),
    onSuccess: (r) => {
      if (r.mode === 'azure') toast.success(`Job iniciado en Azure (${r.execution})`)
      else
        toast.success(
          `Corrida ${STATUS_LABEL[r.run!.status as keyof typeof STATUS_LABEL]}: ${r.run!.rows_ok} filas OK, ${r.run!.rows_quarantined} a cuarentena`,
        )
      if (r.run) setSelected(r.run.id)
      void qc.invalidateQueries({ queryKey: ['pipelines'] })
      void qc.invalidateQueries({ queryKey: ['quarantine'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const current = selected ?? runs.data?.[0]?.id ?? null

  return (
    <div>
      <PageHeader
        title="Data Pipelines"
        description="Ingesta bronze → silver → gold con checks de calidad y cuarentena"
        actions={
          <Button onClick={() => run.mutate()} loading={run.isPending}>
            <Play /> Ejecutar pipeline
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Corridas recientes</CardTitle>
            <CardDescription>Selecciona una corrida para ver sus checks de calidad</CardDescription>
          </CardHeader>
          <CardContent>
            {runs.isError && <Alert variant="danger">{errorMessage(runs.error)}</Alert>}
            {runs.isPending ? (
              <Skeleton className="h-80" />
            ) : (
              <Table>
                <THead>
                  <tr>
                    <TH>Inicio</TH>
                    <TH>Flujo</TH>
                    <TH>Estado</TH>
                    <TH className="text-right">Filas</TH>
                    <TH className="text-right">OK</TH>
                    <TH className="text-right">Cuarentena</TH>
                  </tr>
                </THead>
                <TBody>
                  {runs.data?.map((r) => (
                    <TR
                      key={r.id}
                      className={cn('cursor-pointer', current === r.id && 'bg-accent/60')}
                      onClick={() => setSelected(r.id)}
                    >
                      <TD>
                        <button
                          className="text-left underline-offset-2 hover:underline"
                          onClick={() => setSelected(r.id)}
                        >
                          {formatDateTime(r.started_at)}
                        </button>
                      </TD>
                      <TD className="font-mono text-xs">{r.flow_name}</TD>
                      <TD>
                        <Badge
                          variant={
                            STATUS_VARIANT[r.status as keyof typeof STATUS_VARIANT] ?? 'default'
                          }
                        >
                          {STATUS_LABEL[r.status as keyof typeof STATUS_LABEL] ?? r.status}
                        </Badge>
                        {r.trigger === 'MANUAL' && (
                          <span className="ml-1 text-xs text-muted-foreground">manual</span>
                        )}
                      </TD>
                      <TD className="text-right tabular-nums">{formatNumber(r.rows_in)}</TD>
                      <TD className="text-right tabular-nums">{formatNumber(r.rows_ok)}</TD>
                      <TD
                        className={cn(
                          'text-right tabular-nums',
                          r.rows_quarantined > 0 && 'font-semibold text-warning',
                        )}
                      >
                        {formatNumber(r.rows_quarantined)}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Checks de calidad</CardTitle>
            <CardDescription>
              {current
                ? formatDateTime(runs.data?.find((r) => r.id === current)?.started_at)
                : 'Sin corrida'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {current ? <Checks runId={current} /> : <EmptyState title="Sin corridas todavía" />}
            {runs.data?.find((r) => r.id === current)?.error && (
              <Alert variant="danger" className="mt-3">
                {runs.data.find((r) => r.id === current)?.error}
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Cuarentena</CardTitle>
          <CardDescription>Registros que no pasaron los checks; no llegan a gold</CardDescription>
        </CardHeader>
        <CardContent>
          {quarantine.isPending ? (
            <Skeleton className="h-40" />
          ) : quarantine.data?.length === 0 ? (
            <EmptyState title="Cuarentena vacía" />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Fecha</TH>
                  <TH>Tabla</TH>
                  <TH>Motivo</TH>
                  <TH>Registro</TH>
                </tr>
              </THead>
              <TBody>
                {quarantine.data?.map((q) => (
                  <TR key={q.id}>
                    <TD className="whitespace-nowrap">{formatDateTime(q.created_at)}</TD>
                    <TD className="font-mono text-xs">{q.table_name}</TD>
                    <TD>{q.reason}</TD>
                    <TD
                      className="max-w-md truncate font-mono text-xs"
                      title={JSON.stringify(q.payload)}
                    >
                      {JSON.stringify(q.payload)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
