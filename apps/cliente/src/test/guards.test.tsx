import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'

import { RequireCustomer } from '../components/Layout'
import { validatePersonal } from '../pages/Onboarding'
import { fakeApi, renderWithProviders } from './render'

function Protected() {
  return (
    <Routes>
      <Route path="/bienvenida" element={<p>Pantalla de bienvenida</p>} />
      <Route
        path="/"
        element={
          <RequireCustomer>
            <p>Zona de clientes</p>
          </RequireCustomer>
        }
      />
    </Routes>
  )
}

describe('RequireCustomer', () => {
  const { api } = fakeApi(() => null)

  it('sends anonymous users to the welcome screen', () => {
    renderWithProviders(<Protected />, { api, user: null })
    expect(screen.getByText('Pantalla de bienvenida')).toBeInTheDocument()
  })

  it('blocks staff users from the customer app', () => {
    renderWithProviders(<Protected />, {
      api,
      user: { sub: 'admin', name: 'Admin', roles: ['Admin'], customerId: null },
    })
    expect(screen.queryByText('Zona de clientes')).not.toBeInTheDocument()
    expect(screen.getByText(/Esta aplicación es para clientes/)).toBeInTheDocument()
  })

  it('lets customers in', () => {
    renderWithProviders(<Protected />, { api })
    expect(screen.getByText('Zona de clientes')).toBeInTheDocument()
  })
})

describe('validatePersonal', () => {
  const ok = {
    first_name: 'Rosa',
    last_name: 'Mamani',
    document_number: '45678912',
    birth_date: '1994-03-21',
    email: 'rosa@gmail.com',
    phone: '987654321',
    region: 'Cusco',
    monthly_income: '',
  }
  it('accepts valid data', () => {
    expect(validatePersonal(ok)).toEqual({})
  })
  it('flags DNI, phone, email and minors', () => {
    const e = validatePersonal({
      ...ok,
      document_number: '123',
      phone: '12345',
      email: 'x',
      birth_date: '2015-01-01',
    })
    expect(Object.keys(e).sort()).toEqual(['birth_date', 'document_number', 'email', 'phone'])
  })
})
