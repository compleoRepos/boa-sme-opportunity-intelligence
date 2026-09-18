import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, vi } from 'vitest'
import type { BranchDashboard, CustomerPropensity, RelationshipManagerDashboard as RelationshipManagerDashboardData } from '../api/types'
import { BranchManagerDashboard, RelationshipManagerDashboard } from './DashboardPage'
import { Customer360Page } from './Customer360Page'

const hooks = vi.hoisted(() => ({
  useRelationshipManagerDashboard: vi.fn(),
  useBranchDashboard: vi.fn(),
  useCustomer: vi.fn(),
  useCustomerAccounts: vi.fn(),
  useCustomerProducts: vi.fn(),
  useCustomerTransactions: vi.fn(),
  useCustomerMetrics: vi.fn(),
  useCustomerSignals: vi.fn(),
  useCustomerOpportunities: vi.fn(),
  useCustomerActions: vi.fn(),
  useCustomerPropensity: vi.fn(),
}))

vi.mock('../api/hooks', () => hooks)

const query = <T,>(data: T) => ({
  data,
  isPending: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
})

const rmDashboard: RelationshipManagerDashboardData = {
  scope: { type: 'RELATIONSHIP_MANAGER', relationshipManagerId: 'RM-01', relationshipManagerName: 'Amina El Idrissi', branchName: 'Agence Rabat' },
  kpis: { portfolioCustomers: 1, highPriorityCustomers: 1, openOpportunities: 1, actionsDue: 1 },
  priorityDistribution: [{ priorityLevel: 'P1', count: 1, share: 1 }],
  portfolio: [{
    customerId: 'SME-001',
    customerName: 'Atlas Industrie',
    industry: 'MANUFACTURING',
    propensityScore: 0.84,
    priorityLevel: 'P1',
    priorityReason: 'Croissance soutenue des encaissements.',
    openOpportunities: [{ opportunityId: 'OPP-01', opportunityType: 'INVESTMENT_FINANCING', confidence: 0.88 }],
    nextActions: [{ actionId: 'ACT-01', actionType: 'CONTACT_CUSTOMER', dueAt: '2026-09-20T09:00:00Z' }],
  }],
}

const branchDashboard: BranchDashboard = {
  scope: { type: 'BRANCH', branchId: 'BR-01', branchName: 'Agence Rabat Centre' },
  kpis: { portfolioCustomers: 42, highPriorityCustomers: 8, openOpportunities: 17, actionsDue: 6, convertedOpportunities: 5, conversionRate: 0.25 },
  priorityDistribution: [{ priorityLevel: 'P1', count: 8, share: 0.19 }, { priorityLevel: 'P2', count: 14, share: 0.33 }, { priorityLevel: 'P3', count: 20, share: 0.48 }],
  conversionFunnel: [{ stage: 'CONTACTED', count: 20, rate: 1 }, { stage: 'CONVERTED', count: 5, rate: 0.25 }],
  relationshipManagers: [{ relationshipManagerId: 'RM-01', relationshipManagerName: 'Amina El Idrissi', portfolioCustomers: 20, highPriorityCustomers: 4, openOpportunities: 9, actionsDue: 2, convertedOpportunities: 3, conversionRate: 0.3 }],
}

const propensity: CustomerPropensity = {
  customerId: 'SME-001',
  score: 0.84,
  scoreMeaning: 'intérêt commercial estimé',
  priorityLevel: 'P1',
  model: { modelId: 'sme-propensity', modelVersion: '2.4.0', featureSetVersion: 'features-2026-09' },
  combination: { method: 'HYBRID_ML_RULES', mlScore: 0.86, rulesScore: 0.8, mlWeight: 0.7, rulesWeight: 0.3, summary: 'ML complété par les règles métier actives.' },
  factors: [{ feature: 'inflow_growth_90d', label: 'Croissance des encaissements', value: 0.31, direction: 'POSITIVE', contribution: 0.18, explanation: 'Les encaissements progressent sur 90 jours.', source: 'Analytics' }],
}

beforeEach(() => {
  vi.clearAllMocks()
  hooks.useRelationshipManagerDashboard.mockReturnValue(query(rmDashboard))
  hooks.useBranchDashboard.mockReturnValue(query(branchDashboard))
  hooks.useCustomer.mockReturnValue(query({ customerId: 'SME-001', legalName: 'Atlas Industrie', industry: 'MANUFACTURING', sector: 'INDUSTRY', segment: 'SME', status: 'ACTIVE', relationshipManagerName: 'Amina El Idrissi', branchId: 'BR-01' }))
  hooks.useCustomerAccounts.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerProducts.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerTransactions.mockReturnValue(query({ data: [], meta: { pageSize: 10, hasMore: false } }))
  hooks.useCustomerMetrics.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerSignals.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerOpportunities.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerActions.mockReturnValue(query({ data: [], meta: { pageSize: 100, hasMore: false } }))
  hooks.useCustomerPropensity.mockReturnValue(query(propensity))
})

describe('dashboard chargé de clientèle', () => {
  it('affiche uniquement le portefeuille retourné par /dashboards/me et ses actions', () => {
    render(<MemoryRouter><RelationshipManagerDashboard /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: /voici vos priorités/i })).toBeInTheDocument()
    expect(screen.getByText('Atlas Industrie')).toBeInTheDocument()
    expect(screen.getByLabelText('Propension commerciale 84 pour cent')).toBeInTheDocument()
    expect(screen.getByText('Contact client')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ouvrir la fiche PME/i })).toHaveAttribute('href', '/clients/SME-001')
  })
})

describe('dashboard responsable agence', () => {
  it('affiche les KPIs par CC, les conversions et l’accès au portefeuille', () => {
    render(<MemoryRouter><BranchManagerDashboard /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Agence Rabat Centre' })).toBeInTheDocument()
    expect(screen.getByText('Amina El Idrissi')).toBeInTheDocument()
    expect(screen.getByText('Progression commerciale')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Accéder au portefeuille de Amina/i })).toHaveAttribute('href', '/portefeuilles/RM-01?name=Amina%20El%20Idrissi')
  })
})

describe('fiche PME et propension', () => {
  it('rend le score borné, les versions, la combinaison hybride et le garde-fou crédit', () => {
    render(<MemoryRouter initialEntries={['/clients/SME-001']}><Routes><Route path="/clients/:customerId" element={<Customer360Page />} /></Routes></MemoryRouter>)
    expect(screen.getByText('0.84')).toBeInTheDocument()
    expect(screen.getByText('2.4.0')).toBeInTheDocument()
    expect(screen.getByText('features-2026-09')).toBeInTheDocument()
    expect(screen.getByText('Croissance des encaissements')).toBeInTheDocument()
    expect(screen.getByText('Règles métier')).toBeInTheDocument()
    expect(screen.getByText('Aucune décision de crédit')).toBeInTheDocument()
  })
})
