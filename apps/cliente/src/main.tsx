import './index.css'

import { ApiError, AuthProvider, Toaster } from '@chaski/shared'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'

function onAuthError(error: unknown) {
  // Expired/invalid session: drop it and go back to the welcome screen.
  if (error instanceof ApiError && error.status === 401) {
    try {
      sessionStorage.removeItem('chaski.cliente.token')
    } catch {
      /* ignore */
    }
    window.location.assign('/bienvenida')
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: onAuthError }),
  mutationCache: new MutationCache({ onError: onAuthError }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider appName="cliente">
        <BrowserRouter>
          <App />
        </BrowserRouter>
        <Toaster richColors position="top-center" closeButton />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
