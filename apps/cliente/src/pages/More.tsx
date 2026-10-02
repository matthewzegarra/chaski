import { Button, Card, CardContent, Skeleton, useAuth, useTheme } from '@chaski/shared'
import { ChevronRight, FileWarning, HandCoins, LogOut, Moon, ShoppingBag, Sun } from 'lucide-react'
import { Link } from 'react-router'

import { useProfile } from '../api'
import { PageTitle, SummaryRow } from '../components/common'

const LINKS = [
  { to: '/prestamos', label: 'Préstamos', icon: HandCoins },
  { to: '/pagar', label: 'Pagar con tarjeta', icon: ShoppingBag },
  { to: '/reclamos', label: 'Reclamos', icon: FileWarning },
]

export function MorePage() {
  const profile = useProfile()
  const { logout } = useAuth()
  const { theme, toggle } = useTheme()
  return (
    <div className="flex flex-col gap-4">
      <PageTitle title="Más opciones" />
      <Card>
        <CardContent className="pt-2">
          <ul className="divide-y">
            {LINKS.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <Link to={to} className="flex items-center gap-3 py-3 font-medium">
                  <Icon className="size-5 text-primary" aria-hidden />
                  {label}
                  <ChevronRight className="ml-auto size-4 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <p className="mb-1 font-semibold">Mis datos</p>
          {profile.isPending ? (
            <Skeleton className="h-24" />
          ) : (
            profile.data && (
              <dl className="divide-y">
                <SummaryRow
                  label="Nombre"
                  value={`${profile.data.first_name} ${profile.data.last_name}`}
                />
                <SummaryRow label="DNI" value={profile.data.document_number} />
                <SummaryRow label="Correo" value={profile.data.email} />
                <SummaryRow label="Celular" value={profile.data.phone ?? '—'} />
              </dl>
            )
          )}
        </CardContent>
      </Card>
      <Button variant="outline" onClick={toggle}>
        {theme === 'dark' ? <Sun /> : <Moon />}
        {theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}
      </Button>
      <Button variant="ghost" onClick={logout}>
        <LogOut /> Cerrar sesión
      </Button>
    </div>
  )
}
