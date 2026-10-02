/**
 * One auth API for both apps:
 *  - dev:   persona selector -> core-api /dev/token (HS256, local only). Token kept in sessionStorage.
 *  - entra: MSAL React with the API's App Roles; roles/customer_id are read from the access token.
 */
import {
  createContext,
  lazy,
  type ReactNode,
  Suspense,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react'

import { type ApiClient, createApiClient } from '../api/client'
import type { DevPersona } from '../api/types'
import { config } from '../lib/config'

export interface AuthUser {
  sub: string
  name: string
  roles: string[]
  customerId: string | null
}

export interface AuthContextValue {
  mode: 'dev' | 'entra'
  ready: boolean
  user: AuthUser | null
  api: ApiClient
  getToken: () => Promise<string | null>
  loginDev: (persona: DevPersona) => Promise<void>
  loginEntra: () => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
const EntraAuthProvider = lazy(() => import('./entra'))

export function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const b64 = part
      .replace(/-/g, '+')
      .replace(/_/g, '/')
      .padEnd(Math.ceil(part.length / 4) * 4, '=')
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    return JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>
  } catch {
    return null
  }
}

const EXTENSION_CUSTOMER_ID = /^extension_[0-9a-f]{32}_customer_id$/

/** customer_id from dev tokens or an Entra directory extension (mirrors chaski_common.auth). */
export function customerIdClaim(claims: Record<string, unknown>): unknown {
  for (const key of ['customer_id', 'extension_customer_id', 'extn.customer_id']) {
    if (claims[key]) return claims[key]
  }
  const ext = Object.keys(claims).find((k) => EXTENSION_CUSTOMER_ID.test(k) && claims[k])
  return ext ? claims[ext] : undefined
}

export function userFromToken(token: string): AuthUser | null {
  const claims = decodeJwt(token)
  if (!claims) return null
  const exp = typeof claims.exp === 'number' ? claims.exp : 0
  if (exp * 1000 < Date.now()) return null
  const cid = customerIdClaim(claims)
  return {
    sub: String(claims.oid ?? claims.sub ?? ''),
    name: String(claims.name ?? claims.preferred_username ?? 'Usuario'),
    roles: Array.isArray(claims.roles) ? claims.roles.map(String) : [],
    customerId: typeof cid === 'string' ? cid : null,
  }
}

// ------------------------------------------------------------------ dev

function DevAuthProvider({ storageKey, children }: { storageKey: string; children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => {
    try {
      const saved = sessionStorage.getItem(storageKey)
      return saved && userFromToken(saved) ? saved : null
    } catch {
      return null
    }
  })
  const user = useMemo(() => (token ? userFromToken(token) : null), [token])
  const getToken = useCallback(async () => token, [token])
  const api = useMemo(() => createApiClient(getToken), [getToken])

  const loginDev = useCallback(
    async (persona: DevPersona) => {
      const anon = createApiClient(async () => null)
      const resp = await anon.post<{ access_token: string }>('core', '/dev/token', {
        sub: persona.sub,
        name: persona.name,
        roles: persona.roles,
        customer_id: persona.customer_id,
      })
      try {
        sessionStorage.setItem(storageKey, resp.access_token)
      } catch {
        /* private mode: keep in memory only */
      }
      setToken(resp.access_token)
    },
    [storageKey],
  )

  const logout = useCallback(() => {
    try {
      sessionStorage.removeItem(storageKey)
    } catch {
      /* ignore */
    }
    setToken(null)
  }, [storageKey])

  const value = useMemo<AuthContextValue>(
    () => ({
      mode: 'dev',
      ready: true,
      user,
      api,
      getToken,
      loginDev,
      loginEntra: async () => {
        throw new Error('Entra no está habilitado en modo dev')
      },
      logout,
    }),
    [user, api, getToken, loginDev, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ------------------------------------------------------------------ public

export function AuthProvider({ appName, children }: { appName: string; children: ReactNode }) {
  if (config.authMode === 'entra') {
    return (
      <Suspense fallback={null}>
        <EntraAuthProvider>{children}</EntraAuthProvider>
      </Suspense>
    )
  }
  return <DevAuthProvider storageKey={`chaski.${appName}.token`}>{children}</DevAuthProvider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function useApi(): ApiClient {
  return useAuth().api
}

/** Lets tests render components with a fake session. */
export const TestAuthContext = AuthContext
