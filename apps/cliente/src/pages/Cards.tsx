import {
  Badge,
  Button,
  cn,
  Dialog,
  DialogContent,
  EmptyState,
  errorMessage,
  formatMoney,
  Skeleton,
  toast,
} from '@chaski/shared'
import { Lock, LockOpen } from 'lucide-react'
import { useState } from 'react'

import { useCards, useCardStatus } from '../api'
import { PageTitle } from '../components/common'

export function CardsPage() {
  const cards = useCards()
  const setStatus = useCardStatus()
  const [target, setTarget] = useState<{ id: string; last4: string; block: boolean } | null>(null)

  function confirm() {
    if (!target) return
    setStatus.mutate(
      { id: target.id, block: target.block },
      {
        onSuccess: () => {
          toast.success(target.block ? 'Tarjeta bloqueada' : 'Tarjeta desbloqueada')
          setTarget(null)
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    )
  }

  return (
    <div>
      <PageTitle
        title="Mis tarjetas"
        subtitle="Bloquéala al instante si la pierdes o ves algo extraño"
      />
      {cards.isPending && <Skeleton className="h-48" />}
      {cards.data?.length === 0 && <EmptyState title="No tienes tarjetas" />}
      <div className="flex flex-col gap-4">
        {cards.data?.map((c) => {
          const blocked = c.status === 'BLOQUEADA'
          return (
            <div key={c.id} className="flex flex-col gap-3">
              <div
                className={cn(
                  'relative aspect-[1.6] rounded-2xl p-5 text-white shadow-md',
                  c.type === 'CREDITO'
                    ? 'bg-gradient-to-br from-brand-600 to-brand-900'
                    : 'bg-gradient-to-br from-navy-500 to-navy-900',
                  blocked && 'grayscale',
                )}
              >
                <div className="flex items-start justify-between">
                  <span className="text-sm font-semibold tracking-widest">CHASKI</span>
                  <span className="text-sm font-bold">{c.brand}</span>
                </div>
                <p
                  className="absolute bottom-12 left-5 text-xl tracking-[0.2em]"
                  aria-label={`Terminada en ${c.last4}`}
                >
                  •••• •••• •••• {c.last4}
                </p>
                <p className="absolute bottom-5 left-5 text-xs text-white/80">
                  {c.type === 'DEBITO'
                    ? 'Débito'
                    : `Crédito · Línea ${formatMoney(c.credit_limit)}`}
                </p>
                {blocked && (
                  <span className="absolute right-4 bottom-4 flex items-center gap-1 rounded-full bg-black/40 px-2 py-1 text-xs">
                    <Lock className="size-3" aria-hidden /> Bloqueada
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <Badge variant={blocked ? 'danger' : 'success'}>
                  {blocked ? 'Bloqueada' : 'Activa'}
                </Badge>
                <Button
                  variant={blocked ? 'outline' : 'destructive'}
                  onClick={() => setTarget({ id: c.id, last4: c.last4, block: !blocked })}
                >
                  {blocked ? <LockOpen /> : <Lock />}
                  {blocked ? 'Desbloquear' : 'Bloquear'}
                </Button>
              </div>
            </div>
          )
        })}
      </div>
      <Dialog open={target !== null} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent
          title={target?.block ? '¿Bloquear tu tarjeta?' : '¿Desbloquear tu tarjeta?'}
          description={
            target?.block
              ? `No podrás comprar con la tarjeta •••• ${target?.last4} hasta desbloquearla.`
              : `La tarjeta •••• ${target?.last4} volverá a funcionar de inmediato.`
          }
        >
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" size="lg" onClick={() => setTarget(null)}>
              Cancelar
            </Button>
            <Button
              size="lg"
              variant={target?.block ? 'destructive' : 'default'}
              loading={setStatus.isPending}
              onClick={confirm}
            >
              Confirmar
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
