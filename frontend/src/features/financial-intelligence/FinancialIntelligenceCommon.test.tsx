import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FiResponseMeta } from '../../api/financialIntelligence.types'
import {
  FiBlockedState,
  FiGovernance,
  FiPartialWarning,
  FiSourceStatuses,
  FiValue,
} from './FinancialIntelligenceCommon'

const meta: FiResponseMeta = {
  contractVersion: 'fi.v1',
  asOf: '2026-09-30',
  generatedAt: '2026-09-30T12:00:00Z',
  traceId: 'trace-fi-test',
  requestId: 'trace-fi-test',
  sources: ['analytics-service'],
  calculationVersion: 'fi-composition-1.0.0',
  featureVersion: null,
  modelVersion: null,
  trainingDatasetVersion: null,
  deploymentMode: 'POC_SHADOW',
  mlGovernanceStatus: 'VERIFIED',
  sourceStatus: [
    {
      source: 'analytics-service',
      capability: 'booked-point-in-time-metrics',
      status: 'UNAVAILABLE',
      reason: 'DEPENDENCY_TIMEOUT',
    },
    {
      source: 'analytics-service',
      capability: 'cash-volatility',
      status: 'NOT_IMPLEMENTED',
      reason: 'No owner aggregate supports this calculation without raw data.',
    },
  ],
  partial: true,
  executionMode: 'DETERMINISTIC_RULES',
  mlMode: 'POC_SHADOW',
  rulesWeight: 1,
  mlWeight: 0,
  syntheticData: true,
  nonProduction: true,
  downstreamCallCount: 5,
  fanOutConcurrency: 5,
}

describe('Financial Intelligence — garde-fous de restitution', () => {
  it('affiche explicitement données synthétiques, non-production et ML sans influence', () => {
    render(<FiGovernance meta={meta} />)
    expect(screen.getByText(/SYNTHETIC DATA/)).toBeInTheDocument()
    expect(screen.getByText(/NON-PRODUCTION/)).toBeInTheDocument()
    expect(screen.getByText('DETERMINISTIC_RULES')).toBeInTheDocument()
    expect(screen.getByText('POC_SHADOW')).toBeInTheDocument()
    expect(screen.getByText('ML GOVERNANCE VERIFIED')).toBeInTheDocument()
    expect(screen.getByText('rulesWeight=1')).toBeInTheDocument()
    expect(screen.getByText('mlWeight=0')).toBeInTheDocument()
    expect(screen.getByText(/Aucune décision de crédit/)).toBeInTheDocument()
  })

  it('rend une indisponibilité comme réponse partielle sans inventer une valeur', () => {
    render(
      <>
        <FiPartialWarning meta={meta} />
        <FiSourceStatuses sources={meta.sourceStatus} />
        <span data-testid="missing-value"><FiValue value={null} currency="MAD" /></span>
      </>,
    )
    expect(screen.getByText(/Réponse partielle/)).toBeInTheDocument()
    expect(screen.getByText(/DEPENDENCY_TIMEOUT/)).toBeInTheDocument()
    expect(screen.getByTestId('missing-value')).toHaveTextContent('—')
  })

  it('n’atteste pas le mode ML lorsque sa métadonnée est indisponible', () => {
    render(
      <FiGovernance
        meta={{
          ...meta,
          mlGovernanceStatus: 'UNAVAILABLE',
          deploymentMode: null,
          mlMode: null,
          rulesWeight: null,
          mlWeight: null,
        }}
      />,
    )
    expect(screen.getByText('ML GOVERNANCE UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText('ML MODE NOT ATTESTED')).toBeInTheDocument()
    expect(screen.getByText('rulesWeight=NOT PROVIDED')).toBeInTheDocument()
    expect(screen.getByText('mlWeight=NOT PROVIDED')).toBeInTheDocument()
  })

  it('bloque visiblement une capacité non implémentée', () => {
    render(<FiBlockedState meta={meta} capabilities={['cash-volatility']} />)
    expect(screen.getByText('NOT IMPLEMENTED — BLOCKED')).toBeInTheDocument()
    expect(screen.getByText(/No owner aggregate supports this calculation/)).toBeInTheDocument()
  })
})
