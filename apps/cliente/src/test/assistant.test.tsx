import { ApiError } from '@chaski/shared'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AssistantChat } from '../components/AssistantChat'
import { fakeApi, renderWithProviders } from './render'

describe('AssistantChat', () => {
  it('runs a sensitive action only after the customer confirms', async () => {
    const user = userEvent.setup()
    const { api, calls } = fakeApi((_s, path) => {
      if (path === '/assistant/chat') {
        return {
          reply: 'Puedo bloquear tu tarjeta •••• 1234.',
          pending_action: {
            tool: 'block_card',
            args: { card_id: 'card-1' },
            summary: 'Bloquear tarjeta •••• 1234',
          },
        }
      }
      if (path === '/cards/card-1/block') return { id: 'card-1', status: 'BLOQUEADA' }
      throw new Error(path)
    })
    renderWithProviders(<AssistantChat />, { api })
    await user.click(screen.getByRole('button', { name: 'Abrir Chaski Asistente' }))
    await user.type(screen.getByLabelText('Escribe tu mensaje'), 'bloquea mi tarjeta')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByText('Bloquear tarjeta •••• 1234')).toBeInTheDocument()
    expect(calls.some((c) => c.path.includes('/block'))).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('Listo, tu tarjeta quedó bloqueada.')).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/cards/card-1/block')).toHaveLength(1)
  })

  it('shows a friendly message while ia-api is not available', async () => {
    const user = userEvent.setup()
    const { api } = fakeApi(() => {
      throw new ApiError(404, 'Not Found', null)
    })
    renderWithProviders(<AssistantChat />, { api })
    await user.click(screen.getByRole('button', { name: 'Abrir Chaski Asistente' }))
    await user.click(screen.getByRole('button', { name: '¿Cuál es mi saldo?' }))
    expect(await screen.findByText(/El asistente estará disponible pronto/)).toBeInTheDocument()
  })
})
