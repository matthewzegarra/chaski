/** Simulated debit-card purchase (POS or online), useful to demo the fraud rules. */
import {
  Alert,
  Button,
  Card,
  CardContent,
  EmptyState,
  errorMessage,
  Field,
  formatMoney,
  Input,
  newId,
  type Receipt,
  Select,
  Skeleton,
} from '@chaski/shared'
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { useCardPayment, useCards } from '../api'
import { ConfirmDialog, PageTitle, ReceiptCard } from '../components/common'

const CITIES = ['Lima', 'Arequipa', 'Trujillo', 'Piura', 'Cusco', 'Huancayo', 'Chiclayo', 'Iquitos']

export function PayPage() {
  const cards = useCards()
  const pay = useCardPayment()
  const navigate = useNavigate()
  const debit = useMemo(
    () => cards.data?.filter((c) => c.type === 'DEBITO' && c.status === 'ACTIVA') ?? [],
    [cards.data],
  )
  const [cardId, setCardId] = useState('')
  const [merchant, setMerchant] = useState('')
  const [amount, setAmount] = useState('')
  const [channel, setChannel] = useState<'POS' | 'WEB'>('POS')
  const [city, setCity] = useState('Lima')
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const keyRef = useRef(newId())

  useEffect(() => {
    if (!cardId && debit[0]) setCardId(debit[0].id)
  }, [debit, cardId])

  function review(e: FormEvent) {
    e.preventDefault()
    const value = Number(amount)
    if (merchant.trim().length < 2) return setError('Ingresa el comercio')
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || value <= 0) return setError('Ingresa un monto válido')
    setError(null)
    setConfirming(true)
  }

  function confirm() {
    pay.mutate(
      {
        card_id: cardId,
        amount,
        merchant: merchant.trim(),
        channel,
        city: channel === 'POS' ? city : undefined,
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
  const card = debit.find((c) => c.id === cardId)

  return (
    <div>
      <PageTitle
        title="Pagar con tarjeta"
        subtitle="Compra en tienda o por internet con tu tarjeta de débito"
      />
      {cards.isPending && <Skeleton className="h-72" />}
      {cards.data && debit.length === 0 && (
        <EmptyState
          title="No tienes tarjetas de débito activas"
          description="Desbloquea tu tarjeta desde la sección Tarjetas."
        />
      )}
      {debit.length > 0 && (
        <Card>
          <CardContent className="pt-4">
            <form onSubmit={review} className="flex flex-col gap-3" noValidate>
              <Field label="Tarjeta">
                {(p) => (
                  <Select {...p} value={cardId} onChange={(e) => setCardId(e.target.value)}>
                    {debit.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.brand} Débito •••• {c.last4}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label="Comercio">
                {(p) => (
                  <Input
                    {...p}
                    value={merchant}
                    onChange={(e) => setMerchant(e.target.value)}
                    placeholder="Ej. Plaza Vea"
                  />
                )}
              </Field>
              <Field label="Monto (S/)">
                {(p) => (
                  <Input
                    {...p}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                )}
              </Field>
              <Field label="Tipo de compra">
                {(p) => (
                  <Select
                    {...p}
                    value={channel}
                    onChange={(e) => setChannel(e.target.value as 'POS' | 'WEB')}
                  >
                    <option value="POS">En tienda (POS)</option>
                    <option value="WEB">Por internet</option>
                  </Select>
                )}
              </Field>
              {channel === 'POS' && (
                <Field label="Ciudad">
                  {(p) => (
                    <Select {...p} value={city} onChange={(e) => setCity(e.target.value)}>
                      {CITIES.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </Select>
                  )}
                </Field>
              )}
              {(error || pay.isError) && (
                <Alert variant="danger">{error ?? errorMessage(pay.error)}</Alert>
              )}
              <Button type="submit" size="lg">
                Continuar
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirma tu pago"
        confirmLabel="Pagar"
        loading={pay.isPending}
        onConfirm={confirm}
        rows={[
          { label: 'Tarjeta', value: card ? `•••• ${card.last4}` : '' },
          { label: 'Comercio', value: merchant },
          { label: 'Monto', value: formatMoney(amount) },
          { label: 'Tipo', value: channel === 'POS' ? `En tienda · ${city}` : 'Por internet' },
        ]}
      />
    </div>
  )
}
