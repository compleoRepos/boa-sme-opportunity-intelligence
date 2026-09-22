import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppErrorBoundary } from './AppErrorBoundary'

function BrokenView(): never {
  throw new Error('synthetic render failure')
}

describe('AppErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('remplace une exception de rendu par une page de récupération', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    render(<AppErrorBoundary><BrokenView /></AppErrorBoundary>)

    expect(screen.getByRole('alert')).toHaveTextContent("Cette page n’a pas pu être affichée")
    expect(screen.getByRole('button', { name: 'Recharger la page' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revenir au cockpit' })).toHaveAttribute('href', '/')
  })
})
