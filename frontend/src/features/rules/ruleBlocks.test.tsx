import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { RuleConditionGroup } from '../../api/types'
import { ReadableRule, RuleBuilder } from './RuleBlocks'
import { conditionSentence, newGroup } from './ruleModel'

const conditions = [
  { id: 'c1', type: 'CONDITION' as const, metric: 'INFLOW_GROWTH', operator: 'INCREASE_BY' as const, value: 25, unit: 'PERCENT', period: '90D' },
  { id: 'c2', type: 'CONDITION' as const, metric: 'SUPPLIER_PAYMENT_GROWTH', operator: 'INCREASE_BY' as const, value: 20, unit: 'PERCENT', period: '90D' },
]

describe('Rule Studio — lecture et édition', () => {
  it('affiche la règle en SI / ET / ALORS lisible par le métier', () => {
    render(<ReadableRule conditions={conditions} logic="AND" recommendation={{ opportunityType: 'INVESTMENT_FINANCING', products: ['INVESTMENT_FINANCING'], horizon: '1-3_MONTHS' }} products={{ INVESTMENT_FINANCING: 'Investment Financing' }} />)
    expect(screen.getByText('SI')).toBeInTheDocument()
    expect(screen.getByText('ET')).toBeInTheDocument()
    expect(screen.getByText('ALORS')).toBeInTheDocument()
    expect(screen.getByText('Paiements fournisseurs')).toBeInTheDocument()
    expect(screen.getByText((_, node) => Boolean(node?.classList.contains('value') && node.textContent?.replace(/\s/g, '') === '+25%'))).toBeInTheDocument()
    expect(screen.getByText('Investment Financing')).toBeInTheDocument()
    expect(conditionSentence(conditions[0]!)).toBe('Encaissements augmente de +25 % sur 90 jours')
  })

  it('permet d’ajouter une condition et un groupe imbriqué sans code', () => {
    function Harness() { const [group, setGroup] = useState<RuleConditionGroup>(() => newGroup()); return <RuleBuilder group={group} onChange={setGroup} /> }
    render(<Harness />)
    expect(screen.getAllByTestId('rule-condition')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /^Condition$/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Groupe$/ }))
    expect(screen.getAllByTestId('rule-condition')).toHaveLength(3)
    expect(screen.getAllByTestId('rule-group')).toHaveLength(1)
    fireEvent.click(screen.getAllByRole('button', { name: 'OU' })[0]!)
    expect(screen.getAllByRole('button', { name: 'OU' })[0]).toHaveAttribute('aria-pressed', 'true')
    fireEvent.change(screen.getAllByLabelText(/Valeur condition/)[0]!, { target: { value: '30' } })
    expect(screen.getAllByLabelText(/Valeur condition/)[0]).toHaveValue(30)
  })
})

describe('groupByFamily', () => {
  it('regroupe les produits BOA par famille dans l’ordre du catalogue', async () => {
    const { groupByFamily } = await import('./RuleBlocks')
    const groups = groupByFamily([
      { productId: 'BOA_OPCVM', name: 'OPCVM', family: 'LIQUIDITY_INVESTMENT' },
      { productId: 'BOA_BAIL_ENTREPRISE', name: 'Bail Entreprise', family: 'INVESTMENT_FINANCING' },
      { productId: 'BOA_CREDIT_MLTD_DIRECT', name: 'Crédit MLTD Direct', family: 'INVESTMENT_FINANCING' },
      { productId: 'LEGACY', name: 'Ancien produit' },
    ])
    expect(groups.map(([family]) => family)).toEqual(['INVESTMENT_FINANCING', 'LIQUIDITY_INVESTMENT', 'LEGACY'])
    expect(groups[0]?.[1].map((item) => item.name)).toEqual(['Bail Entreprise', 'Crédit MLTD Direct'])
  })
})
