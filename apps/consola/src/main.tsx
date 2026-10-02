import './index.css'

import { ApiError, AuthProvider, Toaster } from '@chaski/shared'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import { RoleProvider } from './session'

function onAuthError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    try {
      sessionStorage.removeItem('chaski.consola.token')
    } catch {
      /* ignore */
    }
    window.location.assign('/login')
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: onAuthError }),
  mutationCache: new MutationCache({ onError: onAuthError }),
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider appName="consola">
        <RoleProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </RoleProvider>
        <Toaster richColors position="top-right" closeButton />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
