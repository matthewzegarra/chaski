/** Active role: Entra users may hold several App Roles; the console works with one at a time. */
import { useAuth } from '@chaski/shared'
import { createContext, type ReactNode, useContext, useMemo, useState } from 'react'

import { STAFF_ROLES, type StaffRole } from './modules'

interface RoleContextValue {
  roles: StaffRole[]
  activeRole: StaffRole | null
  setActiveRole: (role: StaffRole) => void
}

const RoleContext = createContext<RoleContextValue | null>(null)
const KEY = 'chaski.consola.activeRole'

export function RoleProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const roles = useMemo(() => STAFF_ROLES.filter((r) => user?.roles.includes(r)), [user])
  const [chosen, setChosen] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(KEY)
    } catch {
      return null
    }
  })
  const activeRole = roles.find((r) => r === chosen) ?? roles[0] ?? null
  const value = useMemo<RoleContextValue>(
    () => ({
      roles,
      activeRole,
      setActiveRole: (role) => {
        try {
          sessionStorage.setItem(KEY, role)
        } catch {
          /* ignore */
        }
        setChosen(role)
      },
    }),
    [roles, activeRole],
  )
  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}

export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext)
  if (!ctx) throw new Error('useRole must be used inside <RoleProvider>')
  return ctx
}
