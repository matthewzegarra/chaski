/** DevOps (TI): version per environment and latest GitHub Actions runs. */
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  errorMessage,
  formatDateTime,
  formatRelative,
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
import { GitCommitHorizontal } from 'lucide-react'

import { PageHeader } from '../components/Layout'
import type { Deployments } from '../types'

const STATUS_VARIANT: Record<string, 'success' | 'danger' | 'info' | 'warning'> = {
  success: 'success',
  failure: 'danger',
  cancelled: 'warning',
  in_progress: 'info',
  queued: 'info',
}
const STATUS_LABEL: Record<string, string> = {
  success: 'Exitoso',
  failure: 'Fallido',
  cancelled: 'Cancelado',
  in_progress: 'En curso',
  queued: 'En cola',
}
const ENVS = ['DEV', 'TEST', 'PROD'] as const

export function DevOpsPage() {
  const api = useApi()
  const q = useQuery({
    queryKey: ['deployments'],
    queryFn: () => api.get<Deployments>('core', '/devops/deployments'),
    refetchInterval: 60_000,
  })
  if (q.isPending) return <Skeleton className="h-96" />
  if (q.isError) return <Alert variant="danger">{errorMessage(q.error)}</Alert>
  const d = q.data
  return (
    <div>
      <PageHeader
        title="DevOps"
        description={
          d.source === 'github'
            ? 'Últimas ejecuciones de GitHub Actions'
            : 'Datos simulados: GITHUB_REPO y GITHUB_TOKEN no están configurados'
        }
      />
      <section className="mb-4 grid gap-3 sm:grid-cols-3" aria-label="Versión por entorno">
        {ENVS.map((env) => {
          const v = d.versions[env]
          return (
            <Card key={env}>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Versión en {env}</p>
                <p className="mt-1 flex items-center gap-2 font-mono text-lg font-bold">
                  <GitCommitHorizontal className="size-4" aria-hidden />
                  {v ? v.commit : '—'}
                </p>
                {v && (
                  <p className="text-xs text-muted-foreground">
                    Desplegado {formatRelative(v.deployed_at)}
                  </p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Últimos pipelines</CardTitle>
          <CardDescription>
            CI/CD completo para cuentas-api: lint, tipos, tests con cobertura y despliegue
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <tr>
                <TH>Workflow</TH>
                <TH>Rama</TH>
                <TH>Commit</TH>
                <TH>Entorno</TH>
                <TH>Estado</TH>
                <TH>Tests</TH>
                <TH>Inicio</TH>
              </tr>
            </THead>
            <TBody>
              {d.runs.map((r) => (
                <TR key={r.id}>
                  <TD>
                    {r.url ? (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline-offset-2 hover:underline"
                      >
                        {r.workflow}
                      </a>
                    ) : (
                      r.workflow
                    )}
                  </TD>
                  <TD className="font-mono text-xs">{r.branch}</TD>
                  <TD className="font-mono text-xs">{r.commit}</TD>
                  <TD>
                    <Badge variant="info">{r.environment}</Badge>
                  </TD>
                  <TD>
                    <Badge variant={STATUS_VARIANT[r.status] ?? 'default'}>
                      {STATUS_LABEL[r.status] ?? r.status}
                    </Badge>
                  </TD>
                  <TD className="text-xs">
                    {r.tests ? `${r.tests.passed} ok · ${r.tests.failed} fallidos` : '—'}
                    {r.coverage != null && (
                      <span className="block text-muted-foreground">cobertura {r.coverage} %</span>
                    )}
                  </TD>
                  <TD className="whitespace-nowrap">{formatDateTime(r.started_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
