import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { Opportunity } from '../api/types'
import { OpportunityCard } from './OpportunityCard'
import { EmptyState, ErrorState } from './UI'

const opportunity: Opportunity = {
  opportunityId: 'OPP-TEST-1',
  customerId: 'SME-TEST-1',
  customerName: 'Société de test',
  opportunityType: 'INVESTMENT_FINANCING',
  status: 'OPEN',
  confidence: 0.86,
  confidenceLevel: 'HIGH',
  priorityScore: 91,
  priorityLevel: 'P1',
  horizon: '1-3_MONTHS',
  why: ['Encaissements en progression'],
  what: 'Besoin potentiel',
  when: 'Dans les trois mois',
  generatedAt: '2026-09-18T08:00:00Z',
}

describe('OpportunityCard', () => {
  it('rend les données reçues et un lien fonctionnel vers le détail', () => {
    render(<MemoryRouter><OpportunityCard opportunity={opportunity} /></MemoryRouter>)
    expect(screen.getByText('Société de test')).toBeInTheDocument()
    expect(screen.getByText("Financement d’investissement")).toBeInTheDocument()
    expect(screen.getByLabelText('Confiance 86 pour cent')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Examiner/i })).toHaveAttribute('href', '/opportunites/OPP-TEST-1')
  })
})

describe('états de requête', () => {
  it('affiche un état vide explicite', () => {
    render(<EmptyState title="Aucun résultat" message="Modifiez vos filtres." />)
    expect(screen.getByText('Aucun résultat')).toBeInTheDocument()
    expect(screen.getByText('Modifiez vos filtres.')).toBeInTheDocument()
  })

  it('affiche le code de corrélation d’une erreur Gateway', () => {
    render(<ErrorState error={new ApiError(503, { code: 'DEPENDENCY_UNAVAILABLE', message: 'Service indisponible', correlationId: 'corr-test-123' })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Service indisponible')
    expect(screen.getByText(/corr-test-123/)).toBeInTheDocument()
  })
})
