import {
  type ApiClient,
  type AuthContextValue,
  type AuthUser,
  TestAuthContext,
} from '@chaski/shared'
import { axeViolations } from '@chaski/shared/testing/axe'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'

import { ConsoleLayout } from '../components/Layout'
import { RoleRoute } from '../components/RoleRoute'
import { DemoPage } from '../pages/Demo'
import { LoginPage } from '../pages/Login'
import { PipelinesPage } from '../pages/Pipelines'
import { SecurityPage } from '../pages/Security'
import { RoleProvider } from '../session'

const DATA: Record<string, unknown> = {
  '/dev/users': { staff: [{ sub: 'ti.demo', name: 'Tomás', roles: ['TI'] }], customers: [] },
  '/ops/pipelines': [
    {
      id: 'r1',
      flow_name: 'ingesta',
      status: 'CON_ALERTAS',
      trigger: 'MANUAL',
      started_at: '2026-10-02T10:00:00Z',
      finished_at: null,
      rows_in: 10,
      rows_ok: 9,
      rows_quarantined: 1,
      error: null,
    },
  ],
  '/ops/pipelines/r1/checks': [
    {
      check_name: 'montos_positivos',
      table_name: 'silver.transactions',
      passed: false,
      failed_count: 1,
    },
  ],
  '/ops/quarantine': [],
  '/security/summary': { denegados_24h: 1, accesos_pii_24h: 0, eventos_24h: 3 },
  '/security/audit': { items: [], total: 0, page: 1, page_size: 25 },
}

function renderConsole(ui: ReactNode, user: AuthUser | null) {
  const request = vi.fn(async (_s: string, path: string) => DATA[path] ?? null)
  const api = {
    request,
    get: (s: string, p: string) => request(s, p),
    post: vi.fn(async () => ({})),
  } as unknown as ApiClient
  const auth: AuthContextValue = {
    mode: 'dev', ready: true, user, api, getToken: async () => 't',
    loginDev: vi.fn(), loginEntra: vi.fn(), logout: vi.fn(),
  } // prettier-ignore
  sessionStorage.clear()
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <TestAuthContext.Provider value={auth}>
        <RoleProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </RoleProvider>
      </TestAuthContext.Provider>
    </QueryClientProvider>,
  )
}

const ti: AuthUser = { sub: 'ti', name: 'Tomás', roles: ['TI'], customerId: null }
const admin: AuthUser = { sub: 'admin', name: 'Andrea', roles: ['Admin'], customerId: null }

describe('accessibility (axe)', () => {
  it('login', async () => {
    const { container } = renderConsole(<LoginPage />, null)
    await screen.findByText('TI')
    expect(await axeViolations(container)).toEqual([])
  })

  it('layout with sidebar, header and skip link', async () => {
    const { container } = renderConsole(<ConsoleLayout />, ti)
    expect(screen.getByRole('link', { name: 'Ir al contenido' })).toBeInTheDocument()
    expect(await axeViolations(container)).toEqual([])
  })

  it('access restricted screen', async () => {
    const { container } = renderConsole(
      <Routes>
        <Route path="*" element={<RoleRoute moduleId="prestamos">x</RoleRoute>} />
      </Routes>,
      ti,
    )
    await screen.findByRole('heading', { name: 'Acceso restringido' })
    expect(await axeViolations(container)).toEqual([])
  })

  it('data pipelines', async () => {
    const { container } = renderConsole(<PipelinesPage />, ti)
    await screen.findByText('montos_positivos')
    expect(await axeViolations(container)).toEqual([])
  })

  it('security and audit', async () => {
    const { container } = renderConsole(<SecurityPage />, admin)
    await screen.findByText('0 eventos')
    expect(await axeViolations(container)).toEqual([])
  })

  it('demo mode', async () => {
    const { container } = renderConsole(<DemoPage />, admin)
    expect(await axeViolations(container)).toEqual([])
  })
})
