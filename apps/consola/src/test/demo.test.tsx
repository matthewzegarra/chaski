import { type ApiClient, type AuthContextValue, ApiError, TestAuthContext } from '@chaski/shared'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { DemoPage } from '../pages/Demo'

function setup(
  handler: (path: string, options: Record<string, unknown>) => unknown,
  mode: 'dev' | 'entra' = 'entra',
) {
  const calls: string[] = []
  const request = vi.fn(async (_s: string, path: string, options: Record<string, unknown> = {}) => {
    calls.push(path)
    return handler(path, options)
  })
  const api = {
    request,
    get: (s: string, p: string, query?: unknown) => request(s, p, { query }),
    post: (s: string, p: string, body?: unknown) => request(s, p, { method: 'POST', body }),
  } as unknown as ApiClient
  const auth: AuthContextValue = {
    mode,
    ready: true,
    user: { sub: 'admin.demo', name: 'Andrea', roles: ['Admin'], customerId: null },
    api,
    getToken: async () => 't',
    loginDev: vi.fn(),
    loginEntra: vi.fn(),
    logout: vi.fn(),
  }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TestAuthContext.Provider value={auth}>
        <MemoryRouter>
          <DemoPage />
        </MemoryRouter>
      </TestAuthContext.Provider>
    </QueryClientProvider>,
  )
  return calls
}

describe('Modo Demo', () => {
  it('injects a bad record, runs the pipeline and reports the quarantine', async () => {
    const calls = setup((path) =>
      path === '/ops/pipelines/run'
        ? { mode: 'local', run: { status: 'CON_ALERTAS', rows_ok: 352, rows_quarantined: 1 } }
        : { inserted: 3 },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Inyectar y ejecutar pipeline' }))
    expect(await screen.findByText('1 a cuarentena')).toBeInTheDocument()
    expect(calls).toEqual(['/demo/inject-bad-record', '/ops/pipelines/run'])
  })

  it('shows the rules triggered by the fraud burst', async () => {
    setup(() => ({ transfers: 8, alerts: ['R1_VELOCIDAD'] }))
    await userEvent.click(screen.getByRole('button', { name: 'Lanzar ráfaga de transferencias' }))
    expect(await screen.findByText('R1_VELOCIDAD')).toBeInTheDocument()
  })

  it('shows the 403 and the audit entry for the forbidden access (Entra fallback)', async () => {
    const calls = setup((path) => {
      if (path === '/customers') return { items: [{ id: 'c1' }], total: 1, page: 1, page_size: 1 }
      if (path === '/security/audit')
        return {
          items: [
            {
              id: 77,
              actor_id: 'demo.marketing',
              actor_role: 'Marketing',
              created_at: '2026-10-02T12:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        }
      return { status_code: 403 }
    })
    await userEvent.click(screen.getByRole('button', { name: 'Intentar acceso como Marketing' }))
    expect(await screen.findByText('403 Prohibido')).toBeInTheDocument()
    expect(screen.getByText(/Auditoría #77/)).toBeInTheDocument()
    expect(calls).toContain('/demo/forbidden-access')
  })

  it('shows Prompt Shields blocking the injection', async () => {
    setup(() => ({
      categoria: 'OTRO',
      sospechosa: true,
      bloqueada_por_shields: true,
      requiere_revision: true,
      motivo: 'Prompt Shields detectó un posible intento de manipulación del sistema',
    }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar queja maliciosa' }))
    expect(await screen.findByText('Ataque detectado: no llegó al modelo')).toBeInTheDocument()
  })

  it('reports errors from a scenario', async () => {
    setup(() => {
      throw new ApiError(409, 'No hay una cuenta con saldo suficiente para la demo', null)
    })
    await userEvent.click(screen.getByRole('button', { name: 'Lanzar ráfaga de transferencias' }))
    expect(
      await screen.findByText('No hay una cuenta con saldo suficiente para la demo'),
    ).toBeInTheDocument()
  })
})
