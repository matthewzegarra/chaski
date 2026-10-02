import {
  Badge,
  Button,
  cn,
  config,
  Logo,
  Select,
  Sheet,
  SheetContent,
  SheetTrigger,
  useAuth,
  useTheme,
} from '@chaski/shared'
import { LogOut, Menu, Moon, Sun } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Navigate, NavLink, Outlet, useLocation } from 'react-router'

import { modulesFor, ROLE_LABELS, type StaffRole } from '../modules'
import { useRole } from '../session'

const ENV_VARIANT = { DEV: 'info', TEST: 'warning', PROD: 'danger' } as const

export function RequireStaff({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  const { activeRole } = useRole()
  const location = useLocation()
  if (!ready) return null
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (!activeRole) return <Navigate to="/login" replace state={{ noRole: true }} />
  return <>{children}</>
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { activeRole } = useRole()
  return (
    <nav aria-label="Módulos" className="flex flex-col gap-0.5 p-3">
      {modulesFor(activeRole).map(({ id, path, label, icon: Icon }) => (
        <NavLink
          key={id}
          to={path}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium',
              isActive
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )
          }
        >
          <Icon className="size-4 shrink-0" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

function Header() {
  const { user, logout } = useAuth()
  const { roles, activeRole, setActiveRole } = useRole()
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-card/95 px-4 backdrop-blur">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Abrir menú">
            <Menu />
          </Button>
        </SheetTrigger>
        <SheetContent title="Módulos" side="left">
          <Nav onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
      <Logo subtitle="Control Center" />
      <Badge variant={ENV_VARIANT[config.env]} className="ml-1" title="Entorno">
        {config.env}
      </Badge>
      <div className="ml-auto flex items-center gap-2">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium leading-tight">{user?.name}</p>
          {roles.length <= 1 && (
            <p className="text-xs text-muted-foreground">
              {activeRole ? ROLE_LABELS[activeRole] : 'Sin rol'}
            </p>
          )}
        </div>
        {roles.length > 1 && (
          <>
            <label htmlFor="active-role" className="sr-only">
              Rol activo
            </label>
            <Select
              id="active-role"
              className="h-9 w-40"
              value={activeRole ?? ''}
              onChange={(e) => setActiveRole(e.target.value as StaffRole)}
            >
              {roles.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                </option>
              ))}
            </Select>
          </>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label={theme === 'dark' ? 'Activar modo claro' : 'Activar modo oscuro'}
        >
          {theme === 'dark' ? <Sun /> : <Moon />}
        </Button>
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Cerrar sesión">
          <LogOut />
        </Button>
      </div>
    </header>
  )
}

export function ConsoleLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#contenido" className="sr-only focus:not-sr-only focus:p-2">
        Ir al contenido
      </a>
      <Header />
      <div className="flex flex-1">
        <aside className="hidden w-64 shrink-0 border-r bg-card lg:block">
          <Nav />
        </aside>
        <main id="contenido" className="min-w-0 flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
