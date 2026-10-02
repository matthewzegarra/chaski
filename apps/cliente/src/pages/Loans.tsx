import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  errorMessage,
  Field,
  formatDate,
  formatMoney,
  type Loan,
  Select,
  Skeleton,
  toast,
} from '@chaski/shared'
import { Check } from 'lucide-react'
import { useState } from 'react'

import { useLoanQuote, useLoans, useRequestLoan } from '../api'
import { ConfirmDialog, PageTitle, SummaryRow } from '../components/common'

const TERMS = [6, 12, 18, 24, 36, 48, 60]
const STATUS: Record<
  Loan['status'],
  { label: string; variant: 'info' | 'success' | 'danger' | 'default' | 'warning' }
> = {
  SOLICITADO: { label: 'En evaluación', variant: 'warning' },
  APROBADO: { label: 'Aprobado', variant: 'success' },
  DESEMBOLSADO: { label: 'Desembolsado', variant: 'success' },
  RECHAZADO: { label: 'No aprobado', variant: 'danger' },
  CANCELADO: { label: 'Pagado', variant: 'default' },
}

function Timeline({ loan }: { loan: Loan }) {
  const steps = [
    { label: 'Solicitud recibida', date: loan.created_at, done: true },
    {
      label: loan.status === 'RECHAZADO' ? 'No aprobado' : 'Evaluación de Riesgos',
      date: loan.decided_at,
      done: loan.status !== 'SOLICITADO',
    },
    { label: 'Desembolso en tu cuenta', date: loan.disbursed_at, done: Boolean(loan.disbursed_at) },
  ]
  return (
    <ol className="mt-3 space-y-2">
      {steps.map((s) => (
        <li key={s.label} className="flex items-center gap-2 text-sm">
          <span
            className={`flex size-5 items-center justify-center rounded-full ${s.done ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}
            aria-hidden
          >
            {s.done && <Check className="size-3" />}
          </span>
          <span className={s.done ? '' : 'text-muted-foreground'}>{s.label}</span>
          {s.date && (
            <span className="ml-auto text-xs text-muted-foreground">{formatDate(s.date)}</span>
          )}
        </li>
      ))}
    </ol>
  )
}

export function LoansPage() {
  const [amount, setAmount] = useState(5000)
  const [term, setTerm] = useState(24)
  const [confirming, setConfirming] = useState(false)
  const quote = useLoanQuote(amount, term)
  const loans = useLoans()
  const request = useRequestLoan()
  const hasPending = loans.data?.some((l) => l.status === 'SOLICITADO')

  function submit() {
    request.mutate(
      { amount, term_months: term },
      {
        onSuccess: () => {
          setConfirming(false)
          toast.success('¡Solicitud enviada! Te avisaremos cuando sea evaluada.')
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <PageTitle title="Préstamo personal" subtitle="Simula tu cuota y solicítalo en línea" />
      <Card>
        <CardContent className="flex flex-col gap-4 pt-4">
          <div>
            <label htmlFor="monto" className="text-sm font-medium">
              ¿Cuánto necesitas?
            </label>
            <p className="text-3xl font-bold">{formatMoney(amount)}</p>
            <input
              id="monto"
              type="range"
              min={500}
              max={50000}
              step={500}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="w-full accent-[var(--primary)]"
              aria-valuetext={formatMoney(amount)}
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>S/ 500</span>
              <span>S/ 50,000</span>
            </div>
          </div>
          <Field label="Plazo">
            {(p) => (
              <Select {...p} value={term} onChange={(e) => setTerm(Number(e.target.value))}>
                {TERMS.map((t) => (
                  <option key={t} value={t}>
                    {t} meses
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="rounded-xl bg-accent p-4 text-accent-foreground" aria-live="polite">
            {quote.isPending ? (
              <Skeleton className="h-16" />
            ) : quote.data ? (
              <>
                <p className="text-sm">Cuota mensual estimada</p>
                <p className="text-2xl font-bold">{formatMoney(quote.data.monthly_payment)}</p>
                <p className="mt-1 text-xs">
                  TEA {(quote.data.rate_tea * 100).toFixed(2)} % · Total a pagar{' '}
                  {formatMoney(quote.data.total_payment)}
                </p>
              </>
            ) : (
              <p className="text-sm">{errorMessage(quote.error)}</p>
            )}
          </div>
          {hasPending && <Alert variant="info">Ya tienes una solicitud en evaluación.</Alert>}
          <Button
            size="lg"
            disabled={!quote.data || hasPending}
            onClick={() => setConfirming(true)}
          >
            Solicitar préstamo
          </Button>
          <p className="text-xs text-muted-foreground">
            La evaluación la realiza un especialista de Riesgos. La simulación es referencial.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mis solicitudes</CardTitle>
        </CardHeader>
        <CardContent>
          {loans.isPending && <Skeleton className="h-24" />}
          {loans.data?.length === 0 && <EmptyState title="Aún no tienes préstamos" />}
          <ul className="flex flex-col divide-y">
            {loans.data?.map((l) => (
              <li key={l.id} className="py-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{formatMoney(l.amount)}</span>
                  <Badge variant={STATUS[l.status].variant}>{STATUS[l.status].label}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  {l.term_months} meses · cuota {formatMoney(l.monthly_payment)}
                </p>
                {l.status === 'DESEMBOLSADO' && (
                  <dl className="mt-1">
                    <SummaryRow
                      label="Saldo por pagar"
                      value={formatMoney(l.outstanding_balance)}
                    />
                    {l.days_past_due > 0 && (
                      <SummaryRow label="Días de atraso" value={l.days_past_due} />
                    )}
                  </dl>
                )}
                <Timeline loan={l} />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirma tu solicitud"
        confirmLabel="Enviar solicitud"
        loading={request.isPending}
        onConfirm={submit}
        rows={[
          { label: 'Monto', value: formatMoney(amount) },
          { label: 'Plazo', value: `${term} meses` },
          { label: 'Cuota estimada', value: formatMoney(quote.data?.monthly_payment) },
        ]}
      />
    </div>
  )
}
