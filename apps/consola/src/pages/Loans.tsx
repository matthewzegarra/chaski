/** Préstamos (Riesgos). The AI score is a suggestion; the decision is always this user's. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  EmptyState,
  errorMessage,
  Field,
  formatDate,
  formatMoney,
  formatPercent,
  type Page,
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
  Textarea,
  toast,
  TR,
  useApi,
} from '@chaski/shared'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/Layout'
import type { LoanConsole } from '../types'

const REGIONS = [
  'Lima',
  'Arequipa',
  'La Libertad',
  'Piura',
  'Cusco',
  'Junín',
  'Lambayeque',
  'Loreto',
]
const BUCKET_VARIANT: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  Normal: 'success',
  CPP: 'info',
  Deficiente: 'warning',
  Dudoso: 'danger',
  Pérdida: 'danger',
}

function scoreVariant(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 650) return 'success'
  if (score >= 500) return 'warning'
  return 'danger'
}

function ApplicationCard({
  loan,
  onDecide,
}: {
  loan: LoanConsole
  onDecide: (d: 'APROBADO' | 'RECHAZADO') => void
}) {
  const api = useApi()
  const qc = useQueryClient()
  const rescore = useMutation({
    mutationFn: () => api.post<LoanConsole>('core', `/loans/${loan.id}/rescore`),
    onSuccess: (l) => {
      if (l.ai_score == null) toast.info('El servicio de IA no está disponible todavía.')
      void qc.invalidateQueries({ queryKey: ['loans'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const ratio = loan.monthly_income ? (loan.monthly_payment / loan.monthly_income) * 100 : null
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">{loan.customer_name}</p>
            <p className="text-xs text-muted-foreground">
              {loan.segment} · {loan.region} · {formatDate(loan.created_at)}
            </p>
          </div>
          <p className="text-right">
            <span className="block text-lg font-bold tabular-nums">{formatMoney(loan.amount)}</span>
            <span className="text-xs text-muted-foreground">
              {loan.term_months} meses · TEA {formatPercent(loan.rate_tea * 100, 2)}
            </span>
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-2 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Cuota</dt>
            <dd className="font-medium tabular-nums">{formatMoney(loan.monthly_payment)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Ingreso</dt>
            <dd className="font-medium tabular-nums">
              {loan.monthly_income != null ? formatMoney(loan.monthly_income) : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Cuota / ingreso</dt>
            <dd className={`font-medium ${ratio != null && ratio > 40 ? 'text-destructive' : ''}`}>
              {ratio != null ? formatPercent(ratio) : '—'}
            </dd>
          </div>
        </dl>
        <div className="rounded-lg bg-muted/60 p-3 text-sm">
          <div className="mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1 font-semibold">
              <Bot className="size-4" aria-hidden /> Sugerencia de la IA
            </span>
            {loan.ai_score != null ? (
              <Badge variant={scoreVariant(loan.ai_score)}>Score {loan.ai_score}</Badge>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => rescore.mutate()}
                loading={rescore.isPending}
              >
                <RefreshCw /> Calcular score
              </Button>
            )}
          </div>
          <p className="text-muted-foreground">
            {loan.ai_explanation || 'Aún no hay explicación de la IA para esta solicitud.'}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={() => onDecide('RECHAZADO')}>
            Rechazar
          </Button>
          <Button onClick={() => onDecide('APROBADO')}>Aprobar y desembolsar</Button>
        </div>
      </CardContent>
    </Card>
  )
}

function Applications() {
  const api = useApi()
  const qc = useQueryClient()
  const [target, setTarget] = useState<{
    loan: LoanConsole
    decision: 'APROBADO' | 'RECHAZADO'
  } | null>(null)
  const [comment, setComment] = useState('')
  const list = useQuery({
    queryKey: ['loans', 'SOLICITADO'],
    queryFn: () =>
      api.get<Page<LoanConsole>>('core', '/loans', { status: 'SOLICITADO', page_size: 50 }),
  })
  const decide = useMutation({
    mutationFn: () =>
      api.post<LoanConsole>('core', `/loans/${target!.loan.id}/decision`, {
        decision: target!.decision,
        comment: comment.trim() || undefined,
      }),
    onSuccess: (l) => {
      toast.success(
        l.status === 'DESEMBOLSADO' ? 'Préstamo aprobado y desembolsado.' : 'Solicitud rechazada.',
      )
      setTarget(null)
      setComment('')
      void qc.invalidateQueries({ queryKey: ['loans'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  if (list.isPending) return <Skeleton className="h-96" />
  if (list.isError) return <Alert variant="danger">{errorMessage(list.error)}</Alert>
  if (list.data.items.length === 0) return <EmptyState title="No hay solicitudes por evaluar" />
  return (
    <>
      <p className="mb-3 text-sm text-muted-foreground">
        {list.data.total} solicitudes en evaluación
      </p>
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {list.data.items.map((l) => (
          <ApplicationCard
            key={l.id}
            loan={l}
            onDecide={(decision) => setTarget({ loan: l, decision })}
          />
        ))}
      </div>
      <Dialog open={target !== null} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent
          title={target?.decision === 'APROBADO' ? 'Aprobar préstamo' : 'Rechazar préstamo'}
          description={
            target
              ? `${target.loan.customer_name} · ${formatMoney(target.loan.amount)} a ${target.loan.term_months} meses. La decisión queda registrada con tu usuario.`
              : undefined
          }
        >
          <Field label="Comentario">
            {(p) => (
              <Textarea
                {...p}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                maxLength={500}
                placeholder="Sustento de la decisión"
              />
            )}
          </Field>
          <Button
            variant={target?.decision === 'RECHAZADO' ? 'destructive' : 'default'}
            loading={decide.isPending}
            onClick={() => decide.mutate()}
          >
            Confirmar
          </Button>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Portfolio() {
  const api = useApi()
  const [region, setRegion] = useState('')
  const [minDpd, setMinDpd] = useState('0')
  const [page, setPage] = useState(1)
  const list = useQuery({
    queryKey: ['loans', 'portfolio', region, minDpd, page],
    queryFn: () =>
      api.get<Page<LoanConsole>>('core', '/loans', {
        status: 'DESEMBOLSADO',
        region,
        min_days_past_due: minDpd,
        page,
        page_size: 25,
      }),
    placeholderData: keepPreviousData,
  })
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="mb-4 grid gap-3 sm:grid-cols-[200px_200px]">
          <Field label="Región">
            {(p) => (
              <Select
                {...p}
                value={region}
                onChange={(e) => (setRegion(e.target.value), setPage(1))}
              >
                <option value="">Todas</option>
                {REGIONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Días de atraso">
            {(p) => (
              <Select
                {...p}
                value={minDpd}
                onChange={(e) => (setMinDpd(e.target.value), setPage(1))}
              >
                <option value="0">Toda la cartera</option>
                <option value="1">Con atraso (≥ 1)</option>
                <option value="31">Vencida (&gt; 30)</option>
                <option value="121">Pérdida (&gt; 120)</option>
              </Select>
            )}
          </Field>
        </div>
        {list.isPending ? (
          <Skeleton className="h-96" />
        ) : list.data?.items.length === 0 ? (
          <EmptyState title="Sin préstamos con ese filtro" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Cliente</TH>
                <TH>Región</TH>
                <TH className="text-right">Monto</TH>
                <TH className="text-right">Saldo</TH>
                <TH className="text-right">Días de atraso</TH>
                <TH>Bucket</TH>
              </tr>
            </THead>
            <TBody>
              {list.data?.items.map((l) => (
                <TR key={l.id}>
                  <TD className="font-medium">{l.customer_name}</TD>
                  <TD>{l.region}</TD>
                  <TD className="text-right tabular-nums">{formatMoney(l.amount)}</TD>
                  <TD className="text-right tabular-nums">{formatMoney(l.outstanding_balance)}</TD>
                  <TD className="text-right tabular-nums">{l.days_past_due}</TD>
                  <TD>
                    <Badge variant={BUCKET_VARIANT[l.bucket] ?? 'default'}>{l.bucket}</Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {list.data && list.data.total > 0 && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{list.data.total} préstamos</span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Anterior
              </Button>
              <span>
                {page} / {pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Siguiente
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function LoansPage() {
  return (
    <div>
      <PageHeader
        title="Préstamos"
        description="La IA sugiere un score; la decisión final siempre es de Riesgos."
      />
      <Tabs defaultValue="solicitudes">
        <TabsList className="mb-4">
          <TabsTrigger value="solicitudes">Solicitudes</TabsTrigger>
          <TabsTrigger value="cartera">Cartera</TabsTrigger>
        </TabsList>
        <TabsContent value="solicitudes">
          <Applications />
        </TabsContent>
        <TabsContent value="cartera">
          <Portfolio />
        </TabsContent>
      </Tabs>
    </div>
  )
}
