import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Customer } from '../../api/types'
import { FlowVisibilityBadge, FlowVisibilityDrawer } from './FlowVisibilityPanel'

const hooks = vi.hoisted(() => ({ useDeclareBankingRelationship: vi.fn() }))
vi.mock('../../api/hooks', () => hooks)

const customer: Customer = {
  customerId: 'SME-00482',
  legalName: 'Atlas Multibanque SARL',
  bankingRelationship: 'SECONDARY',
  bankingRelationshipDeclaration: {
    value: 'SECONDARY',
    declaredAt: '2026-09-21T10:30:00Z',
    declaredBy: 'ahmed.mansouri',
    reason: 'Entretien annuel avec la PME',
    source: 'RELATIONSHIP_MANAGER',
  },
  flowVisibility: {
    level: 'LOW',
    estimatedShare: 0.25,
    method: 'TURNOVER_RATIO',
    asOf: '2026-09-20',
    evidence: [
      { fact: 'BANKING_RELATIONSHIP_DECLARED', observedOn: '2026-09-21' },
      { fact: 'TRANSACTION_FINGERPRINTS', value: { count: 2, confidence: 0.8 } },
    ],
  },
}

const mutation = {
  mutate: vi.fn(),
  data: undefined,
  error: null,
  isError: false,
  isPending: false,
  isSuccess: false,
}

beforeEach(() => {
  mutation.mutate.mockReset()
  hooks.useDeclareBankingRelationship.mockReturnValue(mutation)
})

describe('FlowVisibilityBadge', () => {
  it('affiche le niveau faible et ouvre le panneau adressable via son callback', async () => {
    const open = vi.fn()
    render(<FlowVisibilityBadge visibility={customer.flowVisibility} onClick={open} />)
    const badge = screen.getByRole('button', { name: 'Ouvrir la visibilité des flux : faible' })
    expect(badge).toHaveTextContent('Visibilité des flux : faible')
    await userEvent.click(badge)
    expect(open).toHaveBeenCalledOnce()
  })
})

describe('FlowVisibilityDrawer', () => {
  it('rend méthode, part, date, évidence et déclaration auteur/date', () => {
    render(<FlowVisibilityDrawer customer={customer} canDeclare onClose={vi.fn()} />)
    expect(screen.getByRole('dialog', { name: /Visibilité des flux/ })).toBeInTheDocument()
    expect(screen.getByText('Rapport encaissements / chiffre d’affaires')).toBeInTheDocument()
    expect(screen.getByText('25 %')).toBeInTheDocument()
    expect(screen.getByText(/Relation bancaire déclarée/)).toBeInTheDocument()
    expect(screen.getByText(/Empreintes de multibancarisation/)).toHaveTextContent('"confidence": 0.8')
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
    expect(screen.getByText(/ahmed\.mansouri/)).toHaveTextContent('Motif : Entretien annuel avec la PME')
  })

  it('réserve le formulaire aux rôles autorisés et envoie relation, motif et chiffre d’affaires', async () => {
    const user = userEvent.setup()
    render(<FlowVisibilityDrawer customer={customer} canDeclare onClose={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Déclarer la relation bancaire' }))
    await user.selectOptions(screen.getByLabelText('Relation bancaire'), 'PRIMARY')
    await user.type(screen.getByLabelText('Motif'), 'Déclaration confirmée pendant la revue commerciale')
    fireEvent.change(screen.getByLabelText(/Chiffre d’affaires déclaré/), { target: { value: '12000000' } })
    await user.click(screen.getByRole('button', { name: 'Enregistrer la déclaration' }))
    expect(mutation.mutate).toHaveBeenCalledWith(expect.objectContaining({
      bankingRelationship: 'PRIMARY',
      reason: 'Déclaration confirmée pendant la revue commerciale',
      declaredTurnover: 12_000_000,
    }), expect.objectContaining({ onSuccess: expect.any(Function) }))
  })

  it('ne propose aucune édition hors rôle autorisé', () => {
    render(<FlowVisibilityDrawer customer={customer} canDeclare={false} onClose={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Déclarer la relation bancaire' })).not.toBeInTheDocument()
    expect(screen.getByText(/réservée au chargé de clientèle/)).toBeInTheDocument()
  })
})
