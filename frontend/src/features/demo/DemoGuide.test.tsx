import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { DEMO_ACTS, DemoLauncher, DemoProvider } from './DemoGuide'

function renderGuide() {
  return render(
    <MemoryRouter>
      <DemoProvider><DemoLauncher /></DemoProvider>
    </MemoryRouter>,
  )
}

describe('DemoGuide', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('affiche six actes et conserve la progression après remontage', async () => {
    const view = renderGuide()
    fireEvent.click(screen.getByRole('button', { name: 'Démo 0/6' }))

    expect(screen.getByRole('complementary', { name: 'Parcours de démonstration' })).toBeInTheDocument()
    for (const act of DEMO_ACTS) expect(screen.getByRole('button', { name: new RegExp(act.title) })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Marquer terminé' }))
    await waitFor(() => expect(window.localStorage.getItem('boa-sme-demo-progress-v1')).toContain('cc-dashboard'))

    view.unmount()
    renderGuide()
    expect(screen.getByRole('button', { name: 'Démo 1/6' })).toBeInTheDocument()
  })

  it('réinitialise la progression après confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderGuide()
    fireEvent.click(screen.getByRole('button', { name: 'Démo 0/6' }))
    fireEvent.click(screen.getByRole('button', { name: 'Marquer terminé' }))
    fireEvent.click(screen.getByRole('button', { name: 'Réinitialiser la progression' }))

    await waitFor(() => expect(window.localStorage.getItem('boa-sme-demo-progress-v1')).toBe('[]'))
    expect(screen.getByRole('button', { name: 'Marquer terminé' })).toBeEnabled()
  })
})
