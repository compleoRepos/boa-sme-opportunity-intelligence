import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RelationshipManagerDashboard } from '../../api/types'
import { ToastProvider } from '../../ui'
import { CcDashboardPage, selectCustomers } from './CcDashboardPage'

const hooks = vi.hoisted(() => ({ useRelationshipManagerDashboard: vi.fn() }))
vi.mock('../../api/hooks', () => hooks)
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ hasRole: (role: string) => role === 'RELATIONSHIP_MANAGER', roles: ['RELATIONSHIP_MANAGER'], devMode: false }) }))

const dashboard: RelationshipManagerDashboard = {
  scope: { type: 'RELATIONSHIP_MANAGER', relationshipManagerId: 'rm-01', relationshipManagerName: 'Ahmed Mansouri', branchId: 'BR-01', branchName: 'Casablanca Anfa' },
  kpis: { portfolioCustomers: 3, highPriorityCustomers: 1, openOpportunities: 2, actionsDue: 1 },
  priorityDistribution: [{ priorityLevel: 'P1', count: 1, share: 0.34 }, { priorityLevel: 'P2', count: 1, share: 0.33 }, { priorityLevel: 'P4', count: 1, share: 0.33 }],
  portfolio: [
    { customerId: 'SME-00001', customerName: 'Atlas Métal Industrie SAS', industry: 'INDUSTRIE', branchName: 'Casablanca Anfa', propensityScore: 0.87, combinedPriorityScore: 0.9, priorityLevel: 'P1', flowVisibility: { level: 'HIGH', method: 'DECLARED' }, openOpportunities: [{ opportunityId: 'OPP-1', opportunityType: 'INVESTMENT_FINANCING', confidence: 0.94, priorityScore: 90, why: ['Inflow growth: observed=0.32, condition=gt 0.25', 'Supplier payment growth: observed=0.24, condition=gt 0.2'], recommendedProducts: [{ productId: 'INVESTMENT_FINANCING', name: 'Investment Financing' }], generatedAt: '2026-09-30T00:00:00Z' }], nextActions: [] },
    { customerId: 'SME-00002', customerName: 'Rif Trading SARL', industry: 'IMPORT_EXPORT', propensityScore: 0.61, combinedPriorityScore: 0.62, priorityLevel: 'P2', flowVisibility: { level: 'LOW', estimatedShare: 0.25, method: 'TURNOVER_RATIO' }, openOpportunities: [{ opportunityId: 'OPP-2', opportunityType: 'TRADE_FINANCE', confidence: 0.7 }], nextActions: [{ actionType: 'CONTACT_CUSTOMER', dueAt: '2026-10-02T09:00:00Z' }] },
    { customerId: 'SME-00003', customerName: 'Souss Agri SARL', industry: 'AGRICULTURE', propensityScore: 0.2, combinedPriorityScore: 0.2, priorityLevel: 'P4', openOpportunities: [], nextActions: [] },
  ],
}

beforeEach(() => { hooks.useRelationshipManagerDashboard.mockReturnValue({ data: dashboard, isPending: false, isError: false, error: null, refetch: vi.fn() }) })

const renderDashboard = () => render(<MemoryRouter><ToastProvider><CcDashboardPage /></ToastProvider></MemoryRouter>)

describe('selectCustomers', () => {
  it('filtre « aujourd’hui » sur P1 et actions planifiées, trié par priorité règles', () => {
    expect(selectCustomers(dashboard, 'today', '', 'priority').map((item) => item.customerId)).toEqual(['SME-00001', 'SME-00002'])
    expect(selectCustomers(dashboard, 'all', 'agri', 'name').map((item) => item.customerId)).toEqual(['SME-00003'])
    expect(selectCustomers(dashboard, 'limitedVisibility', '', 'priority').map((item) => item.customerId)).toEqual(['SME-00002'])
  })

  it('ne départage pas une égalité de priorité avec la propension shadow', () => {
    const tied: RelationshipManagerDashboard = {
      ...dashboard,
      portfolio: [
        { ...dashboard.portfolio[0]!, propensityScore: 0.01, combinedPriorityScore: 0.5 },
        { ...dashboard.portfolio[1]!, propensityScore: 0.99, combinedPriorityScore: 0.5 },
      ],
    }
    expect(selectCustomers(tied, 'all', '', 'priority').map((item) => item.customerId)).toEqual(['SME-00001', 'SME-00002'])
  })
})

describe('CcDashboardPage', () => {
  it('rend les KPI, les signaux chiffrés et le lien vers la fiche PME', () => {
    renderDashboard()
    expect(screen.getByRole('heading', { name: /Bon.* Ahmed/ })).toBeInTheDocument()
    expect(screen.getByText('Atlas Métal Industrie SAS')).toBeInTheDocument()
    expect(screen.getByText((_, node) => Boolean(node?.tagName === 'B' && node.textContent?.replace(/\u202f|\u00a0/g, ' ') === '+32 %'))).toBeInTheDocument()
    expect(screen.getByText('Investment Financing')).toBeInTheDocument()
    expect(screen.getByLabelText(/Propension 87/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ouvrir la fiche de Atlas/ })).toHaveAttribute('href', '/clients/SME-00001')
  })

  it('bascule la file quand un KPI est cliqué', () => {
    renderDashboard()
    fireEvent.click(screen.getByRole('button', { name: /Clients PME/ }))
    expect(screen.getByText('Souss Agri SARL')).toBeInTheDocument()
  })
})
