import {
  type ApiClient,
  type AuthContextValue,
  type AuthUser,
  TestAuthContext,
} from '@chaski/shared'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'

import { ConsoleLayout } from '../components/Layout'
import { RoleRoute } from '../components/RoleRoute'
import { canAccess, MODULES, moduleById, modulesFor, STAFF_ROLES } from '../modules'
import { RoleProvider } from '../session'

// Prompt section 10, written out independently so the table cannot drift silently.
const EXPECTED: Record<string, string[]> = {
  Admin: ['operaciones', 'clientes', 'pipelines', 'salud-ia', 'seguridad', 'demo'],
  Operaciones: ['operaciones'],
  Atencion: ['operaciones', 'clientes', 'quejas'],
  Riesgos: ['operaciones', 'prestamos', 'insights'],
  Fraude: ['operaciones', 'fraude'],
  Direccion: ['operaciones', 'insights'],
  Marketing: ['operaciones', 'insights'],
  TI: ['operaciones', 'pipelines', 'salud-ia', 'seguridad', 'devops'],
}

describe('module/role matrix', () => {
  it.each(STAFF_ROLES)('%s sees exactly its modules', (role) => {
    expect(modulesFor(role).map((m) => m.id)).toEqual(EXPECTED[role])
  })

  it('customers and unknown roles see nothing', () => {
    expect(modulesFor('Cliente')).toEqual([])
    expect(modulesFor('SuperUser')).toEqual([])
    expect(modulesFor(null)).toEqual([])
  })

  it('every module is reachable by at least one role', () => {
    for (const m of MODULES) expect(STAFF_ROLES.some((r) => canAccess(m, r))).toBe(true)
  })
})

function setup(user: AuthUser, ui: ReactNode, route = '/') {
  const post = vi.fn(async () => ({}))
  const api = { request: vi.fn(), get: vi.fn(), post } as unknown as ApiClient
  const auth: AuthContextValue = {
    mode: 'dev',
    ready: true,
    user,
    api,
    getToken: async () => 't',
    loginDev: vi.fn(),
    loginEntra: vi.fn(),
    logout: vi.fn(),
  }
  sessionStorage.clear()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TestAuthContext.Provider value={auth}>
        <RoleProvider>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </RoleProvider>
      </TestAuthContext.Provider>
    </QueryClientProvider>,
  )
  return { post }
}

const staff = (role: string): AuthUser => ({
  sub: `${role}.demo`,
  name: `Usuario ${role}`,
  roles: [role],
  customerId: null,
})

describe('sidebar', () => {
  it.each(['Fraude', 'Marketing', 'TI'])('only lists the modules of %s', (role) => {
    setup(staff(role), <ConsoleLayout />)
    const nav = screen.getAllByRole('navigation', { name: 'Módulos' })[0]!
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent)
    expect(labels).toEqual(EXPECTED[role]!.map((id) => moduleById(id).label))
  })
})

describe('RoleRoute', () => {
  const page = (
    <Routes>
      <Route
        path="/prestamos"
        element={
          <RoleRoute moduleId="prestamos">
            <p>Contenido de préstamos</p>
          </RoleRoute>
        }
      />
    </Routes>
  )

  it('shows "Acceso restringido" and reports the attempt for the audit log', async () => {
    const { post } = setup(staff('Marketing'), page, '/prestamos')
    expect(screen.getByRole('heading', { name: 'Acceso restringido' })).toBeInTheDocument()
    expect(screen.queryByText('Contenido de préstamos')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('core', '/security/denied-route', {
        route: '/prestamos',
        module: 'prestamos',
      }),
    )
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('renders the module for an allowed role without reporting', () => {
    const { post } = setup(staff('Riesgos'), page, '/prestamos')
    expect(screen.getByText('Contenido de préstamos')).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it('uses the active role when the user has several', () => {
    // Entra users can hold several roles; the first known one is active by default.
    setup({ ...staff('Riesgos'), roles: ['Marketing', 'Riesgos'] }, page, '/prestamos')
    expect(screen.getByText('Contenido de préstamos')).toBeInTheDocument()
  })
})
