import { Alert, Button, Logo, Skeleton, useAuth } from '@chaski/shared'
import { ArrowLeftRight, CreditCard, Home, List, LogOut, Menu } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, NavLink, Outlet, useLocation } from 'react-router'

import { useProfile } from '../api'
import { AssistantChat } from './AssistantChat'

const NAV = [
  { to: '/', label: 'Inicio', icon: Home, end: true },
  { to: '/movimientos', label: 'Movimientos', icon: List },
  { to: '/transferir', label: 'Transferir', icon: ArrowLeftRight },
  { to: '/tarjetas', label: 'Tarjetas', icon: CreditCard },
  { to: '/mas', label: 'Más', icon: Menu },
]

export function RequireCustomer({ children }: { children: ReactNode }) {
  const { user, ready, logout } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (!user) return <Navigate to="/bienvenida" replace state={{ from: location.pathname }} />
  if (!user.roles.includes('Cliente') || !user.customerId) {
    return (
      <Shell>
        <div className="flex flex-col gap-4 p-6">
          <Alert variant="warning">
            Esta aplicación es para clientes. Los colaboradores del banco usan el Chaski Control
            Center.
          </Alert>
          <Button variant="outline" onClick={logout}>
            Cambiar de usuario
          </Button>
        </div>
      </Shell>
    )
  }
  return <>{children}</>
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="mx-auto flex min-h-dvh max-w-md flex-col bg-background">{children}</div>
}

function Header() {
  const { user, logout } = useAuth()
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b bg-card/95 px-4 py-3 backdrop-blur">
      <Logo />
      <div className="flex items-center gap-2">
        <span className="max-w-36 truncate text-sm text-muted-foreground">
          Hola, {user?.name.split(' ')[0]}
        </span>
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Cerrar sesión">
          <LogOut />
        </Button>
      </div>
    </header>
  )
}

function BottomNav() {
  return (
    <nav
      aria-label="Navegación principal"
      className="sticky bottom-0 z-30 grid grid-cols-5 border-t bg-card pb-[env(safe-area-inset-bottom)]"
    >
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
              isActive ? 'text-primary' : 'text-muted-foreground'
            }`
          }
        >
          <Icon className="size-5" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

/** Blocks the banking screens while the KYC review is pending or after a rejection. */
function KycGate({ children }: { children: ReactNode }) {
  const profile = useProfile()
  if (profile.isPending) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-20" />
      </div>
    )
  }
  const status = profile.data?.kyc_status
  if (status === 'PENDIENTE') {
    return (
      <div className="flex flex-col items-center gap-3 p-8 text-center">
        <div className="rounded-full bg-amber-100 px-4 py-2 text-sm font-semibold text-amber-900">
          En revisión
        </div>
        <h1 className="text-xl font-bold">Estamos validando tu identidad</h1>
        <p className="text-sm text-muted-foreground">
          Un asesor revisará tus datos y la foto de tu DNI. Te avisaremos apenas tu cuenta esté
          lista.
        </p>
      </div>
    )
  }
  if (status === 'RECHAZADO') {
    return (
      <div className="p-6">
        <Alert variant="danger">
          No pudimos aprobar tu solicitud. Comunícate con nosotros para más información.
        </Alert>
      </div>
    )
  }
  return <>{children}</>
}

export function AppLayout() {
  return (
    <Shell>
      <a href="#contenido" className="sr-only focus:not-sr-only focus:p-2">
        Ir al contenido
      </a>
      <Header />
      <main id="contenido" className="flex-1 px-4 pt-4 pb-24">
        <KycGate>
          <Outlet />
        </KycGate>
      </main>
      <AssistantChat />
      <BottomNav />
    </Shell>
  )
}
