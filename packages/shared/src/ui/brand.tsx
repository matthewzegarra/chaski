/** CHASKI typographic logo (own mark, not Interbank's), empty states and error helpers. */
import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { ApiError } from '../api/client'
import { cn } from '../lib/utils'

export function Logo({ className, subtitle }: { className?: string; subtitle?: string }) {
  return (
    <span className={cn('inline-flex items-baseline gap-2', className)}>
      <span
        className="text-xl font-extrabold tracking-[0.18em] text-navy-700 dark:text-white"
        aria-label="CHASKI"
      >
        CHAS<span className="text-brand-500">KI</span>
      </span>
      {subtitle && <span className="text-xs font-medium text-muted-foreground">{subtitle}</span>}
    </span>
  )
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string
  description?: string
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <div className="rounded-full bg-muted p-3 text-muted-foreground">
        {icon ?? <Inbox className="size-6" />}
      </div>
      <p className="font-semibold">{title}</p>
      {description && <p className="max-w-xs text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  if (err instanceof Error) return err.message
  return 'Ocurrió un error inesperado'
}

export function toastError(err: unknown): void {
  toast.error(errorMessage(err))
}

export { toast } from 'sonner'
export { Toaster } from 'sonner'
