import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  errorMessage,
  formatMoney,
  PRODUCT_LABELS,
  Skeleton,
} from '@chaski/shared'
import { ArrowLeftRight, CreditCard, FileWarning, HandCoins, ShoppingBag } from 'lucide-react'
import { Link } from 'react-router'

import { useAccounts, useCards, useMovements } from '../api'
import { MovementItem } from './Movements'

const QUICK = [
  { to: '/transferir', label: 'Transferir', icon: ArrowLeftRight },
  { to: '/pagar', label: 'Pagar', icon: ShoppingBag },
  { to: '/prestamos', label: 'Préstamo', icon: HandCoins },
  { to: '/reclamos', label: 'Reclamos', icon: FileWarning },
]

export function HomePage() {
  const accounts = useAccounts()
  const cards = useCards()
  const main = accounts.data?.find((a) => a.currency === 'PEN') ?? accounts.data?.[0]
  const movements = useMovements(main?.id, { pageSize: 5 })

  return (
    <div className="flex flex-col gap-5">
      <section aria-labelledby="saldos" className="flex flex-col gap-3">
        <h1 id="saldos" className="sr-only">
          Mis cuentas
        </h1>
        {accounts.isPending && <Skeleton className="h-32 rounded-xl" />}
        {accounts.isError && (
          <p className="text-sm text-destructive">{errorMessage(accounts.error)}</p>
        )}
        {accounts.data?.length === 0 && <EmptyState title="Aún no tienes cuentas" />}
        {accounts.data?.map((a) => (
          <div
            key={a.id}
            className="rounded-2xl bg-gradient-to-br from-navy-700 to-navy-900 p-5 text-white shadow-md"
          >
            <p className="text-sm text-navy-100">{PRODUCT_LABELS[a.product] ?? a.product}</p>
            <p className="mt-1 text-3xl font-bold tracking-tight">
              {formatMoney(a.balance, a.currency)}
            </p>
            <p className="mt-3 text-xs text-navy-100">
              Saldo disponible · N.° {a.number}
              {a.status !== 'ACTIVA' && ` · ${a.status}`}
            </p>
          </div>
        ))}
      </section>

      <nav aria-label="Accesos rápidos" className="grid grid-cols-4 gap-2">
        {QUICK.map(({ to, label, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="flex flex-col items-center gap-1.5 rounded-xl bg-card p-3 text-center text-xs font-semibold shadow-sm ring-1 ring-border hover:bg-muted"
          >
            <span className="rounded-full bg-accent p-2 text-accent-foreground">
              <Icon className="size-5" aria-hidden />
            </span>
            {label}
          </Link>
        ))}
      </nav>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Mis tarjetas</CardTitle>
          <Link
            to="/tarjetas"
            className="text-sm font-medium text-secondary underline dark:text-navy-300"
          >
            Gestionar
          </Link>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {cards.isPending && <Skeleton className="h-12" />}
          {cards.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No tienes tarjetas.</p>
          )}
          {cards.data?.map((c) => (
            <div key={c.id} className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm">
                <CreditCard className="size-4 text-muted-foreground" aria-hidden />
                {c.brand} {c.type === 'DEBITO' ? 'Débito' : 'Crédito'} •••• {c.last4}
              </span>
              <Badge variant={c.status === 'ACTIVA' ? 'success' : 'danger'}>
                {c.status === 'ACTIVA' ? 'Activa' : 'Bloqueada'}
              </Badge>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Últimos movimientos</CardTitle>
          <Link
            to="/movimientos"
            className="text-sm font-medium text-secondary underline dark:text-navy-300"
          >
            Ver todos
          </Link>
        </CardHeader>
        <CardContent>
          {movements.isPending && main && <Skeleton className="h-40" />}
          {movements.data?.items.length === 0 && <EmptyState title="Sin movimientos todavía" />}
          <ul className="divide-y">
            {movements.data?.items.map((m) => (
              <MovementItem key={m.id} movement={m} />
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
