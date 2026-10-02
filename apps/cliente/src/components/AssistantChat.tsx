/**
 * Chaski Asistente. The model never executes sensitive actions: ia-api returns a
 * `pending_action` and only an explicit "Confirmar" here calls the real endpoint (D9).
 */
import {
  ApiError,
  Button,
  type ChatMessage,
  type ChatResponse,
  cn,
  errorMessage,
  Input,
  type PendingAction,
  Sheet,
  SheetContent,
  SheetTrigger,
  toast,
  useApi,
} from '@chaski/shared'
import { useQueryClient } from '@tanstack/react-query'
import { Bot, Send, ShieldCheck } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'

interface UiMessage extends ChatMessage {
  action?: PendingAction
  actionState?: 'pending' | 'done' | 'cancelled'
}

const WELCOME: UiMessage = {
  role: 'assistant',
  content:
    'Hola, soy Chaski 👋 Puedo consultar tu saldo, revisar tus movimientos, explicarte un cargo, bloquear tu tarjeta o registrar un reclamo.',
}
const SUGGESTIONS = ['¿Cuál es mi saldo?', 'Mis últimos movimientos', 'Bloquear mi tarjeta']

export function AssistantChat() {
  const api = useApi()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<UiMessage[]>([WELCOME])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [messages, open])

  async function send(content: string) {
    const trimmed = content.trim()
    if (!trimmed || busy) return
    const history: UiMessage[] = [...messages, { role: 'user', content: trimmed }]
    setMessages(history)
    setText('')
    setBusy(true)
    try {
      const resp = await api.post<ChatResponse>('ia', '/assistant/chat', {
        messages: history
          .filter((m) => m !== WELCOME)
          .map(({ role, content: c }) => ({ role, content: c })),
      })
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: resp.reply,
          action: resp.pending_action ?? undefined,
          actionState: resp.pending_action ? 'pending' : undefined,
        },
      ])
    } catch (err) {
      const unavailable = err instanceof ApiError && (err.status === 0 || err.status === 404)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: unavailable
            ? 'El asistente estará disponible pronto. Mientras tanto puedes usar el menú de la app.'
            : errorMessage(err),
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  async function confirm(index: number, action: PendingAction) {
    setBusy(true)
    try {
      if (action.tool === 'block_card') {
        await api.post('core', `/cards/${action.args.card_id}/block`)
        void qc.invalidateQueries({ queryKey: ['cards'] })
      } else {
        await api.post('core', '/complaints', {
          subject: action.args.subject,
          body: action.args.body,
          channel: 'APP',
        })
        void qc.invalidateQueries({ queryKey: ['complaints'] })
      }
      setMessages((m) => [
        ...m.map((msg, i) => (i === index ? { ...msg, actionState: 'done' as const } : msg)),
        {
          role: 'assistant',
          content:
            action.tool === 'block_card'
              ? 'Listo, tu tarjeta quedó bloqueada.'
              : 'Listo, registré tu reclamo.',
        },
      ])
      toast.success('Acción realizada')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function cancel(index: number) {
    setMessages((m) =>
      m.map((msg, i) => (i === index ? { ...msg, actionState: 'cancelled' as const } : msg)),
    )
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send(text)
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          className="fixed bottom-20 right-[max(1rem,calc(50%-14rem+1rem))] z-30 flex size-14 items-center justify-center rounded-full bg-secondary text-secondary-foreground shadow-lg"
          aria-label="Abrir Chaski Asistente"
        >
          <Bot className="size-7" />
        </button>
      </SheetTrigger>
      <SheetContent title="Chaski Asistente" side="bottom" className="mx-auto h-[80dvh] max-w-md">
        <div className="flex h-full flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                <div
                  className={cn(
                    'max-w-[85%] rounded-2xl px-3 py-2 text-sm',
                    m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted',
                  )}
                >
                  <p className="whitespace-pre-line">{m.content}</p>
                  {m.action && (
                    <div className="mt-2 rounded-lg border bg-card p-3 text-foreground">
                      <p className="flex items-center gap-1 text-xs font-semibold text-muted-foreground">
                        <ShieldCheck className="size-4" /> Requiere tu confirmación
                      </p>
                      <p className="mt-1 font-medium">{m.action.summary}</p>
                      {m.actionState === 'pending' ? (
                        <div className="mt-2 grid grid-cols-2 gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => cancel(i)}
                            disabled={busy}
                          >
                            Cancelar
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => void confirm(i, m.action!)}
                            loading={busy}
                          >
                            Confirmar
                          </Button>
                        </div>
                      ) : (
                        <p className="mt-2 text-xs text-muted-foreground">
                          {m.actionState === 'done' ? 'Confirmado' : 'Cancelado'}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <p className="text-xs text-muted-foreground">Chaski está escribiendo…</p>}
            <div ref={endRef} />
          </div>
          {messages.length === 1 && (
            <div className="flex flex-wrap gap-2 px-4 pb-2">
              {SUGGESTIONS.map((s) => (
                <Button key={s} size="sm" variant="outline" onClick={() => void send(s)}>
                  {s}
                </Button>
              ))}
            </div>
          )}
          <form onSubmit={onSubmit} className="flex gap-2 border-t p-3">
            <label htmlFor="chat-input" className="sr-only">
              Escribe tu mensaje
            </label>
            <Input
              id="chat-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Escribe tu consulta…"
              maxLength={500}
              autoComplete="off"
            />
            <Button type="submit" size="icon" aria-label="Enviar" disabled={!text.trim() || busy}>
              <Send />
            </Button>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  )
}
