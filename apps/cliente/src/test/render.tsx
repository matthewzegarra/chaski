import {
  type ApiClient,
  type AuthContextValue,
  type AuthUser,
  TestAuthContext,
} from '@chaski/shared'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

export const CUSTOMER: AuthUser = {
  sub: 'cliente-1',
  name: 'María Quispe',
  roles: ['Cliente'],
  customerId: 'c-1',
}

export type Handler = (service: string, path: string, options: Record<string, unknown>) => unknown

/** Fake ApiClient: `handler` returns the response (or throws) for each call; calls are recorded. */
export function fakeApi(handler: Handler) {
  const calls: { service: string; path: string; options: Record<string, unknown> }[] = []
  const request = vi.fn(
    async (service: string, path: string, options: Record<string, unknown> = {}) => {
      calls.push({ service, path, options })
      return handler(service, path, options)
    },
  )
  const api: ApiClient = {
    request: request as ApiClient['request'],
    get: ((service: string, path: string, query?: unknown) =>
      request(service, path, { query })) as ApiClient['get'],
    post: ((service: string, path: string, body?: unknown, headers?: Record<string, string>) =>
      request(service, path, { method: 'POST', body, headers })) as ApiClient['post'],
  }
  return { api, calls }
}

export function renderWithProviders(
  ui: ReactNode,
  { api, user = CUSTOMER, route = '/' }: { api: ApiClient; user?: AuthUser | null; route?: string },
) {
  const auth: AuthContextValue = {
    mode: 'dev',
    ready: true,
    user,
    api,
    getToken: async () => 'token',
    loginDev: vi.fn(),
    loginEntra: vi.fn(),
    logout: vi.fn(),
  }
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <TestAuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </TestAuthContext.Provider>
    </QueryClientProvider>,
  )
}
