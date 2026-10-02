/** Centro de Quejas IA (Atención): AI triage, mandatory review queue and human correction. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CATEGORY_LABELS,
  cn,
  Dialog,
  DialogContent,
  EmptyState,
  errorMessage,
  Field,
  formatDate,
  type Page,
  Select,
  Skeleton,
  toast,
  useApi,
} from '@chaski/shared'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, ShieldAlert } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/Layout'
import type { ComplaintConsole } from '../types'

const CATEGORIES = Object.keys(CATEGORY_LABELS)
const URGENCY_VARIANT = { ALTA: 'danger', MEDIA: 'warning', BAJA: 'default' } as const
const STATUS_LABEL = { NUEVA: 'Nueva', EN_REVISION: 'En revisión', RESUELTA: 'Resuelta' } as const

function DaysLeft({ days, resolved }: { days: number; resolved: boolean }) {
  if (resolved) return <span className="text-xs text-muted-foreground">Resuelta</span>
  const variant = days < 0 ? 'danger' : days <= 3 ? 'warning' : 'default'
  const label = days < 0 ? `Vencida hace ${-days} d. hábiles` : `${days} d. hábiles restantes`
  return <Badge variant={variant}>{label}</Badge>
}

function ComplaintCard({ c, onReview }: { c: ComplaintConsole; onReview: () => void }) {
  return (
    <Card className={cn(c.ai_suspicious && 'border-red-300 dark:border-red-900')}>
      <CardContent className="flex flex-col gap-2 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{c.subject}</span>
          {c.ai_suspicious && (
            <Badge variant="danger">
              <ShieldAlert className="size-3" aria-hidden /> Sospechosa
            </Badge>
          )}
          {c.requires_review && c.status !== 'RESUELTA' && (
            <Badge variant="warning">Revisión obligatoria</Badge>
          )}
          <span className="ml-auto">
            <DaysLeft days={c.business_days_left} resolved={c.status === 'RESUELTA'} />
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          {c.customer_name} · {c.channel} · {formatDate(c.created_at)} · vence{' '}
          {formatDate(c.due_at)} · {STATUS_LABEL[c.status]}
        </p>
        <p className="line-clamp-3 rounded-lg bg-muted/60 p-2 text-sm">{c.body}</p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Bot className="size-4 text-muted-foreground" aria-label="Clasificación IA" />
          {c.ai_category ? (
            <>
              <Badge variant="info">{CATEGORY_LABELS[c.ai_category] ?? c.ai_category}</Badge>
              {c.ai_urgency && (
                <Badge variant={URGENCY_VARIANT[c.ai_urgency]}>
                  Urgencia {c.ai_urgency.toLowerCase()}
                </Badge>
              )}
              {c.ai_confidence != null && (
                <span
                  className={cn(
                    'tabular-nums',
                    c.ai_confidence < 0.8 && 'font-semibold text-warning',
                  )}
                >
                  Confianza {Math.round(c.ai_confidence * 100)} %
                </span>
              )}
            </>
          ) : (
            <span className="text-muted-foreground">
              Sin clasificación IA (servicio no disponible)
            </span>
          )}
        </div>
        {c.ai_reason && <p className="text-xs text-muted-foreground">Motivo IA: {c.ai_reason}</p>}
        <div className="flex items-center justify-between gap-2">
          {c.final_category ? (
            <p className="text-xs">
              Categoría final:{' '}
              <strong>{CATEGORY_LABELS[c.final_category] ?? c.final_category}</strong>
              {c.final_category !== c.ai_category && c.ai_category && ' (corregida por humano)'}
              {c.reviewed_by && ` · ${c.reviewed_by}`}
            </p>
          ) : (
            <span />
          )}
          {c.status !== 'RESUELTA' && (
            <Button size="sm" onClick={onReview}>
              Revisar
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function ComplaintsPage() {
  const api = useApi()
  const qc = useQueryClient()
  const [view, setView] = useState<'review' | 'open' | 'resolved' | 'suspicious'>('review')
  const [page, setPage] = useState(1)
  const [target, setTarget] = useState<ComplaintConsole | null>(null)
  const [category, setCategory] = useState('OTRO')
  const [status, setStatus] = useState<'EN_REVISION' | 'RESUELTA'>('RESUELTA')

  const filters = {
    review: { requires_review: true, status: '' },
    open: { status: 'NUEVA' },
    resolved: { status: 'RESUELTA' },
    suspicious: { suspicious: true },
  }[view]
  const list = useQuery({
    queryKey: ['complaints', view, page],
    queryFn: () =>
      api.get<Page<ComplaintConsole>>('core', '/complaints', { ...filters, page, page_size: 20 }),
    placeholderData: keepPreviousData,
  })
  const review = useMutation({
    mutationFn: () =>
      api.post('core', `/complaints/${target!.id}/review`, { final_category: category, status }),
    onSuccess: () => {
      toast.success(
        category !== target?.ai_category && target?.ai_category
          ? 'Etiqueta corregida: la corrección alimenta la métrica de precisión de la IA.'
          : 'Revisión registrada.',
      )
      setTarget(null)
      void qc.invalidateQueries({ queryKey: ['complaints'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  function open(c: ComplaintConsole) {
    setCategory(c.final_category ?? c.ai_category ?? 'OTRO')
    setStatus('RESUELTA')
    setTarget(c)
  }

  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1
  return (
    <div>
      <PageHeader
        title="Centro de Quejas IA"
        description="La IA clasifica; FRAUDE, confianza < 80 % o texto sospechoso pasan por revisión humana. Plazo: 15 días hábiles."
        actions={
          <>
            <label htmlFor="c-view" className="sr-only">
              Bandeja
            </label>
            <Select
              id="c-view"
              className="h-9 w-56"
              value={view}
              onChange={(e) => (setView(e.target.value as typeof view), setPage(1))}
            >
              <option value="review">Cola de revisión obligatoria</option>
              <option value="open">Nuevas</option>
              <option value="suspicious">Sospechosas</option>
              <option value="resolved">Resueltas</option>
            </Select>
          </>
        }
      />
      {list.isError && <Alert variant="danger">{errorMessage(list.error)}</Alert>}
      {list.isPending ? (
        <Skeleton className="h-96" />
      ) : list.data?.items.length === 0 ? (
        <EmptyState title="Bandeja vacía" description="No hay quejas en esta vista." />
      ) : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">{list.data?.total} quejas</p>
          <div className="grid gap-3 xl:grid-cols-2">
            {list.data?.items.map((c) => (
              <ComplaintCard key={c.id} c={c} onReview={() => open(c)} />
            ))}
          </div>
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
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
        </>
      )}
      <Dialog open={target !== null} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent
          title="Revisar queja"
          description={
            target
              ? `${target.subject} · sugerencia IA: ${target.ai_category ? CATEGORY_LABELS[target.ai_category] : 'ninguna'}`
              : undefined
          }
        >
          <Field label="Categoría final">
            {(p) => (
              <Select {...p} value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((k) => (
                  <option key={k} value={k}>
                    {CATEGORY_LABELS[k]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Estado">
            {(p) => (
              <Select
                {...p}
                value={status}
                onChange={(e) => setStatus(e.target.value as typeof status)}
              >
                <option value="RESUELTA">Resuelta</option>
                <option value="EN_REVISION">En revisión</option>
              </Select>
            )}
          </Field>
          <Button loading={review.isPending} onClick={() => review.mutate()}>
            Guardar revisión
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
