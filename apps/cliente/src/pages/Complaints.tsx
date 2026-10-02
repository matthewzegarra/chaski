import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CATEGORY_LABELS,
  type ComplaintCustomer,
  EmptyState,
  errorMessage,
  Field,
  formatDate,
  Input,
  Skeleton,
  Textarea,
  toast,
} from '@chaski/shared'
import { type FormEvent, useState } from 'react'

import { useComplaints, useCreateComplaint } from '../api'
import { PageTitle } from '../components/common'

const STATUS: Record<
  ComplaintCustomer['status'],
  { label: string; variant: 'warning' | 'info' | 'success' }
> = {
  NUEVA: { label: 'Recibido', variant: 'info' },
  EN_REVISION: { label: 'En revisión', variant: 'warning' },
  RESUELTA: { label: 'Resuelto', variant: 'success' },
}

export function ComplaintsPage() {
  const complaints = useComplaints()
  const create = useCreateComplaint()
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [errors, setErrors] = useState<{ subject?: string; body?: string }>({})

  function submit(e: FormEvent) {
    e.preventDefault()
    const found: typeof errors = {}
    if (subject.trim().length < 3) found.subject = 'Escribe un asunto'
    if (body.trim().length < 10) found.body = 'Cuéntanos un poco más (mínimo 10 caracteres)'
    setErrors(found)
    if (Object.keys(found).length) return
    create.mutate(
      { subject: subject.trim(), body: body.trim() },
      {
        onSuccess: (c) => {
          toast.success(`Reclamo registrado. Te responderemos hasta el ${formatDate(c.due_at)}.`)
          setSubject('')
          setBody('')
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <PageTitle
        title="Libro de reclamaciones"
        subtitle="Respondemos en un plazo máximo de 15 días hábiles"
      />
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
            <Field label="Asunto" error={errors.subject}>
              {(p) => (
                <Input
                  {...p}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  maxLength={120}
                />
              )}
            </Field>
            <Field label="Detalle" error={errors.body} hint={`${body.length}/2000`}>
              {(p) => (
                <Textarea
                  {...p}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  maxLength={2000}
                />
              )}
            </Field>
            <Button type="submit" size="lg" loading={create.isPending}>
              Enviar reclamo
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Mis reclamos</CardTitle>
        </CardHeader>
        <CardContent>
          {complaints.isPending && <Skeleton className="h-24" />}
          {complaints.data?.length === 0 && <EmptyState title="No tienes reclamos registrados" />}
          <ul className="divide-y">
            {complaints.data?.map((c) => (
              <li key={c.id} className="py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{c.subject}</span>
                  <Badge variant={STATUS[c.status].variant}>{STATUS[c.status].label}</Badge>
                </div>
                <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{c.body}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatDate(c.created_at)}
                  {c.category && ` · ${CATEGORY_LABELS[c.category] ?? c.category}`}
                  {c.status !== 'RESUELTA' && ` · Respuesta hasta ${formatDate(c.due_at)}`}
                </p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
