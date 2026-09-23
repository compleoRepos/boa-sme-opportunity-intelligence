export type FiSourceAvailability = 'AVAILABLE' | 'EMPTY' | 'UNAVAILABLE' | 'NOT_IMPLEMENTED'

export interface FiSourceStatus {
  source: string
  capability: string
  status: FiSourceAvailability
  reason: string | null
}

export interface FiResponseMeta {
  contractVersion: string
  asOf: string
  generatedAt: string
  traceId: string
  requestId: string
  sources: string[]
  calculationVersion: string
  featureVersion: string | null
  modelVersion: string | null
  trainingDatasetVersion: string | null
  deploymentMode: 'POC_SHADOW' | null
  mlGovernanceStatus: 'VERIFIED' | 'UNAVAILABLE' | 'NOT_APPLICABLE'
  sourceStatus: FiSourceStatus[]
  partial: boolean
  executionMode: string
  mlMode: 'POC_SHADOW' | null
  rulesWeight: 1 | null
  mlWeight: 0 | null
  syntheticData: true
  nonProduction: true
  downstreamCallCount: number
  fanOutConcurrency: number
}

export interface FiEnvelope<T> {
  data: T
  meta: FiResponseMeta
}

export interface FiMetric {
  metric: string
  period: string
  value: number | null
  previousValue: number | null
  growthRate: number | null
  unit: string
  dataQuality: string | null
  dataCoverage: number | null
  sampleSize: number | null
}

export interface FiVisibility {
  level: 'HIGH' | 'PARTIAL' | 'LOW' | 'UNKNOWN'
  estimatedShare: number | null
  method: string
  categorizationCoverage: number | null
  fingerprintCount90d: number | null
  asOf: string | null
}

export interface FiSignal {
  signalRef: string
  type: string
  severity: string
  status: null
  stateAsOfStatus: 'NOT_IMPLEMENTED'
  value: number
  threshold: number
  asOf: string
  ruleVersion: string | null
  evidenceRefs: string[]
}

export interface FiOpportunity {
  opportunityId: string
  opportunityType: string
  status: null
  stateAsOfStatus: 'NOT_IMPLEMENTED'
  confidence: number
  priorityScore: number | null
  priorityLevel: string | null
  horizon: string | null
  asOf: string
  ruleVersion: string | null
  engineVersion: string | null
  scoringPolicyId: string | null
  scoringPolicyVersion: number | null
  fallbackMode: string | null
  evidenceRefs: string[]
}

export interface FiCashPosition {
  currency: string
  period: string
  averageBalance: number | null
  minimumBalance: number | null
  maximumBalance: number | null
  balanceTrend: number | null
  concentrationRatio: null
  volatility: null
}

export interface FiFlowSummary {
  currency: string
  period: string
  inflows: number | null
  outflows: number | null
  netFlow: number | null
  inflowTrend: number | null
  outflowTrend: number | null
  netFlowRatio: number | null
  transactionCount: number | null
  activityTrend: number | null
  concentrationRatio: null
  volatility: null
}

export interface FiCompanySummary {
  companyId: string
  legalName: string | null
  sector: string | null
  segment: string | null
  status: string | null
  portfolioId: string
  fundId: string
  visibility: FiVisibility
  cashPosition: FiCashPosition
  flowSummary: FiFlowSummary
  signals: FiSignal[]
  opportunities: FiOpportunity[]
  metrics: FiMetric[]
  disclaimer: 'NO_CREDIT_DECISION'
}

export interface FiPortfolioSummary {
  portfolioId: string
  fundId: string
  companyCount: number
  companies: FiCompanySummary[]
  totalInflows: number | null
  totalOutflows: number | null
  totalNetFlow: number | null
  signalCount: number
  companiesWithSignals: number
  opportunityCount: number
  opportunityDistribution: Record<string, number>
  disclaimer: 'NO_CREDIT_DECISION'
}

export interface FiPortfolioCatalogItem {
  portfolioId: string
  fundId: string
  name: string
  companyCount: number
}

export interface FiPortfolioCatalog {
  portfolios: FiPortfolioCatalogItem[]
  totalCount: number
  pageSize: number
  nextOffset: number | null
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function parseFiEnvelope<T>(payload: unknown): FiEnvelope<T> {
  if (!isObject(payload) || !('data' in payload) || !isObject(payload.meta)) {
    throw new Error('Réponse Financial Intelligence invalide : enveloppe {data, meta} absente.')
  }
  const meta = payload.meta
  const requiredMeta = [
    'contractVersion', 'asOf', 'generatedAt', 'traceId', 'requestId', 'sources', 'sourceStatus',
    'executionMode', 'mlGovernanceStatus', 'mlMode', 'rulesWeight', 'mlWeight',
    'syntheticData', 'nonProduction',
  ]
  if (requiredMeta.some((key) => !(key in meta))) {
    throw new Error('Réponse Financial Intelligence invalide : métadonnées de gouvernance incomplètes.')
  }
  if (
    meta.contractVersion !== 'fi.v1'
    || meta.executionMode !== 'DETERMINISTIC_RULES'
    || meta.syntheticData !== true
    || meta.nonProduction !== true
    || !Array.isArray(meta.sources)
    || !Array.isArray(meta.sourceStatus)
  ) {
    throw new Error('Réponse Financial Intelligence invalide : invariants de gouvernance non respectés.')
  }
  const mlVerified = meta.mlGovernanceStatus === 'VERIFIED'
  const mlNotAttested = ['UNAVAILABLE', 'NOT_APPLICABLE'].includes(String(meta.mlGovernanceStatus))
  if (
    (mlVerified && (
      meta.mlMode !== 'POC_SHADOW'
      || meta.deploymentMode !== 'POC_SHADOW'
      || meta.rulesWeight !== 1
      || meta.mlWeight !== 0
    ))
    || (mlNotAttested && (
      meta.mlMode !== null
      || meta.deploymentMode !== null
      || meta.rulesWeight !== null
      || meta.mlWeight !== null
    ))
    || (!mlVerified && !mlNotAttested)
  ) {
    throw new Error('Réponse Financial Intelligence invalide : attestation ML incohérente.')
  }
  return payload as unknown as FiEnvelope<T>
}

export function sourceStatusFor(meta: FiResponseMeta | undefined, capability: string) {
  return meta?.sourceStatus.filter((source) => source.capability === capability) ?? []
}

export const FI_API_ROOT = '/api/v1/financial-intelligence'

function withAsOf(path: string, asOf: string) {
  return `${path}?asOf=${encodeURIComponent(asOf)}`
}

export function fiPortfolioCatalogPath(asOf: string) {
  return withAsOf(`${FI_API_ROOT}/portfolios`, asOf)
}

export function fiPortfolioSummaryPath(portfolioId: string, asOf: string) {
  return withAsOf(`${FI_API_ROOT}/portfolios/${encodeURIComponent(portfolioId)}/summary`, asOf)
}

export function fiCompanyPath(companyId: string, resource: 'summary' | 'signals' | 'opportunities' | 'cash-position' | 'flow-summary', asOf: string) {
  return withAsOf(`${FI_API_ROOT}/companies/${encodeURIComponent(companyId)}/${resource}`, asOf)
}
