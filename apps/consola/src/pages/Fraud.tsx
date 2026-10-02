/** Chaski Guard: live fraud alerts (5 s refresh), confirm/dismiss and card blocking. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  cn,
  Dialog,
  DialogContent,
  EmptyState,
  errorMessage,
  formatMoney,
  formatRelative,
  Select,
  Skeleton,
  toast,
  TX_LABELS,
  useApi,
} from '@chaski/shared'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { PageHeader } from '../components/Layout'
import type { FraudAlert } from '../types'

const REFRESH_MS = 5_000
const RULE_LABELS: Record<string, string> = {
  R1_VELOCIDAD: 'R1 · Muchas transferencias seguidas',
  R2_MONTO_ATIPICO: 'R2 · Monto atípico',
  R3_CIUDAD_DISTINTA: 'R3 · Ciudad distinta',
  R4_BENEFICIARIO_NUEVO: 'R4 · Beneficiario nuevo > S/ 5,000',
}
const STATUS_VARIANT = { ABIERTA: 'danger', CONFIRMADA: 'warning', DESCARTADA: 'default' } as const

function AlertCard({
  alert,
  isNew,
  onResolve,
}: {
  alert: FraudAlert
  isNew: boolean
  onResolve: (a: FraudAlert) => void
}) {
  const description =
    typeof alert.details?.descripcion === 'string' ? alert.details.descripcion : null
  return (
    <Card
      className={cn(
        alert.status === 'ABIERTA' && 'border-red-300 dark:border-red-900',
        isNew && 'ring-2 ring-red-400',
      )}
    >
      <CardContent className="flex flex-col gap-2 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <ShieldAlert className="size-4 text-destructive" aria-hidden />
          <span className="font-semibold">{RULE_LABELS[alert.rule] ?? alert.rule}</span>
          <Badge variant={alert.source === 'FABRIC' ? 'info' : 'default'}>{alert.source}</Badge>
          <Badge variant={STATUS_VARIANT[alert.status]}>{alert.status.toLowerCase()}</Badge>
          {isNew && <Badge variant="danger">Nueva</Badge>}
          <span className="ml-auto text-xs text-muted-foreground">
            {formatRelative(alert.created_at)}
          </span>
        </div>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Cliente</dt>
            <dd className="font-medium">{alert.customer_name ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Operación</dt>
            <dd>{alert.tx_type ? (TX_LABELS[alert.tx_type] ?? alert.tx_type) : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Monto</dt>
            <dd className="font-medium tabular-nums">
              {alert.tx_amount != null
                ? formatMoney(alert.tx_amount, alert.tx_currency ?? 'PEN')
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Score</dt>
            <dd className="font-medium tabular-nums">{alert.score.toFixed(0)} / 100</dd>
          </div>
          {(alert.merchant || alert.city) && (
            <div className="col-span-2">
              <dt className="text-xs text-muted-foreground">Comercio / ciudad</dt>
              <dd>{[alert.merchant, alert.city].filter(Boolean).join(' · ')}</dd>
            </div>
          )}
          {alert.card_last4 && (
            <div className="col-span-2">
              <dt className="text-xs text-muted-foreground">Tarjeta</dt>
              <dd className="flex items-center gap-1">
                <CreditCard className="size-3.5" aria-hidden /> •••• {alert.card_last4} ·{' '}
                {alert.card_status?.toLowerCase()}
              </dd>
            </div>
          )}
        </dl>
        {alert.status === 'ABIERTA' ? (
          <div className="flex justify-end">
            <Button size="sm" onClick={() => onResolve(alert)}>
              Resolver
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Resuelta por {alert.resolved_by}{' '}
            {alert.resolved_at && formatRelative(alert.resolved_at)}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function FraudPage() {
  const api = useApi()
  const qc = useQueryClient()
  const [status, setStatus] = useState('ABIERTA')
  const [source, setSource] = useState('')
  const [target, setTarget] = useState<FraudAlert | null>(null)
  const [blockCard, setBlockCard] = useState(true)
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())

  const alerts = useQuery({
    queryKey: ['fraud-alerts', status, source],
    queryFn: () => api.get<FraudAlert[]>('core', '/fraud/alerts', { status, source, limit: 100 }),
    refetchInterval: REFRESH_MS,
    // A live monitor: keep polling even when the tab is in the background.
    refetchIntervalInBackground: true,
  })

  // Highlight alerts that arrived after the first load (e.g. the demo fraud burst).
  useEffect(() => {
    if (!alerts.data) return
    const ids = alerts.data.map((a) => a.id)
    if (seen.current === null) {
      seen.current = new Set(ids)
      return
    }
    const arrived = ids.filter((id) => !seen.current!.has(id))
    if (arrived.length) {
      arrived.forEach((id) => seen.current!.add(id))
      setFresh((prev) => new Set([...prev, ...arrived]))
      toast.warning(`${arrived.length} alerta(s) nueva(s) de fraude`)
    }
  }, [alerts.data])

  const resolve = useMutation({
    mutationFn: (decision: 'CONFIRMADA' | 'DESCARTADA') =>
      api.post<{ card_blocked: boolean }>('core', `/fraud/alerts/${target!.id}/resolve`, {
        status: decision,
        block_card: decision === 'CONFIRMADA' && blockCard,
      }),
    onSuccess: (r, decision) => {
      toast.success(
        decision === 'CONFIRMADA'
          ? `Fraude confirmado${r.card_blocked ? ' y tarjeta bloqueada' : ''}.`
          : 'Alerta descartada.',
      )
      setTarget(null)
      void qc.invalidateQueries({ queryKey: ['fraud-alerts'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  return (
    <div>
      <PageHeader
        title="Chaski Guard"
        description="Alertas del motor de reglas (RULES) y de Fabric (FABRIC). Se actualiza cada 5 s."
        actions={
          <div className="flex gap-2">
            <label htmlFor="f-status" className="sr-only">
              Estado
            </label>
            <Select
              id="f-status"
              className="h-9 w-40"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="ABIERTA">Abiertas</option>
              <option value="CONFIRMADA">Confirmadas</option>
              <option value="DESCARTADA">Descartadas</option>
              <option value="">Todas</option>
            </Select>
            <label htmlFor="f-source" className="sr-only">
              Fuente
            </label>
            <Select
              id="f-source"
              className="h-9 w-36"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">Toda fuente</option>
              <option value="RULES">RULES</option>
              <option value="FABRIC">FABRIC</option>
            </Select>
          </div>
        }
      />
      {alerts.isError && <Alert variant="danger">{errorMessage(alerts.error)}</Alert>}
      {alerts.isPending ? (
        <Skeleton className="h-96" />
      ) : alerts.data?.length === 0 ? (
        <EmptyState title="Sin alertas" description="No hay alertas con ese filtro." />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2" aria-live="polite">
          {alerts.data?.map((a) => (
            <AlertCard key={a.id} alert={a} isNew={fresh.has(a.id)} onResolve={setTarget} />
          ))}
        </div>
      )}
      <Dialog open={target !== null} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent
          title="Resolver alerta"
          description={
            target
              ? `${RULE_LABELS[target.rule] ?? target.rule} · ${target.customer_name ?? 'cliente desconocido'}`
              : undefined
          }
        >
          {target?.card_id && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={blockCard}
                onChange={(e) => setBlockCard(e.target.checked)}
                className="size-4 accent-[var(--primary)]"
              />
              Bloquear la tarjeta •••• {target.card_last4} al confirmar
            </label>
          )}
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              loading={resolve.isPending}
              onClick={() => resolve.mutate('DESCARTADA')}
            >
              Descartar
            </Button>
            <Button
              variant="destructive"
              loading={resolve.isPending}
              onClick={() => resolve.mutate('CONFIRMADA')}
            >
              Confirmar fraude
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
