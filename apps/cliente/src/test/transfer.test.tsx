import { ApiError } from '@chaski/shared'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { TransferPage, validateTransfer } from '../pages/Transfer'
import { fakeApi, renderWithProviders } from './render'

const ACCOUNT = {
  id: 'acc-1',
  number: '200-3000000001',
  product: 'AHORRO_SOLES',
  currency: 'PEN',
  balance: 500,
  status: 'ACTIVA',
  opened_at: '2026-01-01T00:00:00Z',
}
const RECEIPT = {
  transaction_id: 'abcdef12-0000-4000-8000-000000000000',
  operation: 'TRANSFERENCIA',
  amount: 150,
  currency: 'PEN',
  from_account_number: ACCOUNT.number,
  to_account_number: '200-3000000099',
  internal: true,
  new_balance: 350,
  created_at: '2026-10-01T15:00:00Z',
}

describe('validateTransfer', () => {
  it('accepts internal numbers and 20-digit CCI', () => {
    expect(validateTransfer({ to: '200-3000000001', amount: '10' }, 100)).toEqual({})
    expect(validateTransfer({ to: '0'.repeat(20), amount: '10.50' }, 100)).toEqual({})
  })
  it('rejects bad destination, amounts and insufficient balance', () => {
    expect(validateTransfer({ to: '123', amount: '10' }, 100).to).toBeDefined()
    expect(validateTransfer({ to: '0'.repeat(20), amount: '-1' }, 100).amount).toBe(
      'Ingresa un monto válido',
    )
    expect(validateTransfer({ to: '0'.repeat(20), amount: '1.234' }, 100).amount).toBe(
      'Máximo 2 decimales',
    )
    expect(validateTransfer({ to: '0'.repeat(20), amount: '101' }, 100).amount).toBe(
      'Saldo insuficiente',
    )
  })
})

describe('TransferPage', () => {
  it('asks for confirmation, sends an Idempotency-Key and shows the receipt', async () => {
    const user = userEvent.setup()
    const { api, calls } = fakeApi((_s, path) => {
      if (path === '/accounts/me') return [ACCOUNT]
      if (path === '/transfers') return RECEIPT
      throw new Error(`unexpected ${path}`)
    })
    renderWithProviders(<TransferPage />, { api })

    await user.type(await screen.findByLabelText('Cuenta destino o CCI'), '200-3000000099')
    await user.type(screen.getByLabelText('Monto (PEN)'), '150')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    // Nothing is posted until the customer confirms.
    expect(calls.some((c) => c.path === '/transfers')).toBe(false)
    expect(
      await screen.findByRole('dialog', { name: 'Confirma tu transferencia' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Transferir' }))

    expect(await screen.findByText('Transferencia exitosa')).toBeInTheDocument()
    expect(screen.getByText('S/ 350.00')).toBeInTheDocument()
    const post = calls.find((c) => c.path === '/transfers')!
    expect(post.options.body).toMatchObject({
      from_account_id: 'acc-1',
      to_account_number: '200-3000000099',
      amount: '150',
    })
    expect((post.options.headers as Record<string, string>)['Idempotency-Key']).toMatch(
      /[0-9a-f-]{36}/,
    )
  })

  it('reuses the same Idempotency-Key when retrying after an error', async () => {
    const user = userEvent.setup()
    let attempt = 0
    const { api, calls } = fakeApi((_s, path) => {
      if (path === '/accounts/me') return [ACCOUNT]
      attempt += 1
      if (attempt === 1) throw new ApiError(0, 'No pudimos conectarnos. Revisa tu conexión.', null)
      return RECEIPT
    })
    renderWithProviders(<TransferPage />, { api })
    await user.type(await screen.findByLabelText('Cuenta destino o CCI'), '200-3000000099')
    await user.type(screen.getByLabelText('Monto (PEN)'), '150')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await user.click(await screen.findByRole('button', { name: 'Transferir' }))
    expect(
      await screen.findByText('No pudimos conectarnos. Revisa tu conexión.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Transferir' }))
    await waitFor(() => expect(screen.getByText('Transferencia exitosa')).toBeInTheDocument())

    const keys = calls
      .filter((c) => c.path === '/transfers')
      .map((c) => (c.options.headers as Record<string, string>)['Idempotency-Key'])
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  it('validates before opening the confirmation', async () => {
    const user = userEvent.setup()
    const { api } = fakeApi(() => [ACCOUNT])
    renderWithProviders(<TransferPage />, { api })
    await user.type(await screen.findByLabelText('Cuenta destino o CCI'), '200-3000000099')
    await user.type(screen.getByLabelText('Monto (PEN)'), '9999')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByText('Saldo insuficiente')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
