import { axeViolations } from '@chaski/shared/testing/axe'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { CardsPage } from '../pages/Cards'
import { ComplaintsPage } from '../pages/Complaints'
import { LoansPage } from '../pages/Loans'
import { OnboardingPage } from '../pages/Onboarding'
import { TransferPage } from '../pages/Transfer'
import { WelcomePage } from '../pages/Welcome'
import { fakeApi, renderWithProviders } from './render'

const DATA: Record<string, unknown> = {
  '/accounts/me': [
    {
      id: 'a1',
      number: '200-3000000001',
      product: 'AHORRO_SOLES',
      currency: 'PEN',
      balance: 500,
      status: 'ACTIVA',
      opened_at: '2026-01-01',
    },
  ],
  '/cards/me': [
    {
      id: 'c1',
      account_id: 'a1',
      type: 'DEBITO',
      brand: 'VISA',
      last4: '1234',
      credit_limit: null,
      status: 'ACTIVA',
    },
  ],
  '/loans/me': [],
  '/loans/quote': {
    amount: 5000,
    term_months: 24,
    rate_tea: 0.35,
    monthly_payment: 280.57,
    total_payment: 6733.68,
  },
  '/complaints/me': [],
  '/dev/users': {
    staff: [],
    customers: [
      { customer_id: 'x', name: 'Rosa Mamani', segment: 'MASIVO', kyc_status: 'APROBADO' },
    ],
  },
}
const api = () => fakeApi((_s, path) => DATA[path] ?? null).api

async function expectAccessible(ui: React.ReactElement, ready: string, anonymous = false) {
  const { container } = renderWithProviders(ui, {
    api: api(),
    ...(anonymous ? { user: null } : {}),
  })
  await screen.findAllByText(ready)
  expect(await axeViolations(container)).toEqual([])
  return container
}

describe('accessibility (axe)', () => {
  it('welcome', async () => {
    await expectAccessible(<WelcomePage />, 'Rosa Mamani', true)
  })
  it('onboarding step 1 and its validation errors', async () => {
    const { container } = renderWithProviders(<OnboardingPage />, { api: api(), user: null })
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByLabelText('DNI')).toHaveAttribute('aria-invalid', 'true')
    expect(await axeViolations(container)).toEqual([])
  })
  it('transfer', async () => {
    await expectAccessible(<TransferPage />, 'Transferir')
  })
  it('cards', async () => {
    await expectAccessible(<CardsPage />, 'Activa')
  })
  it('loans', async () => {
    await expectAccessible(<LoansPage />, 'Préstamo personal')
  })
  it('complaints', async () => {
    await expectAccessible(<ComplaintsPage />, 'Libro de reclamaciones')
  })
})
