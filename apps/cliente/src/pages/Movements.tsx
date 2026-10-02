import {
  Button,
  Card,
  CardContent,
  cn,
  EmptyState,
  errorMessage,
  Field,
  formatDateTime,
  formatMoney,
  Input,
  type Movement,
  Select,
  Sheet,
  SheetContent,
  Skeleton,
  TX_LABELS,
} from '@chaski/shared'
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useAccounts, useMovements } from '../api'
import { PageTitle, SummaryRow } from '../components/common'

export function MovementItem({
  movement: m,
  onSelect,
}: {
  movement: Movement
  onSelect?: (m: Movement) => void
}) {
  const credit = m.direction === 'CREDITO'
  const Icon = credit ? ArrowDownLeft : ArrowUpRight
  const content = (
    <>
      <span
        className={cn(
          'rounded-full p-2',
          credit ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground',
        )}
      >
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {m.merchant ?? m.description ?? TX_LABELS[m.type]}
        </span>
        <span className="text-xs text-muted-foreground">
          {TX_LABELS[m.type] ?? m.type} · {formatDateTime(m.created_at)}
        </span>
      </span>
      <span
        className={cn('text-sm font-semibold', credit ? 'text-brand-600 dark:text-brand-400' : '')}
      >
        {credit ? '+' : '-'}
        {formatMoney(m.amount, m.currency)}
      </span>
    </>
  )
  return (
    <li>
      {onSelect ? (
        <button
          className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-muted/40"
          onClick={() => onSelect(m)}
        >
          {content}
        </button>
      ) : (
        <div className="flex items-center gap-3 py-2.5">{content}</div>
      )}
    </li>
  )
}

export function MovementsPage() {
  const accounts = useAccounts()
  const [accountId, setAccountId] = useState<string>()
  const [type, setType] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Movement | null>(null)

  useEffect(() => {
    if (!accountId && accounts.data?.[0]) setAccountId(accounts.data[0].id)
  }, [accounts.data, accountId])
  useEffect(() => setPage(1), [accountId, type, from, to])

  const movements = useMovements(accountId, { type, from, to, page, pageSize: 20 })
  const totalPages = movements.data
    ? Math.max(1, Math.ceil(movements.data.total / movements.data.page_size))
    : 1

  return (
    <div>
      <PageTitle title="Movimientos" />
      <Card className="mb-4">
        <CardContent className="grid grid-cols-2 gap-3 pt-4">
          <div className="col-span-2">
            <Field label="Cuenta">
              {(p) => (
                <Select
                  {...p}
                  value={accountId ?? ''}
                  onChange={(e) => setAccountId(e.target.value)}
                >
                  {accounts.data?.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.number} · {a.currency}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Tipo">
              {(p) => (
                <Select {...p} value={type} onChange={(e) => setType(e.target.value)}>
                  <option value="">Todos</option>
                  {Object.entries(TX_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label="Desde">
            {(p) => (
              <Input {...p} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            )}
          </Field>
          <Field label="Hasta">
            {(p) => <Input {...p} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}
          </Field>
        </CardContent>
      </Card>

      {movements.isPending && accountId && <Skeleton className="h-64" />}
      {movements.isError && (
        <p className="text-sm text-destructive">{errorMessage(movements.error)}</p>
      )}
      {movements.data?.items.length === 0 && (
        <EmptyState title="No hay movimientos" description="Prueba cambiando los filtros." />
      )}
      <ul className="divide-y rounded-xl bg-card px-3 ring-1 ring-border">
        {movements.data?.items.map((m) => (
          <MovementItem key={m.id} movement={m} onSelect={setSelected} />
        ))}
      </ul>
      {movements.data && movements.data.total > 0 && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </Button>
          <span className="text-muted-foreground">
            Página {page} de {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Siguiente
          </Button>
        </div>
      )}

      <Sheet open={selected !== null} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent title="Detalle del movimiento" side="bottom" className="mx-auto max-w-md">
          {selected && (
            <dl className="divide-y px-4 py-2">
              <SummaryRow label="Tipo" value={TX_LABELS[selected.type] ?? selected.type} />
              <SummaryRow
                label="Monto"
                value={`${selected.direction === 'CREDITO' ? '+' : '-'}${formatMoney(selected.amount, selected.currency)}`}
              />
              <SummaryRow label="Fecha" value={formatDateTime(selected.created_at)} />
              <SummaryRow label="Canal" value={selected.channel} />
              {selected.merchant && <SummaryRow label="Comercio" value={selected.merchant} />}
              {selected.city && <SummaryRow label="Ciudad" value={selected.city} />}
              {selected.counterparty_account && (
                <SummaryRow label="Cuenta relacionada" value={selected.counterparty_account} />
              )}
              {selected.description && (
                <SummaryRow label="Descripción" value={selected.description} />
              )}
              <SummaryRow label="N.° de operación" value={selected.id.slice(0, 8).toUpperCase()} />
            </dl>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
