/**
 * Guards a module route. A user without permission sees "Acceso restringido" and the
 * attempt is reported to core-api, which writes it to ops.audit_log (allowed=false).
 */
import { Button, useApi } from '@chaski/shared'
import { Lock } from 'lucide-react'
import { type ReactNode, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router'

import { canAccess, moduleById } from '../modules'
import { useRole } from '../session'

export function AccessRestricted({ moduleLabel }: { moduleLabel: string }) {
  return (
    <div className="mx-auto mt-16 flex max-w-md flex-col items-center gap-3 text-center">
      <div className="rounded-full bg-red-100 p-4 text-red-800 dark:bg-red-950 dark:text-red-200">
        <Lock className="size-8" aria-hidden />
      </div>
      <h1 className="text-2xl font-bold">Acceso restringido</h1>
      <p className="text-muted-foreground">
        Tu rol no tiene permiso para ver <strong>{moduleLabel}</strong>. El intento quedó registrado
        en la auditoría.
      </p>
      <Button asChild variant="outline">
        <Link to="/">Volver al inicio</Link>
      </Button>
    </div>
  )
}

export function RoleRoute({ moduleId, children }: { moduleId: string; children: ReactNode }) {
  const module = moduleById(moduleId)
  const { activeRole } = useRole()
  const api = useApi()
  const location = useLocation()
  const allowed = canAccess(module, activeRole)
  const reported = useRef<string | null>(null)

  useEffect(() => {
    const key = `${location.pathname}|${activeRole}`
    if (!allowed && reported.current !== key) {
      reported.current = key
      void api
        .post('core', '/security/denied-route', { route: location.pathname, module: module.id })
        .catch(() => undefined)
    }
  }, [allowed, api, location.pathname, module.id, activeRole])

  if (!allowed) return <AccessRestricted moduleLabel={module.label} />
  return <>{children}</>
}
