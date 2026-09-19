export const PRODUCT_FAMILIES: Array<[string, string]> = [
  ['INVESTMENT_FINANCING', 'Financement de l’investissement'],
  ['WORKING_CAPITAL_FACILITY', 'Financement du cycle d’exploitation'],
  ['OVERDRAFT', 'Avances et découverts'],
  ['TRADE_FINANCE', 'Opérations à l’international'],
  ['CASH_MANAGEMENT', 'Gestion des flux et de la trésorerie'],
  ['TERM_DEPOSIT', 'Placements à taux garanti'],
  ['LIQUIDITY_INVESTMENT', 'Placements en OPCVM'],
]
export const familyLabel = (family?: string | null) => PRODUCT_FAMILIES.find(([code]) => code === family)?.[1] ?? label(family)
export const familyRank = (family?: string | null) => { const index = PRODUCT_FAMILIES.findIndex(([code]) => code === family); return index === -1 ? PRODUCT_FAMILIES.length : index }

const labels: Record<string, string> = {
  INVESTMENT_FINANCING: "Financement d’investissement",
  LEASING: 'Crédit-bail',
  GUARANTEE: 'Garantie',
  ACCOUNT: 'Compte',
  PACKAGE: 'Forfait',
  DIGITAL: 'Banque à distance',
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
  '3-6_MONTHS': '3–6 mois',
  '6-12_MONTHS': '6–12 mois',
  INDUSTRIE: 'Industrie',
  IMPORT_EXPORT: 'Import / Export',
  DISTRIBUTION: 'Distribution',
  SERVICES: 'Services',
  BTP: 'BTP',
  AGRICULTURE: 'Agriculture',
  COMMERCE: 'Commerce',
  TECHNOLOGIE: 'Technologie',
  SMALL: 'Petite entreprise',
  SME: 'PME',
  MICRO_BUSINESS: 'TPE',
  MID_MARKET: 'ETI',
  P1: 'Priorité P1',
  P2: 'Priorité P2',
  P3: 'Priorité P3',
  P4: 'Priorité P4',
  COMPLETED: 'Terminée',
  CANDIDATE: 'Candidat',
  ALL: 'Tous',
  datasetKind: 'Type de dataset',
  evaluationMode: 'Mode d’évaluation',
  validationStatus: 'Statut de validation',
  productionPerformanceClaim: 'Performance de production revendiquée',
  confirmed_signal_ratio: 'Part de signaux confirmés',
  published_rule_match_strength: 'Force de correspondance aux règles publiées',
  CUSTOMER_RECEIPT: 'Encaissement client',
  SUPPLIER_PAYMENT: 'Paiement fournisseur',
  OPERATING_EXPENSE: 'Charge d’exploitation',
  TRANSFER: 'Virement',
  PAYMENT: 'Paiement',
  FINANCING: 'Financement',
  TRADE: 'Trade finance',
  CASH: 'Cash management',
  INVESTMENT: 'Placement',
  cash_inflow_growth_90d: 'Croissance des encaissements (90 j)',
  supplier_payment_growth_90d: 'Dynamique des paiements fournisseurs (90 j)',
  international_activity_ratio_90d: 'Part de l’activité internationale (90 j)',
  balance_strength_90d: 'Solidité de la trésorerie (90 j)',
  activity_density_90d: 'Densité d’activité transactionnelle (90 j)',
  analytics_coverage_90d: 'Couverture des données analytiques',
  customer_tenure_ratio: 'Ancienneté de la relation',
  segment_medium: 'Segment PME intermédiaire',
  inflow_amount: 'Encaissements',
  outflow_amount: 'Décaissements',
  supplier_payment_amount: 'Paiements fournisseurs',
  transaction_count: 'Volume de transactions',
  HISTORICAL_CONSISTENCY: 'Cohérence historique',
  PRODUCT_GAP: 'Écart d’équipement',
  RECENCY: 'Récence',
  NO_RECENT_INVESTMENT_FINANCING: 'Aucun financement investissement récent',
  ROLLED_BACK: 'Restaurée',
  CREATED: 'Créée',
  UPDATED: 'Modifiée',
  'CASH_INVESTMENT_RULE': 'Placement de trésorerie',
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

export const formatCompact = (value?: number | null, currency = 'MAD') => {
  if (value == null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(value / 1_000_000)} M${currency}`
  if (abs >= 10_000) return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value / 1_000)} k${currency}`
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value)} ${currency}`
}

export const formatRelative = (value?: string | null, now = new Date()) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const days = Math.round((now.getTime() - date.getTime()) / 86_400_000)
  if (days < 0) return `le ${formatShortDate(value)}`
  if (days === 0) return 'aujourd’hui'
  if (days === 1) return 'il y a 1 jour'
  if (days < 30) return `il y a ${days} jours`
  const months = Math.round(days / 30)
  return months <= 1 ? 'il y a 1 mois' : `il y a ${months} mois`
}

export const formatMonth = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('fr-FR', { month: 'short', year: '2-digit' }).format(date)
}

export const formatShortDate = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short' }).format(date)
}

export const initials = (name?: string) => (name || '?').split(/\s+/).map((part) => part[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()

export const opportunityTone = (type?: string) => type === 'FINANCIAL_STRESS_SIGNAL' ? 'warning' : type === 'TRADE_FINANCE' ? 'teal' : type === 'CASH_INVESTMENT' ? 'violet' : 'info'

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
