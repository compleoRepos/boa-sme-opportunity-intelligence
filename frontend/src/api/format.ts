const labels: Record<string, string> = {
  INVESTMENT_FINANCING: "Financement d’investissement",
  TRADE_FINANCE: 'Trade finance',
  CASH_INVESTMENT: 'Placement de trésorerie',
  FINANCIAL_STRESS_SIGNAL: 'Signal de tension financière',
  INFLOW_GROWTH: 'Croissance des encaissements',
  OUTFLOW_GROWTH: 'Croissance des décaissements',
  SUPPLIER_PAYMENT_GROWTH: 'Croissance des paiements fournisseurs',
  INTERNATIONAL_FLOW_GROWTH: 'Croissance des flux internationaux',
  BALANCE_SURPLUS: 'Excédent de trésorerie',
  BALANCE_DECLINE: 'Baisse du solde',
  CREDIT_UTILIZATION_INCREASE: 'Hausse de l’utilisation des lignes',
  TRANSACTION_VOLUME_GROWTH: 'Croissance du volume de transactions',
  ACCEPT_OPPORTUNITY: 'Opportunité acceptée',
  DISMISS_OPPORTUNITY: 'Opportunité écartée',
  CONTACT_CUSTOMER: 'Contact client',
  CREATE_FOLLOW_UP: 'Suivi créé',
  SCHEDULE_MEETING: 'Rendez-vous planifié',
  MARK_CONVERTED: 'Conversion enregistrée',
  CONTACTED: 'Contacté',
  MEETING_SCHEDULED: 'Rendez-vous planifié',
  OFFER_CREATED: 'Offre créée',
  CONVERTED: 'Converti',
  REJECTED: 'Refusé',
  NOT_RELEVANT: 'Non pertinent',
  OPEN: 'Ouvert',
  ACCEPTED: 'Acceptée',
  DISMISSED: 'Écartée',
  HIGH: 'Élevée',
  MEDIUM: 'Moyenne',
  LOW: 'Faible',
  ACTIVE: 'Actif',
  DRAFT: 'Brouillon',
  VALIDATED: 'Validée',
  SIMULATED: 'Simulée',
  SUBMITTED: 'Soumise',
  APPROVED: 'Approuvée',
  PUBLISHED: 'Publiée',
  DISABLED: 'Désactivée',
  RETIRED: 'Retirée',
  MATCH: 'Correspondance',
  NO_MATCH: 'Aucune correspondance',
  GREATER_THAN: 'Supérieur à',
  GREATER_THAN_OR_EQUAL: 'Supérieur ou égal à',
  LESS_THAN: 'Inférieur à',
  LESS_THAN_OR_EQUAL: 'Inférieur ou égal à',
  EQUAL: 'Égal à',
  NOT_EQUAL: 'Différent de',
  BETWEEN: 'Entre',
  IN: 'Dans la liste',
  NOT_IN: 'Hors de la liste',
  INCREASE_BY: 'Augmente de',
  DECREASE_BY: 'Diminue de',
  PERSISTENT_FOR: 'Persistant pendant',
  PERCENT: '%',
  MAD: 'MAD',
  COUNT: 'éléments',
  RATIO: 'ratio',
  DAYS: 'jours',
  BOOLEAN: '',
  '7D': '7 jours',
  '30D': '30 jours',
  '90D': '90 jours',
  '180D': '180 jours',
  '365D': '12 mois',
  WORKING_CAPITAL: 'Financement BFR',
  INACTIVE: 'Inactif',
  CURRENT_ACCOUNT: 'Compte courant',
  SAVINGS: 'Épargne',
  CREDIT_LINE: 'Ligne de crédit',
  MONTHLY_INFLOW: 'Encaissements',
  monthly_inflow: 'Encaissements',
  MONTHLY_OUTFLOW: 'Décaissements',
  monthly_outflow: 'Décaissements',
  AVERAGE_BALANCE: 'Solde moyen',
  average_balance: 'Solde moyen',
  INTERNATIONAL_FLOW_AMOUNT: 'Flux internationaux',
  international_flow_amount: 'Flux internationaux',
  international_flow_growth: 'Flux internationaux',
  CREDIT_LINE_UTILIZATION: 'Utilisation des lignes',
  credit_line_utilization: 'Utilisation des lignes',
  '0-1_MONTH': '0–1 mois',
  '0-3_MONTHS': '0–3 mois',
  '1-3_MONTHS': '1–3 mois',
}

export const label = (value?: string | null) => {
  if (!value) return '—'
  return labels[value] ?? value.replaceAll('_', ' ').toLocaleLowerCase('fr-FR').replace(/^./, (char) => char.toUpperCase())
}

export const formatPercent = (value?: number | null, digits = 0) =>
  value == null || Number.isNaN(value) ? '—' : new Intl.NumberFormat('fr-FR', { style: 'percent', maximumFractionDigits: digits }).format(value)

export const formatNumber = (value?: number | null, digits = 0) =>
  value == null || Number.isNaN(value) ? '—' : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value)

export const formatMoney = (value?: number | null, currency = 'MAD') =>
  value == null || Number.isNaN(value)
    ? '—'
    : new Intl.NumberFormat('fr-FR', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)

export const formatDate = (value?: string | null, includeTime = false) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('fr-FR', includeTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(date)
}

export const getCustomerName = (value?: { customerName?: string; legalName?: string; tradeName?: string; customerId?: string }) =>
  value?.customerName || value?.tradeName || value?.legalName || value?.customerId || 'Client non renseigné'

export const metricUnit = (metric: string) => {
  const normalized = metric.toUpperCase()
  if (normalized.includes('UTILIZATION') || normalized.includes('GROWTH') || normalized.includes('RATIO')) return 'percent'
  if (normalized.includes('COUNT') || normalized.includes('VOLUME')) return 'number'
  return 'money'
}

export const safeJson = (value: unknown) => {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}
