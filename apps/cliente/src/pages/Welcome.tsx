import {
  Badge,
  Button,
  Card,
  CardContent,
  type DevUsers,
  errorMessage,
  Logo,
  Skeleton,
  toast,
  useApi,
  useAuth,
} from '@chaski/shared'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ShieldCheck, Smartphone, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'

function DevSelector() {
  const api = useApi()
  const { loginDev } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const users = useQuery({
    queryKey: ['dev-users'],
    queryFn: () => api.request<DevUsers>('core', '/dev/users', { auth: false }),
  })

  async function enter(customer: DevUsers['customers'][number]) {
    setBusy(customer.customer_id)
    try {
      await loginDev({ name: customer.name, roles: ['Cliente'], customer_id: customer.customer_id })
      navigate('/', { replace: true })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardContent className="pt-4">
        <p className="mb-1 text-sm font-semibold">Ingresar como cliente de prueba</p>
        <p className="mb-3 text-xs text-muted-foreground">
          Modo desarrollo: no se usan contraseñas.
        </p>
        {users.isPending && <Skeleton className="h-40" />}
        {users.isError && <p className="text-sm text-destructive">{errorMessage(users.error)}</p>}
        <ul className="divide-y">
          {users.data?.customers.map((c) => (
            <li key={c.customer_id}>
              <button
                onClick={() => void enter(c)}
                disabled={busy !== null}
                className="flex w-full items-center justify-between gap-2 py-2.5 text-left hover:bg-muted/50 disabled:opacity-60"
              >
                <span>
                  <span className="block text-sm font-medium">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.segment}</span>
                </span>
                <span className="flex items-center gap-2">
                  {c.kyc_status === 'PENDIENTE' && <Badge variant="warning">En revisión</Badge>}
                  <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

export function WelcomePage() {
  const { user, mode, loginEntra } = useAuth()
  if (user?.roles.includes('Cliente')) return <Navigate to="/" replace />
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col gap-6 bg-gradient-to-b from-navy-700 to-navy-900 px-5 pb-8 pt-12 text-white">
      <div>
        <Logo className="[&>span:first-child]:text-white" />
        <h1 className="mt-6 text-3xl font-extrabold leading-tight">
          Tu banco, <span className="text-brand-400">en tiempo real</span>
        </h1>
        <p className="mt-2 text-navy-100">
          Abre tu cuenta en minutos, desde tu celular y sin ir a una agencia.
        </p>
      </div>
      <ul className="space-y-2 text-sm text-navy-100">
        <li className="flex items-center gap-2">
          <Smartphone className="size-4 text-brand-400" aria-hidden /> Transferencias y pagos al
          instante
        </li>
        <li className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-brand-400" aria-hidden /> Bloquea tu tarjeta con un
          toque
        </li>
        <li className="flex items-center gap-2">
          <Sparkles className="size-4 text-brand-400" aria-hidden /> Chaski Asistente te ayuda 24/7
        </li>
      </ul>
      <div className="mt-auto flex flex-col gap-3 text-foreground">
        <Button asChild size="lg" className="bg-brand-500 text-navy-900 hover:bg-brand-400">
          <Link to="/registro">Abrir mi cuenta</Link>
        </Button>
        {mode === 'entra' ? (
          <Button size="lg" variant="outline" onClick={() => void loginEntra()}>
            Ya soy cliente · Ingresar
          </Button>
        ) : (
          <DevSelector />
        )}
      </div>
    </div>
  )
}
