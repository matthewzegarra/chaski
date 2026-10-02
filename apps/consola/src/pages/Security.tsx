/** Seguridad y Auditoría (Admin, TI): audit log, denied accesses and Key Vault secret metadata. */
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  errorMessage,
  Field,
  formatDate,
  formatDateTime,
  formatNumber,
  Input,
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
  TR,
  useApi,
} from '@chaski/shared'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { KeyRound, ShieldX } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/Layout'
import type { AuditEntry, SecretsMetadata, SecuritySummary } from '../types'

const SECRET_VARIANT = {
  OK: 'success',
  POR_ROTAR: 'warning',
  VENCIDO: 'danger',
  SIN_EXPIRACION: 'default',
} as const
const SECRET_LABEL = {
  OK: 'Vigente',
  POR_ROTAR: 'Rotar pronto',
  VENCIDO: 'Vencido',
  SIN_EXPIRACION: 'Sin expiración',
}

function AuditTable() {
  const api = useApi()
  const [allowed, setAllowed] = useState('')
  const [pii, setPii] = useState('')
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const q = useQuery({
    queryKey: ['audit', allowed, pii, actor, action, page],
    queryFn: () =>
      api.get<Page<AuditEntry>>('core', '/security/audit', {
        allowed,
        pii_accessed: pii,
        actor,
        action,
        page,
        page_size: 25,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="mb-4 grid gap-3 md:grid-cols-4">
          <Field label="Resultado">
            {(p) => (
              <Select
                {...p}
                value={allowed}
                onChange={(e) => (setAllowed(e.target.value), setPage(1))}
              >
                <option value="">Todos</option>
                <option value="false">Denegados (403)</option>
                <option value="true">Permitidos</option>
              </Select>
            )}
          </Field>
          <Field label="Acceso a PII">
            {(p) => (
              <Select {...p} value={pii} onChange={(e) => (setPii(e.target.value), setPage(1))}>
                <option value="">Todos</option>
                <option value="true">Solo PII revelada</option>
              </Select>
            )}
          </Field>
          <Field label="Usuario">
            {(p) => (
              <Input
                {...p}
                value={actor}
                onChange={(e) => (setActor(e.target.value), setPage(1))}
                placeholder="Ej. marketing"
              />
            )}
          </Field>
          <Field label="Acción">
            {(p) => (
              <Input
                {...p}
                value={action}
                onChange={(e) => (setAction(e.target.value), setPage(1))}
                placeholder="Ej. REVEAL_PII"
              />
            )}
          </Field>
        </div>
        {q.isError && <Alert variant="danger">{errorMessage(q.error)}</Alert>}
        {q.isPending ? (
          <Skeleton className="h-96" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Fecha</TH>
                <TH>Usuario</TH>
                <TH>Rol</TH>
                <TH>Acción</TH>
                <TH>Resultado</TH>
                <TH>Motivo</TH>
              </tr>
            </THead>
            <TBody>
              {q.data?.items.map((e) => (
                <TR key={e.id}>
                  <TD className="whitespace-nowrap">{formatDateTime(e.created_at)}</TD>
                  <TD className="font-mono text-xs">{e.actor_id}</TD>
                  <TD>{e.actor_role ?? '—'}</TD>
                  <TD className="max-w-xs truncate font-mono text-xs" title={e.action}>
                    {e.action}
                  </TD>
                  <TD>
                    <span className="flex flex-wrap gap-1">
                      <Badge variant={e.allowed ? 'success' : 'danger'}>
                        {e.allowed ? 'Permitido' : 'Denegado'}
                      </Badge>
                      {e.pii_accessed && <Badge variant="warning">PII</Badge>}
                    </span>
                  </TD>
                  <TD className="max-w-xs truncate text-xs" title={e.reason ?? ''}>
                    {e.reason ?? ''}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {q.data && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{formatNumber(q.data.total)} eventos</span>
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

function Secrets() {
  const api = useApi()
  const q = useQuery({
    queryKey: ['secrets'],
    queryFn: () => api.get<SecretsMetadata>('core', '/security/secrets-metadata'),
  })
  if (q.isPending) return <Skeleton className="h-72" />
  if (q.isError) return <Alert variant="danger">{errorMessage(q.error)}</Alert>
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" aria-hidden /> Secretos en Key Vault
        </CardTitle>
        <CardDescription>
          Solo metadatos (nombre, versión, fechas): los valores nunca salen de Key Vault.
          {q.data.source === 'mock' && ' Datos simulados: KEY_VAULT_URL no está configurado.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <THead>
            <tr>
              <TH>Secreto</TH>
              <TH>Versión</TH>
              <TH>Actualizado</TH>
              <TH>Expira</TH>
              <TH>Estado</TH>
            </tr>
          </THead>
          <TBody>
            {q.data.secrets.map((s) => (
              <TR key={s.name}>
                <TD className="font-mono text-xs">{s.name}</TD>
                <TD className="font-mono text-xs">{s.version?.slice(0, 8) ?? '—'}</TD>
                <TD>{formatDate(s.updated_on)}</TD>
                <TD>
                  {formatDate(s.expires_on)}
                  {s.days_to_expiry != null && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      (
                      {s.days_to_expiry >= 0
                        ? `en ${s.days_to_expiry} días`
                        : `hace ${-s.days_to_expiry} días`}
                      )
                    </span>
                  )}
                </TD>
                <TD>
                  <Badge variant={SECRET_VARIANT[s.status]}>{SECRET_LABEL[s.status]}</Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function SecurityPage() {
  const api = useApi()
  const summary = useQuery({
    queryKey: ['security-summary'],
    queryFn: () => api.get<SecuritySummary>('core', '/security/summary'),
    refetchInterval: 15_000,
  })
  return (
    <div>
      <PageHeader
        title="Seguridad y Auditoría"
        description="Accesos, revelados de PII y rotación de secretos"
      />
      <section className="mb-4 grid grid-cols-3 gap-3" aria-label="Resumen de seguridad">
        {[
          { label: 'Accesos denegados (24 h)', value: summary.data?.denegados_24h, icon: true },
          { label: 'Revelados de PII (24 h)', value: summary.data?.accesos_pii_24h },
          { label: 'Eventos auditados (24 h)', value: summary.data?.eventos_24h },
        ].map((t) => (
          <Card key={t.label}>
            <CardContent className="pt-4">
              <p className="flex items-center gap-1 text-sm text-muted-foreground">
                {t.icon && <ShieldX className="size-4" aria-hidden />} {t.label}
              </p>
              <p className="mt-1 text-2xl font-bold tabular-nums">
                {t.value != null ? formatNumber(t.value) : '—'}
              </p>
            </CardContent>
          </Card>
        ))}
      </section>
      <Tabs defaultValue="auditoria">
        <TabsList className="mb-4">
          <TabsTrigger value="auditoria">Auditoría</TabsTrigger>
          <TabsTrigger value="secretos">Secretos</TabsTrigger>
        </TabsList>
        <TabsContent value="auditoria">
          <AuditTable />
        </TabsContent>
        <TabsContent value="secretos">
          <Secrets />
        </TabsContent>
      </Tabs>
    </div>
  )
}
