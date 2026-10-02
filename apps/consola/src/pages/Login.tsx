import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  type DevUsers,
  errorMessage,
  Logo,
  Skeleton,
  toast,
  useApi,
  useAuth,
} from '@chaski/shared'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { ROLE_LABELS, type StaffRole } from '../modules'
import { useRole } from '../session'

function DevSelector() {
  const api = useApi()
  const { loginDev } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const users = useQuery({
    queryKey: ['dev-users'],
    queryFn: () => api.request<DevUsers>('core', '/dev/users', { auth: false }),
  })

  async function enter(persona: DevUsers['staff'][number]) {
    setBusy(persona.sub ?? persona.name)
    try {
      await loginDev(persona)
      navigate('/', { replace: true })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  if (users.isPending) return <Skeleton className="h-80" />
  if (users.isError) return <Alert variant="danger">{errorMessage(users.error)}</Alert>
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {users.data.staff.map((p) => (
        <li key={p.sub}>
          <button
            onClick={() => void enter(p)}
            disabled={busy !== null}
            className="flex w-full items-center justify-between gap-2 rounded-lg border bg-card p-3 text-left hover:bg-muted disabled:opacity-60"
          >
            <span>
              <span className="block text-sm font-semibold">
                {ROLE_LABELS[p.roles[0] as StaffRole] ?? p.roles[0]}
              </span>
              <span className="text-xs text-muted-foreground">{p.name}</span>
            </span>
            <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  )
}

export function LoginPage() {
  const { user, mode, loginEntra, logout } = useAuth()
  const { activeRole } = useRole()
  const location = useLocation()
  if (user && activeRole) return <Navigate to="/" replace />
  const noRole = Boolean(user && !activeRole) || (location.state as { noRole?: boolean })?.noRole

  return (
    <div className="flex min-h-dvh items-center justify-center bg-gradient-to-br from-navy-800 to-navy-900 p-4">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <Logo subtitle="Control Center" />
          <CardTitle className="mt-3 text-xl">Ingresa a la consola del banco</CardTitle>
          <CardDescription>
            {mode === 'dev'
              ? 'Modo desarrollo: elige un rol de prueba. Cada rol ve solo sus módulos.'
              : 'Usa tu cuenta corporativa de Entra ID.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {noRole && (
            <Alert variant="warning">
              Tu usuario no tiene un rol del banco asignado.{' '}
              <button className="underline" onClick={logout}>
                Cambiar de usuario
              </button>
            </Alert>
          )}
          {mode === 'dev' ? (
            <DevSelector />
          ) : (
            <Button size="lg" onClick={() => void loginEntra()}>
              Iniciar sesión con Microsoft
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
