import { render, screen } from '@testing-library/react'

import { Button } from './button'

describe('Button', () => {
  it('renders a child link with button styles when asChild is set', () => {
    render(
      <Button asChild>
        <a href="/registro">Abrir mi cuenta</a>
      </Button>,
    )
    const link = screen.getByRole('link', { name: 'Abrir mi cuenta' })
    expect(link).toHaveAttribute('href', '/registro')
    expect(link.className).toContain('rounded-lg')
  })

  it('shows a spinner and disables itself while loading', () => {
    render(<Button loading>Pagar</Button>)
    const button = screen.getByRole('button', { name: 'Pagar' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })
})
