/** Palette catégorielle validée (script dataviz, mode clair) : ordre fixe, jamais cyclé. */
export const CHART = {
  blue: '#1f5fd0',
  amber: '#c97a0c',
  green: '#0e8a5f',
  violet: '#8b5cf6',
  red: '#c0392b',
  teal: '#0e9bb0',
  grid: '#e6ebf2',
  axis: '#94a3b8',
  text: '#64748b',
} as const

/** Couleur par entité (jamais par rang) */
export const SERIES = {
  inflow: CHART.green,
  outflow: CHART.amber,
  net: CHART.blue,
  transactionCount: CHART.blue,
  supplierPayments: CHART.violet,
  internationalAmount: CHART.teal,
  opportunities: CHART.blue,
  actions: CHART.violet,
  ml: CHART.violet,
  rules: CHART.blue,
} as const

export const OPPORTUNITY_COLORS: Record<string, string> = {
  INVESTMENT_FINANCING: CHART.blue,
  TRADE_FINANCE: CHART.teal,
  CASH_INVESTMENT: CHART.violet,
  FINANCIAL_STRESS_SIGNAL: CHART.amber,
  WORKING_CAPITAL: CHART.green,
}

export const PRIORITY_COLORS: Record<string, string> = { P1: CHART.red, P2: CHART.amber, P3: CHART.blue, P4: '#94a3b8' }

export const OUTCOME_COLORS: Record<string, string> = {
  CONTACTED: CHART.blue,
  MEETING_SCHEDULED: CHART.teal,
  OFFER_CREATED: CHART.violet,
  CONVERTED: CHART.green,
  REJECTED: CHART.red,
  NOT_RELEVANT: '#94a3b8',
}

export const axisProps = { tick: { fontSize: 11, fill: CHART.text }, axisLine: false as const, tickLine: false as const }
