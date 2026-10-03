import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { OnboardingPage } from '../pages/Onboarding'

import { fakeApi, renderWithProviders } from './render'

it('si la consulta no trae nombres se pueden escribir a mano', async () => {
  const { api } = fakeApi((_s, path) => {
    if (path.startsWith('/onboarding/lookup-dni/')) {
      return { found: false, available: true, nombres: null, apellidos: null, fuente: 'APISPERU' }
    }
    return null
  })
  renderWithProviders(<OnboardingPage />, { api, user: null })
  await userEvent.type(screen.getByLabelText('DNI'), '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Consultar' }))
  expect(screen.getByLabelText('Nombres')).toHaveValue('')
  await userEvent.type(screen.getByLabelText('Nombres'), 'Rosa')
  await userEvent.type(screen.getByLabelText('Apellidos'), 'Mamani')
  expect(screen.getByLabelText('Nombres')).toHaveValue('Rosa')
  expect(screen.getByLabelText('Apellidos')).toHaveValue('Mamani')
})

it('consultar DNI rellena nombres y apellidos', async () => {
  const { api } = fakeApi((_s, path) => {
    if (path === '/onboarding/lookup-dni/45678912') {
      return {
        found: true,
        available: true,
        nombres: 'Rosa',
        apellidos: 'Mamani Quispe',
        fuente: 'MOCK',
      }
    }
    return null
  })
  renderWithProviders(<OnboardingPage />, { api, user: null })
  await userEvent.type(screen.getByLabelText('DNI'), '45678912')
  await userEvent.click(screen.getByRole('button', { name: 'Consultar' }))
  expect(screen.getByLabelText('Nombres')).toHaveValue('Rosa')
  expect(screen.getByLabelText('Apellidos')).toHaveValue('Mamani Quispe')
})
