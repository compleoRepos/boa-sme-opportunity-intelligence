import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Modal } from './Modal'
import { Tabs, tabId } from './Tabs'
import { ToastProvider, useToast } from './Toast'

function ModalFixture() {
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" onClick={() => setOpen(true)}>Ouvrir</button>
    {open && <Modal title="Test clavier" onClose={() => setOpen(false)} footer={<button type="button">Confirmer</button>}>
      <label>Nom<input data-autofocus /></label>
    </Modal>}
  </>
}

function TabsFixture() {
  const [value, setValue] = useState('one')
  return <>
    <Tabs
      value={value}
      onChange={setValue}
      ariaLabel="Sections"
      panelId="test-panel"
      items={[{ id: 'one', label: 'Premier' }, { id: 'two', label: 'Deuxième' }]}
    />
    <div id="test-panel" role="tabpanel" aria-labelledby={tabId('test-panel', value)}>{value}</div>
  </>
}

function ToastFixture() {
  const toast = useToast()
  const [open, setOpen] = useState(true)
  return open && <Modal title="Dialogue avec annonce" onClose={() => setOpen(false)}>
    <button type="button" onClick={() => toast.push('success', 'Action annoncée')}>Notifier</button>
  </Modal>
}

function NestedModalFixture() {
  const [outerOpen, setOuterOpen] = useState(false)
  const [innerOpen, setInnerOpen] = useState(false)
  return <>
    <button type="button" onClick={() => setOuterOpen(true)}>Ouvrir le parent</button>
    {outerOpen && <Modal title="Dialogue parent" onClose={() => setOuterOpen(false)}>
      <button type="button" onClick={() => setInnerOpen(true)}>Ouvrir le dialogue imbriqué</button>
      {innerOpen && <Modal title="Dialogue imbriqué" onClose={() => setInnerOpen(false)}>
        <button type="button">Action imbriquée</button>
      </Modal>}
    </Modal>}
  </>
}

function ExistingToastFixture() {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" onClick={() => toast.push('success', 'Annonce préalable')}>Annoncer avant</button>
    <button type="button" onClick={() => setOpen(true)}>Ouvrir après</button>
    {open && <Modal title="Dialogue après annonce" onClose={() => setOpen(false)}><button type="button">Action</button></Modal>}
  </>
}

describe('accessibilité des primitives interactives', () => {
  it('piège le focus dans la modale, ferme avec Échap et restaure le déclencheur', async () => {
    const user = userEvent.setup()
    render(<ModalFixture />)
    const trigger = screen.getByRole('button', { name: 'Ouvrir' })
    await user.click(trigger)
    const input = screen.getByRole('textbox', { name: 'Nom' })
    await waitFor(() => expect(input).toHaveFocus())

    screen.getByRole('button', { name: 'Fermer' }).focus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Confirmer' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('déplace la sélection des onglets avec les flèches et Home', async () => {
    const user = userEvent.setup()
    render(<TabsFixture />)
    const first = screen.getByRole('tab', { name: 'Premier' })
    const second = screen.getByRole('tab', { name: 'Deuxième' })
    first.focus()

    await user.keyboard('{ArrowRight}')
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('aria-selected', 'true')
    expect(second).toHaveAttribute('aria-controls', 'test-panel')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', second.id)
    expect(first).toHaveAttribute('tabindex', '-1')

    await user.keyboard('{Home}')
    expect(first).toHaveFocus()
    expect(first).toHaveAttribute('aria-selected', 'true')
  })

  it('rend le live region Toast hors du sous-arbre applicatif inertable', async () => {
    const user = userEvent.setup()
    const view = render(<ToastProvider><ToastFixture /></ToastProvider>)

    await user.click(screen.getByRole('button', { name: 'Notifier' }))
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Action annoncée')
    expect(view.container).not.toContainElement(status)
    expect(status.closest('.toast-stack')?.parentElement).toBe(document.body)
    const dismiss = screen.getByRole('button', { name: 'Fermer la notification' })
    expect(dismiss).toHaveAttribute('tabindex', '-1')
    dismiss.focus()
    expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement)
    expect(dismiss).not.toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(dismiss).toHaveAttribute('tabindex', '0')
  })

  it('ferme uniquement le dialogue supérieur avec Échap', async () => {
    const user = userEvent.setup()
    render(<NestedModalFixture />)

    await user.click(screen.getByRole('button', { name: 'Ouvrir le parent' }))
    const openInner = screen.getByRole('button', { name: 'Ouvrir le dialogue imbriqué' })
    await user.click(openInner)
    expect(screen.getAllByRole('dialog', { hidden: true })).toHaveLength(2)
    const parent = screen.getByText('Dialogue parent').closest('[role="dialog"]')
    expect(parent).not.toBeNull()
    expect(parent).toHaveAttribute('aria-hidden', 'true')
    expect(parent).toHaveProperty('inert', true)
    const inner = screen.getByRole('dialog', { name: 'Dialogue imbriqué' })
    await waitFor(() => expect(inner).toContainElement(document.activeElement as HTMLElement))
    openInner.focus()
    expect(inner).toContainElement(document.activeElement as HTMLElement)

    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog', { name: 'Dialogue parent' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Dialogue imbriqué' })).not.toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('retire aussi un Toast préexistant du parcours Tab pendant un dialogue', async () => {
    const user = userEvent.setup()
    render(<ToastProvider><ExistingToastFixture /></ToastProvider>)
    await user.click(screen.getByRole('button', { name: 'Annoncer avant' }))
    const dismiss = screen.getByRole('button', { name: 'Fermer la notification' })
    expect(dismiss).toHaveAttribute('tabindex', '0')

    await user.click(screen.getByRole('button', { name: 'Ouvrir après' }))
    expect(dismiss).toHaveAttribute('tabindex', '-1')
    await user.keyboard('{Escape}')
    expect(dismiss).toHaveAttribute('tabindex', '0')
  })
})
