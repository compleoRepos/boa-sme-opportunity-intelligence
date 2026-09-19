import { formatPercent, label } from '../../api/format'
import type { DashboardOpportunitySummary, Opportunity, PortfolioCustomerSummary } from '../../api/types'

/** Une raison moteur lisible : libellé métier, valeur observée, condition. */
export interface ParsedReason {
  raw: string
  key?: string
  label: string
  observed?: number
  operator?: string
  threshold?: number
  isBoolean?: boolean
  text: string
  delta?: string
}

const REASON_LABELS: Record<string, string> = {
  'inflow growth': 'Encaissements',
  'supplier payment growth': 'Paiements fournisseurs',
  'transaction volume growth': 'Volume transactions',
  'international flow growth': 'Flux internationaux',
  'international frequency growth': 'Fréquence internationale',
  'no recent investment financing': 'Aucun financement récent',
  'trade finance gap': 'Trade finance absent',
  'high average balance': 'Solde moyen élevé',
  'persistent cash surplus': 'Excédent persistant',
  'surplus confirmed in multiple periods': 'Excédent confirmé',
  'low credit utilization': 'Faible utilisation crédit',
  'inflow decline': 'Baisse des encaissements',
  'balance decline': 'Baisse du solde',
  'credit utilization increase': 'Hausse utilisation crédit',
  'cash surplus': 'Excédent de trésorerie',
}

const OPERATORS: Record<string, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤', eq: '=', ne: '≠' }

function humanLabel(text: string) {
  const normalized = text.trim().toLowerCase()
  if (REASON_LABELS[normalized]) return REASON_LABELS[normalized]
  const upper = text.trim().toUpperCase().replaceAll(' ', '_')
  const known = label(upper)
  return known === upper ? text.trim() : known
}

/** Parse « Inflow growth: observed=0.858, condition=gt 0.25 » ou un texte libre. */
export function parseReason(raw: string): ParsedReason {
  const match = /^(.*?):\s*observed=([^,]+),\s*condition=(\w+)\s+(.+)$/i.exec(raw)
  if (!match) return { raw, label: raw, text: raw }
  const name = match[1] ?? ''
  const observedText = match[2] ?? ''
  const operator = match[3] ?? ''
  const thresholdText = match[4] ?? ''
  const observed = Number(observedText)
  const threshold = Number(thresholdText)
  const isBoolean = observedText === 'True' || observedText === 'False' || thresholdText === 'True' || thresholdText === 'False'
  const labelText = humanLabel(name)
  if (isBoolean) {
    return { raw, label: labelText, isBoolean: true, text: labelText, operator, key: name }
  }
  const delta = Number.isFinite(observed) ? `${observed > 0 ? '+' : ''}${formatPercent(observed, 0)}` : undefined
  const condition = Number.isFinite(threshold) ? `${OPERATORS[operator] || operator} ${formatPercent(threshold, 0)}` : `${operator} ${thresholdText}`
  return { raw, key: name, label: labelText, observed, operator, threshold, delta, text: `${labelText} ${delta ?? ''} (seuil ${condition})` }
}

export function parseReasons(reasons?: string[]) {
  return (reasons || []).map(parseReason)
}

export function topSignals(reasons?: string[], limit = 3) {
  return parseReasons(reasons).filter((reason) => !reason.isBoolean && reason.delta).slice(0, limit)
}

export function primaryOpportunity(customer: PortfolioCustomerSummary): DashboardOpportunitySummary | undefined {
  return [...customer.openOpportunities].sort((a, b) => (b.priorityScore ?? b.confidence) - (a.priorityScore ?? a.confidence))[0]
}

export function productNames(opportunity?: { recommendedProducts?: Array<{ name: string }> } | Opportunity) {
  return opportunity?.recommendedProducts?.map((product) => product.name) ?? []
}
