import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import type { RuleConditionGroup, RuleSimulationResult, RuleTestResult } from '../../api/types'
import { ConditionBuilder, newGroup } from './ConditionBuilder'
import { RuleTestProof, SimulationPreview } from './RuleInsights'

function BuilderHarness() {
  const [group, setGroup] = useState<RuleConditionGroup>(() => newGroup())
  return <ConditionBuilder group={group} onChange={setGroup} />
}

describe('ConditionBuilder', () => {
  it('construit sans code un groupe imbriqué et permet AND, OR et NOT', () => {
    render(<BuilderHarness />)
    expect(screen.getAllByTestId('rule-condition')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /Groupe imbriqué/i }))
    expect(screen.getAllByText(/Groupe [12]/)).toHaveLength(2)
    const non = screen.getAllByRole('button', { name: 'NON' })[1]!
    fireEvent.click(non)
    expect(non).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getAllByRole('button', { name: /^Condition$/ })[0]!)
    expect(screen.getAllByTestId('rule-condition')).toHaveLength(3)
    fireEvent.change(screen.getAllByLabelText(/Opérateur condition/)[0]!, { target: { value: 'BETWEEN' } })
    expect(screen.getAllByLabelText(/Opérateur condition/)[0]).toHaveValue('BETWEEN')
  })
})

const simulation: RuleSimulationResult = {
  populationAnalyzed: 12438,
  matchedCustomers: 1284,
  highConfidence: 421,
  conversionRate: 'NOT_AVAILABLE',
  averageOpportunitiesPerRm: 17.2,
  topCustomers: [{ customerId: 'SME-00125', legalName: 'Atlas Industrie', signals: ['INFLOW_GROWTH'], values: { INFLOW_GROWTH: 36 }, confidence: .86, opportunityType: 'INVESTMENT_FINANCING' }],
  impact: { bySector: [{ sector: 'INDUSTRY', count: 621, rate: .48 }], byRegion: [{ region: 'CASABLANCA_SETTAT', count: 510, rate: .4 }], bySegment: [{ segment: 'SME', count: 1284, rate: 1 }] },
  warnings: [{ message: 'Cette règle toucherait 68% de la population PME.', affectedRate: .68 }],
}

const testResult: RuleTestResult = {
  matched: true,
  ruleId: 'INV_FIN_001',
  ruleVersion: 3,
  engineVersion: 'engine-2.4',
  customerId: 'SME-00125',
  customerName: 'Atlas Industrie',
  opportunityType: 'INVESTMENT_FINANCING',
  confidence: .86,
  evidence: [{ metric: 'INFLOW_GROWTH', actual: 36, threshold: 25, operator: 'GREATER_THAN', unit: 'PERCENT', period: '90D', result: true }],
}

describe('Résultats Rule Studio', () => {
  it('rend la preview, le warning de règle large et les impacts exclusivement depuis la réponse API', () => {
    render(<SimulationPreview result={simulation} />)
    expect(screen.getByText('Population analysée').nextElementSibling).toHaveTextContent('12')
    expect(screen.getByText('Atlas Industrie')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('68%')
    expect(screen.getByText('Par secteur')).toBeInTheDocument()
    expect(screen.getByText(/aucune donnée commerciale inventée/i)).toBeInTheDocument()
  })

  it('rend une preuve explicable condition par condition pour la PME testée', () => {
    render(<RuleTestProof result={testResult} />)
    expect(screen.getByText('Atlas Industrie')).toBeInTheDocument()
    expect(screen.getByText('Condition 1')).toBeInTheDocument()
    expect(screen.getByText(/Valeur observée/)).toHaveTextContent('36')
    expect(screen.getByText('CORRESPONDANCE')).toBeInTheDocument()
    expect(screen.getByText('Confiance').nextElementSibling).toHaveTextContent('86')
  })
})
