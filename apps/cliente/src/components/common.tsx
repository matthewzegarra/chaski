import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  formatDateTime,
  formatMoney,
  type Receipt,
} from '@chaski/shared'
import { CheckCircle2, Share2 } from 'lucide-react'
import type { ReactNode } from 'react'

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold">{title}</h1>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  )
}

export function SummaryRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  )
}

/** Shows the operation summary and asks for explicit confirmation before posting money. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  rows,
  confirmLabel,
  loading,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  rows: { label: string; value: ReactNode }[]
  confirmLabel: string
  loading: boolean
  onConfirm: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description="Revisa los datos antes de confirmar.">
        <dl className="divide-y rounded-lg border px-3">
          {rows.map((r) => (
            <SummaryRow key={r.label} label={r.label} value={r.value} />
          ))}
        </dl>
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="outline"
            size="lg"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancelar
          </Button>
          <Button size="lg" onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function ReceiptCard({ receipt, onDone }: { receipt: Receipt; onDone: () => void }) {
  const isTransfer = receipt.operation === 'TRANSFERENCIA'
  async function share() {
    const text = `Chaski · ${isTransfer ? 'Transferencia' : 'Pago'} de ${formatMoney(receipt.amount, receipt.currency)} · Operación ${receipt.transaction_id.slice(0, 8).toUpperCase()}`
    try {
      if (navigator.share) await navigator.share({ title: 'Comprobante Chaski', text })
      else await navigator.clipboard.writeText(text)
    } catch {
      /* user cancelled */
    }
  }
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 pt-6 text-center">
        <CheckCircle2 className="size-14 text-brand-500" aria-hidden />
        <div>
          <p className="text-sm text-muted-foreground">
            {isTransfer ? 'Transferencia exitosa' : 'Pago exitoso'}
          </p>
          <p className="text-3xl font-bold">{formatMoney(receipt.amount, receipt.currency)}</p>
        </div>
        <dl className="w-full divide-y rounded-lg border px-3 text-left">
          <SummaryRow
            label="N.° de operación"
            value={receipt.transaction_id.slice(0, 8).toUpperCase()}
          />
          <SummaryRow label="Fecha" value={formatDateTime(receipt.created_at)} />
          {receipt.from_account_number && (
            <SummaryRow label="Desde" value={receipt.from_account_number} />
          )}
          {receipt.to_account_number && (
            <SummaryRow
              label="Hacia"
              value={`${receipt.to_account_number}${receipt.internal ? '' : ' (otro banco)'}`}
            />
          )}
          {receipt.merchant && <SummaryRow label="Comercio" value={receipt.merchant} />}
          {receipt.card_last4 && (
            <SummaryRow label="Tarjeta" value={`•••• ${receipt.card_last4}`} />
          )}
          <SummaryRow
            label="Saldo disponible"
            value={formatMoney(receipt.new_balance, receipt.currency)}
          />
        </dl>
        <div className="grid w-full grid-cols-2 gap-2">
          <Button variant="outline" onClick={share}>
            <Share2 /> Compartir
          </Button>
          <Button onClick={onDone}>Listo</Button>
        </div>
      </CardContent>
    </Card>
  )
}
