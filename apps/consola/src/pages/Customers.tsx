/** Clientes y KYC: masked customer table, detail, audited PII reveal and the onboarding inbox. */
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
  Input,
  type Page,
  PRODUCT_LABELS,
  Select,
  Sheet,
  SheetContent,
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
import { CheckCircle2, CircleAlert, CircleHelp, Eye, EyeOff, Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { PageHeader } from '../components/Layout'
import { useRole } from '../session'
import type { CustomerDetail, CustomerMasked, PendingOnboarding, RevealedPii } from '../types'

const KYC_VARIANT = { APROBADO: 'success', PENDIENTE: 'warning', RECHAZADO: 'danger' } as const
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
const CHECK_LABELS: Record<string, string> = {
  dni_coincide: 'DNI',
  nombres_coinciden: 'Nombres',
  fecha_nacimiento_coincide: 'Nacimiento',
  consulta_nombres_coinciden: 'Consulta vs datos',
  consulta_ocr_coinciden: 'Consulta vs DNI',
}

function CheckBadge({ label, value }: { label: string; value: boolean | null }) {
  if (value === true)
    return (
      <Badge variant="success">
        <CheckCircle2 className="size-3" aria-hidden /> {label} coincide
      </Badge>
    )
  if (value === false)
    return (
      <Badge variant="danger">
        <CircleAlert className="size-3" aria-hidden /> {label} no coincide
      </Badge>
    )
  return (
    <Badge>
      <CircleHelp className="size-3" aria-hidden /> {label} sin leer
    </Badge>
  )
}

// ------------------------------------------------------------------ PII reveal

function RevealPii({ customerId }: { customerId: string }) {
  const api = useApi()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [data, setData] = useState<RevealedPii | null>(null)
  const reveal = useMutation({
    mutationFn: () =>
      api.post<RevealedPii>('core', `/customers/${customerId}/reveal-pii`, {
        reason: reason.trim(),
      }),
    onSuccess: (d) => {
      setData(d)
      setOpen(false)
      setReason('')
      toast.success('Datos revelados. El acceso quedó registrado en auditoría.')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  if (data) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950">
        <div className="mb-2 flex items-center justify-between">
          <p className="font-semibold">Datos completos (acceso auditado)</p>
          <Button size="sm" variant="ghost" onClick={() => setData(null)}>
            <EyeOff /> Ocultar
          </Button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">DNI</dt>
          <dd>{data.document_number}</dd>
          <dt className="text-muted-foreground">Correo</dt>
          <dd>{data.email}</dd>
          <dt className="text-muted-foreground">Celular</dt>
          <dd>{data.phone ?? '—'}</dd>
          <dt className="text-muted-foreground">Nacimiento</dt>
          <dd>{formatDate(data.birth_date)}</dd>
        </dl>
      </div>
    )
  }
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Eye /> Revelar PII
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Revelar datos personales"
          description="Indica el motivo. El acceso quedará registrado con tu usuario en la auditoría."
        >
          <form
            className="flex flex-col gap-3"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              reveal.mutate()
            }}
          >
            <Field label="Motivo" hint="Mínimo 10 caracteres">
              {(p) => (
                <Textarea
                  {...p}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={300}
                  placeholder="Ej. El cliente llamó para validar su identidad (ticket #1234)"
                />
              )}
            </Field>
            <Button type="submit" disabled={reason.trim().length < 10} loading={reveal.isPending}>
              Revelar
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ------------------------------------------------------------------ detail

function CustomerSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const api = useApi()
  const { activeRole } = useRole()
  const detail = useQuery({
    queryKey: ['customer', id],
    queryFn: () => api.get<CustomerDetail>('core', `/customers/${id}`),
    enabled: Boolean(id),
  })
  const c = detail.data
  return (
    <Sheet open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent title="Detalle del cliente">
        <div className="flex flex-col gap-4 p-4">
          {detail.isPending && <Skeleton className="h-64" />}
          {detail.isError && <Alert variant="danger">{errorMessage(detail.error)}</Alert>}
          {c && (
            <>
              <div>
                <p className="text-lg font-bold">
                  {c.first_name} {c.last_name}
                </p>
                <p className="text-sm text-muted-foreground">
                  {c.segment} · {c.region} · Riesgo {c.risk_level.toLowerCase()}
                </p>
                <Badge variant={KYC_VARIANT[c.kyc_status]} className="mt-1">
                  KYC {c.kyc_status.toLowerCase()}
                </Badge>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">DNI</dt>
                <dd>{c.document_number}</dd>
                <dt className="text-muted-foreground">Correo</dt>
                <dd>{c.email}</dd>
                <dt className="text-muted-foreground">Celular</dt>
                <dd>{c.phone ?? '—'}</dd>
                <dt className="text-muted-foreground">Ingreso</dt>
                <dd>{c.monthly_income != null ? formatMoney(c.monthly_income) : '—'}</dd>
                <dt className="text-muted-foreground">Cliente desde</dt>
                <dd>{formatDate(c.created_at)}</dd>
              </dl>
              {(activeRole === 'Atencion' || activeRole === 'Admin') && (
                <RevealPii customerId={c.id} />
              )}
              <section>
                <h3 className="mb-1 text-sm font-semibold">Cuentas</h3>
                {c.accounts.length === 0 && (
                  <p className="text-sm text-muted-foreground">Sin cuentas</p>
                )}
                <ul className="divide-y text-sm">
                  {c.accounts.map((a) => (
                    <li key={a.id} className="flex justify-between py-1.5">
                      <span>
                        {PRODUCT_LABELS[a.product] ?? a.product}
                        <span className="block text-xs text-muted-foreground">{a.number}</span>
                      </span>
                      <span className="font-medium tabular-nums">
                        {formatMoney(a.balance, a.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-1 text-sm font-semibold">Tarjetas</h3>
                <ul className="flex flex-wrap gap-2">
                  {c.cards.map((k) => (
                    <li key={k.id}>
                      <Badge variant={k.status === 'ACTIVA' ? 'info' : 'danger'}>
                        {k.brand} {k.type.toLowerCase()} •••• {k.last4}
                      </Badge>
                    </li>
                  ))}
                  {c.cards.length === 0 && (
                    <p className="text-sm text-muted-foreground">Sin tarjetas</p>
                  )}
                </ul>
              </section>
              <section>
                <h3 className="mb-1 text-sm font-semibold">Préstamos</h3>
                {c.loans.length === 0 && (
                  <p className="text-sm text-muted-foreground">Sin préstamos</p>
                )}
                <ul className="divide-y text-sm">
                  {c.loans.map((l) => (
                    <li key={l.id} className="flex justify-between py-1.5">
                      <span>
                        {formatMoney(l.amount)} · {l.status.toLowerCase()}
                      </span>
                      {l.days_past_due > 0 && (
                        <Badge variant="warning">{l.days_past_due} días de atraso</Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
              <p className="text-sm text-muted-foreground">Quejas abiertas: {c.open_complaints}</p>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

// ------------------------------------------------------------------ list

function CustomerTable() {
  const api = useApi()
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [kyc, setKyc] = useState('')
  const [region, setRegion] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const list = useQuery({
    queryKey: ['customers', query, kyc, region, page],
    queryFn: () =>
      api.get<Page<CustomerMasked>>('core', '/customers', {
        q: query,
        kyc_status: kyc,
        region,
        page,
        page_size: 20,
      }),
    placeholderData: keepPreviousData,
  })
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1

  return (
    <Card>
      <CardContent className="pt-4">
        <form
          className="mb-4 grid gap-3 md:grid-cols-[1fr_180px_180px_auto]"
          onSubmit={(e) => {
            e.preventDefault()
            setPage(1)
            setQuery(q.trim())
          }}
        >
          <Field label="Buscar por nombre o DNI completo">
            {(p) => (
              <Input
                {...p}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ej. Quispe o 45678912"
              />
            )}
          </Field>
          <Field label="KYC">
            {(p) => (
              <Select {...p} value={kyc} onChange={(e) => (setKyc(e.target.value), setPage(1))}>
                <option value="">Todos</option>
                <option value="APROBADO">Aprobado</option>
                <option value="PENDIENTE">Pendiente</option>
                <option value="RECHAZADO">Rechazado</option>
              </Select>
            )}
          </Field>
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
          <Button type="submit" className="self-end">
            <Search /> Buscar
          </Button>
        </form>
        {list.isError && <Alert variant="danger">{errorMessage(list.error)}</Alert>}
        {list.isPending ? (
          <Skeleton className="h-96" />
        ) : list.data?.items.length === 0 ? (
          <EmptyState title="Sin resultados" description="Prueba con otro nombre o filtro." />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Cliente</TH>
                <TH>DNI</TH>
                <TH>Correo</TH>
                <TH>Celular</TH>
                <TH>Segmento</TH>
                <TH>Región</TH>
                <TH>KYC</TH>
              </tr>
            </THead>
            <TBody>
              {list.data?.items.map((c) => (
                <TR key={c.id}>
                  <TD>
                    <button
                      className="text-left font-medium text-secondary underline-offset-2 hover:underline dark:text-navy-300"
                      onClick={() => setSelected(c.id)}
                    >
                      {c.first_name} {c.last_name}
                    </button>
                  </TD>
                  <TD className="font-mono text-xs">{c.document_number}</TD>
                  <TD className="text-xs">{c.email}</TD>
                  <TD className="font-mono text-xs">{c.phone}</TD>
                  <TD>{c.segment}</TD>
                  <TD>{c.region}</TD>
                  <TD>
                    <Badge variant={KYC_VARIANT[c.kyc_status]}>{c.kyc_status.toLowerCase()}</Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {list.data && list.data.total > 0 && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{list.data.total} clientes</span>
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
      <CustomerSheet id={selected} onClose={() => setSelected(null)} />
    </Card>
  )
}

// ------------------------------------------------------------------ onboarding inbox

function OnboardingInbox() {
  const api = useApi()
  const qc = useQueryClient()
  const [decision, setDecision] = useState<{
    item: PendingOnboarding
    value: 'APROBADO' | 'RECHAZADO'
  } | null>(null)
  const [reason, setReason] = useState('')
  const inbox = useQuery({
    queryKey: ['onboarding-pending'],
    queryFn: () => api.get<PendingOnboarding[]>('core', '/onboarding/pending'),
  })
  const decide = useMutation({
    mutationFn: () =>
      api.post('core', `/onboarding/${decision!.item.customer.id}/decision`, {
        decision: decision!.value,
        reason: reason.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success(
        decision!.value === 'APROBADO'
          ? 'Cliente aprobado: se abrió su cuenta y tarjeta.'
          : 'Solicitud rechazada.',
      )
      setDecision(null)
      setReason('')
      void qc.invalidateQueries({ queryKey: ['onboarding-pending'] })
      void qc.invalidateQueries({ queryKey: ['customers'] })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  if (inbox.isPending) return <Skeleton className="h-96" />
  if (inbox.isError) return <Alert variant="danger">{errorMessage(inbox.error)}</Alert>
  if (inbox.data.length === 0)
    return <EmptyState title="Bandeja vacía" description="No hay solicitudes pendientes." />

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {inbox.data.map((item) => {
        const c = item.customer
        const mismatch = Object.values(item.checks).includes(false)
        return (
          <Card key={c.id} className={mismatch ? 'border-red-300 dark:border-red-900' : undefined}>
            <CardContent className="flex flex-col gap-3 pt-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold">
                    {c.first_name} {c.last_name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    DNI {c.document_number} · {c.region} · solicitado {formatDate(c.created_at)}
                  </p>
                </div>
                {item.confidence != null && (
                  <Badge variant={item.confidence >= 0.85 ? 'success' : 'warning'}>
                    Confianza {Math.round(item.confidence * 100)} %
                  </Badge>
                )}
              </div>
              {item.extracted ? (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 rounded-lg bg-muted/60 p-3 text-sm">
                  {Object.entries(item.extracted)
                    .filter(([key]) => key !== 'modelo')
                    .map(([key, v]) => (
                      <div key={key} className="contents">
                        <dt className="capitalize text-muted-foreground">
                          {key.replace(/_/g, ' ')}
                        </dt>
                        <dd className="font-medium">{v}</dd>
                      </div>
                    ))}
                </dl>
              ) : (
                <Alert variant="info">La IA no pudo leer el DNI: valida la foto manualmente.</Alert>
              )}
              {item.lookup && (
                <p className="text-xs text-muted-foreground">
                  Consulta de identidad ({item.lookup.fuente}): {item.lookup.nombres}{' '}
                  {item.lookup.apellidos}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(item.checks).map(([key, v]) => (
                  <CheckBadge key={key} label={CHECK_LABELS[key] ?? key} value={v} />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" onClick={() => setDecision({ item, value: 'RECHAZADO' })}>
                  Rechazar
                </Button>
                <Button onClick={() => setDecision({ item, value: 'APROBADO' })}>Aprobar</Button>
              </div>
            </CardContent>
          </Card>
        )
      })}
      <Dialog open={decision !== null} onOpenChange={(o) => !o && setDecision(null)}>
        <DialogContent
          title={decision?.value === 'APROBADO' ? 'Aprobar onboarding' : 'Rechazar onboarding'}
          description={
            decision?.value === 'APROBADO'
              ? 'Se abrirá una cuenta de ahorros en soles y una tarjeta de débito.'
              : 'El cliente verá que su solicitud no fue aprobada.'
          }
        >
          <Field
            label={
              decision?.value === 'RECHAZADO' ? 'Motivo (obligatorio)' : 'Comentario (opcional)'
            }
          >
            {(p) => (
              <Textarea
                {...p}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
              />
            )}
          </Field>
          <Button
            variant={decision?.value === 'RECHAZADO' ? 'destructive' : 'default'}
            loading={decide.isPending}
            disabled={decision?.value === 'RECHAZADO' && reason.trim().length < 5}
            onClick={() => decide.mutate()}
          >
            Confirmar
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function CustomersPage() {
  const api = useApi()
  const pending = useQuery({
    queryKey: ['onboarding-pending'],
    queryFn: () => api.get<PendingOnboarding[]>('core', '/onboarding/pending'),
  })
  return (
    <div>
      <PageHeader
        title="Clientes y KYC"
        description="Los datos personales se muestran enmascarados. Revelarlos requiere un motivo y queda auditado."
      />
      <Tabs defaultValue="clientes">
        <TabsList className="mb-4">
          <TabsTrigger value="clientes">Clientes</TabsTrigger>
          <TabsTrigger value="onboarding">
            Bandeja de onboarding
            {pending.data && pending.data.length > 0 && (
              <Badge variant="warning" className="ml-2">
                {pending.data.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="clientes">
          <CustomerTable />
        </TabsContent>
        <TabsContent value="onboarding">
          <OnboardingInbox />
        </TabsContent>
      </Tabs>
    </div>
  )
}
