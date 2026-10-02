import {
  Alert,
  Button,
  Card,
  CardContent,
  errorMessage,
  Field,
  formatMoney,
  Input,
  newId,
  type Receipt,
  Select,
  Skeleton,
} from '@chaski/shared'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAccounts, useTransfer } from '../api'
import { ConfirmDialog, PageTitle, ReceiptCard } from '../components/common'

const ACCOUNT_RE = /^(\d{3}-\d{10}|\d{20})$/

export function validateTransfer(
  input: { to: string; amount: string },
  balance: number,
): Partial<Record<'to' | 'amount', string>> {
  const e: Partial<Record<'to' | 'amount', string>> = {}
  if (!ACCOUNT_RE.test(input.to.trim()))
    e.to = 'Usa el formato 200-3XXXXXXXXX o un CCI de 20 dígitos'
  const amount = Number(input.amount)
  if (!input.amount || !Number.isFinite(amount) || amount <= 0) e.amount = 'Ingresa un monto válido'
  else if (!/^\d+(\.\d{1,2})?$/.test(input.amount)) e.amount = 'Máximo 2 decimales'
  else if (amount > balance) e.amount = 'Saldo insuficiente'
  return e
}

export function TransferPage() {
  const accounts = useAccounts()
  const transfer = useTransfer()
  const navigate = useNavigate()
  const [fromId, setFromId] = useState('')
  const [to, setTo] = useState('')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<Partial<Record<'to' | 'amount', string>>>({})
  const [confirming, setConfirming] = useState(false)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  // One key per operation: retries after a network error reuse it, so money moves only once.
  const keyRef = useRef(newId())

  useEffect(() => {
    if (!fromId && accounts.data?.[0]) setFromId(accounts.data[0].id)
  }, [accounts.data, fromId])
  const source = accounts.data?.find((a) => a.id === fromId)

  function review(e: FormEvent) {
    e.preventDefault()
    const found = validateTransfer({ to, amount }, source?.balance ?? 0)
    setErrors(found)
    if (Object.keys(found).length === 0) setConfirming(true)
  }

  function confirm() {
    transfer.mutate(
      {
        from_account_id: fromId,
        to_account_number: to.trim(),
        amount,
        description: description || undefined,
        idempotencyKey: keyRef.current,
      },
      {
        onSuccess: (r) => {
          setConfirming(false)
          setReceipt(r)
          keyRef.current = newId()
        },
      },
    )
  }

  if (receipt) return <ReceiptCard receipt={receipt} onDone={() => navigate('/')} />

  return (
    <div>
      <PageTitle title="Transferir" subtitle="A cuentas Chaski o a otros bancos (CCI)" />
      {accounts.isPending ? (
        <Skeleton className="h-72" />
      ) : (
        <Card>
          <CardContent className="pt-4">
            <form onSubmit={review} className="flex flex-col gap-3" noValidate>
              <Field
                label="Desde"
                hint={
                  source ? `Disponible: ${formatMoney(source.balance, source.currency)}` : undefined
                }
              >
                {(p) => (
                  <Select {...p} value={fromId} onChange={(e) => setFromId(e.target.value)}>
                    {accounts.data?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.number} · {formatMoney(a.balance, a.currency)}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label="Cuenta destino o CCI" error={errors.to}>
                {(p) => (
                  <Input
                    {...p}
                    value={to}
                    onChange={(e) => setTo(e.target.value)}
                    placeholder="200-3XXXXXXXXX"
                    inputMode="numeric"
                  />
                )}
              </Field>
              <Field label={`Monto (${source?.currency ?? 'PEN'})`} error={errors.amount}>
                {(p) => (
                  <Input
                    {...p}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="0.00"
                    inputMode="decimal"
                  />
                )}
              </Field>
              <Field label="Descripción (opcional)">
                {(p) => (
                  <Input
                    {...p}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    maxLength={140}
                  />
                )}
              </Field>
              {transfer.isError && <Alert variant="danger">{errorMessage(transfer.error)}</Alert>}
              <Button type="submit" size="lg" className="mt-1">
                Continuar
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirma tu transferencia"
        confirmLabel="Transferir"
        loading={transfer.isPending}
        onConfirm={confirm}
        rows={[
          { label: 'Desde', value: source?.number },
          { label: 'Hacia', value: to },
          { label: 'Monto', value: formatMoney(amount, source?.currency) },
          ...(description ? [{ label: 'Descripción', value: description }] : []),
        ]}
      />
    </div>
  )
}
