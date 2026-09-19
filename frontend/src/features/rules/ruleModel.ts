import type { RuleConditionDefinition, RuleConditionGroup, RuleExpression, RuleLogic, RuleOperator, RuleUnit } from '../../api/types'

export const METRICS: Array<[string, string]> = [
  ['INFLOW_GROWTH', 'Encaissements'],
  ['SUPPLIER_PAYMENT_GROWTH', 'Paiements fournisseurs'],
  ['TRANSACTION_VOLUME_GROWTH', 'Volume transactions'],
  ['INTERNATIONAL_FLOW_GROWTH', 'Flux internationaux'],
  ['OUTFLOW_GROWTH', 'Décaissements'],
  ['BALANCE_SURPLUS', 'Excédent de trésorerie'],
  ['BALANCE_DECLINE', 'Baisse du solde'],
  ['CREDIT_UTILIZATION_INCREASE', 'Utilisation des lignes'],
  ['NO_RECENT_INVESTMENT_FINANCING', 'Aucun financement investissement récent'],
]

export const OPERATORS: Array<[RuleOperator, string]> = [
  ['INCREASE_BY', 'augmente de'],
  ['DECREASE_BY', 'diminue de'],
  ['GREATER_THAN', 'est supérieur à'],
  ['GREATER_THAN_OR_EQUAL', 'est supérieur ou égal à'],
  ['LESS_THAN', 'est inférieur à'],
  ['LESS_THAN_OR_EQUAL', 'est inférieur ou égal à'],
  ['EQUAL', 'est égal à'],
  ['NOT_EQUAL', 'est différent de'],
  ['BETWEEN', 'est entre'],
  ['IN', 'est dans'],
  ['NOT_IN', 'n’est pas dans'],
  ['PERSISTENT_FOR', 'est persistant pendant'],
]

export const UNITS: Array<[RuleUnit, string]> = [['PERCENT', '%'], ['MAD', 'MAD'], ['COUNT', 'opérations'], ['RATIO', 'ratio'], ['DAYS', 'jours'], ['BOOLEAN', 'oui/non']]
export const PERIODS: Array<[string, string]> = [['7D', '7 jours'], ['30D', '30 jours'], ['90D', '90 jours'], ['180D', '180 jours'], ['365D', '12 mois']]
export const LOGIC_LABELS: Record<RuleLogic, string> = { AND: 'ET', OR: 'OU', NOT: 'NON' }
export const OPPORTUNITY_TYPES: Array<[string, string]> = [['INVESTMENT_FINANCING', 'Financement d’investissement'], ['WORKING_CAPITAL', 'Financement BFR'], ['TRADE_FINANCE', 'Trade finance'], ['CASH_INVESTMENT', 'Placement de trésorerie'], ['FINANCIAL_STRESS_SIGNAL', 'Signal de tension financière']]
export const HORIZONS: Array<[string, string]> = [['0-1_MONTH', '0–1 mois'], ['0-3_MONTHS', '0–3 mois'], ['1-3_MONTHS', '1–3 mois'], ['3-6_MONTHS', '3–6 mois'], ['6-12_MONTHS', '6–12 mois']]
export const SECTORS = ['ALL', 'INDUSTRIE', 'IMPORT_EXPORT', 'DISTRIBUTION', 'SERVICES', 'BTP', 'AGRICULTURE', 'COMMERCE', 'TECHNOLOGIE']
export const REGIONS = ['ALL', 'CASABLANCA_SETTAT', 'RABAT_SALE_KENITRA', 'MARRAKECH_SAFI', 'FES_MEKNES', 'TANGER_TETOUAN_AL_HOCEIMA']
export const SEGMENTS = ['SME', 'MICRO_BUSINESS', 'MID_MARKET']
export const LIFECYCLE = ['DRAFT', 'VALIDATED', 'SIMULATED', 'SUBMITTED', 'APPROVED', 'PUBLISHED', 'ACTIVE'] as const
export const LIFECYCLE_LABELS: Record<string, string> = { DRAFT: 'Brouillon', VALIDATED: 'Validée', SIMULATED: 'Simulée', SUBMITTED: 'Soumise', APPROVED: 'Approuvée', PUBLISHED: 'Publiée', ACTIVE: 'Active', DISABLED: 'Désactivée', RETIRED: 'Retirée' }

export const metricLabel = (metric: string) => METRICS.find(([value]) => value === metric)?.[1] || metric
export const operatorLabel = (operator: string) => OPERATORS.find(([value]) => value === operator)?.[1] || operator.toLowerCase()
export const unitLabel = (unit: string) => UNITS.find(([value]) => value === unit)?.[1] || unit
export const periodLabel = (period: string) => PERIODS.find(([value]) => value === period)?.[1] || period

export const newCondition = (): RuleConditionDefinition => ({ id: crypto.randomUUID(), type: 'CONDITION', metric: 'INFLOW_GROWTH', operator: 'INCREASE_BY', value: 25, unit: 'PERCENT', period: '90D', weight: 20 })
export const newGroup = (): RuleConditionGroup => ({ id: crypto.randomUUID(), type: 'GROUP', logic: 'AND', conditions: [newCondition()] })
export const isGroup = (item: RuleExpression): item is RuleConditionGroup => item.type === 'GROUP' || 'conditions' in item

export const valueText = (value: RuleConditionDefinition['value']) => Array.isArray(value) ? value.join(', ') : String(value)

export function parseValue(text: string, operator: RuleOperator, unit: string): RuleConditionDefinition['value'] {
  if (unit === 'BOOLEAN') return text === 'true'
  if (operator === 'BETWEEN' || operator === 'IN' || operator === 'NOT_IN') {
    return text.split(',').map((part) => part.trim()).filter(Boolean).map((part) => (Number.isNaN(Number(part)) ? part : Number(part)))
  }
  return Number.isNaN(Number(text)) || text.trim() === '' ? text : Number(text)
}

/** Phrase lisible : « Encaissements augmente de 25 % sur 90 jours » */
export function conditionSentence(condition: RuleConditionDefinition) {
  const value = Array.isArray(condition.value) ? condition.value.join(' et ') : String(condition.value)
  const unit = condition.unit === 'BOOLEAN' ? '' : ` ${unitLabel(condition.unit)}`
  const sign = ['INCREASE_BY', 'DECREASE_BY'].includes(condition.operator) && condition.unit === 'PERCENT' ? '+' : ''
  return `${metricLabel(condition.metric)} ${operatorLabel(condition.operator)} ${sign}${value}${unit} sur ${periodLabel(condition.period)}`
}

export function countConditions(expressions: RuleExpression[]): number {
  return expressions.reduce((sum, item) => sum + (isGroup(item) ? countConditions(item.conditions) : 1), 0)
}
