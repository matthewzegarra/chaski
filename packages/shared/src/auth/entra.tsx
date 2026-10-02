/** Entra ID (MSAL React). Loaded on demand only when authMode=entra, so dev builds skip MSAL. */
import {
  type AccountInfo,
  InteractionRequiredAuthError,
  PublicClientApplication,
} from '@azure/msal-browser'
import { MsalProvider, useMsal } from '@azure/msal-react'
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { createApiClient } from '../api/client'
import { config } from '../lib/config'
import { AuthContext, type AuthContextValue, type AuthUser, userFromToken } from './AuthProvider'

let msalInstance: PublicClientApplication | null = null

function getMsal(): PublicClientApplication {
  if (!msalInstance) {
    msalInstance = new PublicClientApplication({
      auth: {
        clientId: config.entraClientId,
        authority: `https://login.microsoftonline.com/${config.entraTenantId}`,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    })
  }
  return msalInstance
}

function EntraInner({ children }: { children: ReactNode }) {
  const { instance, accounts, inProgress } = useMsal()
  const account: AccountInfo | null = instance.getActiveAccount() ?? accounts[0] ?? null
  const [user, setUser] = useState<AuthUser | null>(null)
  const scopes = useMemo(() => [config.entraApiScope], [])

  const getToken = useCallback(async () => {
    if (!account) return null
    try {
      const result = await instance.acquireTokenSilent({ scopes, account })
      return result.accessToken
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        await instance.acquireTokenRedirect({ scopes, account })
      }
      return null
    }
  }, [instance, account, scopes])

  useEffect(() => {
    let cancelled = false
    if (account && inProgress === 'none') {
      void getToken().then((t) => {
        if (!cancelled) setUser(t ? userFromToken(t) : null)
      })
    } else if (!account) {
      setUser(null)
    }
    return () => {
      cancelled = true
    }
  }, [account, inProgress, getToken])

  const api = useMemo(() => createApiClient(getToken), [getToken])
  const value = useMemo<AuthContextValue>(
    () => ({
      mode: 'entra',
      ready: inProgress === 'none' && (!account || user !== null),
      user,
      api,
      getToken,
      loginDev: async () => {
        throw new Error('El selector de usuarios solo existe en modo dev')
      },
      loginEntra: () => instance.loginRedirect({ scopes }),
      logout: () => void instance.logoutRedirect(),
    }),
    [inProgress, account, user, api, getToken, instance, scopes],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export default function EntraAuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const msal = getMsal()
  useEffect(() => {
    void msal
      .initialize()
      .then(() => msal.handleRedirectPromise())
      .then((result) => {
        if (result?.account) msal.setActiveAccount(result.account)
        setReady(true)
      })
  }, [msal])
  if (!ready) return null
  return (
    <MsalProvider instance={msal}>
      <EntraInner>{children}</EntraInner>
    </MsalProvider>
  )
}
