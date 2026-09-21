export type Role = 'RELATIONSHIP_MANAGER' | 'BRANCH_MANAGER' | 'ADMIN' | 'DATA_ANALYST' | 'BUSINESS_ANALYST' | 'RULE_APPROVER'

export interface PageMeta {
  pageSize: number
  nextCursor?: string | null
  hasMore: boolean
  totalCount?: number | null
}

export interface ApiPage<T> {
  data: T[]
  meta: PageMeta
  links?: { self?: string; next?: string | null }
  correlationId?: string
}

export interface ApiProblem {
  code?: string
  message?: string
  title?: string
  status?: number
  correlationId?: string
  timestamp?: string
  details?: Array<{ field?: string; code?: string; message?: string }>
}

export interface Customer {
  customerId: string
  legalName: string
  tradeName?: string
  industry?: string
  sector?: string
  segment?: string
  country?: string
  branchId?: string
  branchName?: string
  relationshipManagerId?: string
  relationshipManagerName?: string
  status?: string
  incorporatedOn?: string
  createdAt?: string
  updatedAt?: string
}

export interface AccountBalance {
  asOf: string
  available?: number
  ledger?: number
  currency: string
}

export interface Account {
  accountId: string
  customerId: string
  accountType: string
  currency: string
  status: string
  openedAt?: string
  creditLimit?: number
  balance?: AccountBalance
}

export interface Transaction {
  transactionId: string
  customerId: string
  accountId: string
  bookingDate: string
  valueDate?: string
  type: string
  direction: 'CREDIT' | 'DEBIT' | string
  amount: number
  currency: string
  category?: string
  counterpartyName?: string
  international?: boolean
  countryCode?: string
  description?: string
}

export interface FinancialMetric {
  customerId: string
  metric: string
  currentValue: number
  previousPeriodValue?: number | null
  historicalBaselineValue?: number | null
  growthRate?: number | null
  deviationFromBaseline?: number | null
  period: string
  asOf: string
  currency?: string
  calculationVersion?: string
  dataQuality?: string
}

export interface Signal {
  signalId: string
  customerId: string
  customerName?: string
  type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | string
  value: number
  threshold?: number
  period?: string
  detectedAt: string
  status?: string
  evidence?: string[]
  metricReferences?: string[]
  engineVersion?: string
  ruleVersion?: string
}

export interface ProductReference {
  productId: string
  name: string
}

export interface Product {
  productId: string
  name: string
  description?: string | null
  category: string
  family?: string
  sourceUrl?: string | null
  eligibilityRules?: string[] | Record<string, unknown>
  targetSegment?: string | string[]
  currency?: string | string[]
  active: boolean
}

export interface Opportunity {
  opportunityId: string
  customerId: string
  customerName?: string
  legalName?: string
  opportunityType: string
  status: string
  confidence: number
  confidenceLevel: 'LOW' | 'MEDIUM' | 'HIGH' | string
  priorityScore: number
  priorityLevel: string
  horizon: string
  why: string[]
  what: string
  when: string
  recommendedProducts?: ProductReference[]
  evidenceCount?: number
  generatedAt: string
  engineVersion?: string
  ruleVersion?: string
  statusUpdatedAt?: string
  statusReason?: string | null
  expiresAt?: string | null
  cooldownUntil?: string | null
  lastActionAt?: string | null
}

export interface ConfidenceComponent {
  name: string
  points: number
  maxPoints: number
  satisfied: boolean
  value?: number | string
}

export interface Explanation {
  opportunityId: string
  signals: Array<Pick<Signal, 'signalId' | 'type' | 'value' | 'threshold'> & Partial<Signal>>
  metrics: FinancialMetric[]
  thresholds: Record<string, number | string | boolean>
  historicalComparison?: Record<string, unknown> | string
  confidenceComponents: ConfidenceComponent[]
  recommendedProducts: ProductReference[]
  horizon: string
  engineVersion?: string
  ruleVersion?: string
  evidence?: Array<string | Record<string, unknown>>
}

export type ActionType =
  | 'ACCEPT_OPPORTUNITY'
  | 'DISMISS_OPPORTUNITY'
  | 'CONTACT_CUSTOMER'
  | 'CREATE_FOLLOW_UP'
  | 'DEFER_OPPORTUNITY'
  | 'SCHEDULE_MEETING'
  | 'MARK_CONVERTED'

export type Outcome = 'CONTACTED' | 'MEETING_SCHEDULED' | 'OFFER_CREATED' | 'CONVERTED' | 'REJECTED' | 'NOT_RELEVANT' | 'REVIEW_LATER'

export interface OpportunityAction {
  actionId: string
  opportunityId: string
  customerId: string
  actionType: ActionType | string
  status: string
  assignedTo?: string
  dueAt?: string | null
  note?: string | null
  outcome?: Outcome | null
  transitionStatus?: 'NOT_REQUIRED' | 'PENDING' | 'APPLIED' | 'FAILED'
  transitionError?: string | null
  createdAt: string
  createdBy?: string
  updatedAt?: string
}

export interface DashboardKpis {
  totalOpportunities?: number
  todaysOpportunities?: number
  highConfidenceOpportunities?: number
  contactedOpportunities?: number
  contactRate?: number
  meetingRate?: number
  offerRate?: number
  conversionRate?: number
  dismissalRate?: number
  falsePositiveRate?: number
  opportunitiesByType?: Array<{ type?: string; opportunityType?: string; count: number }>
  opportunitiesByPriority?: Array<{ priority?: string; priorityLevel?: string; count: number }>
  opportunityTrend?: Array<{ date?: string; period?: string; count: number }>
  generatedAt?: string
  asOf?: string
  [key: string]: unknown
}

export type CustomerPriority = 'P1' | 'P2' | 'P3' | string

export interface DashboardScope {
  type: 'RELATIONSHIP_MANAGER' | 'BRANCH'
  relationshipManagerId?: string
  relationshipManagerName?: string
  branchId?: string
  branchName?: string
  asOf?: string
}

export interface CommercialDashboardKpis {
  portfolioCustomers: number
  highPriorityCustomers: number
  openOpportunities: number
  actionsDue: number
  contactedCustomers?: number
  convertedOpportunities?: number
  conversionRate?: number
}

export interface DashboardOpportunitySummary {
  opportunityId: string
  opportunityType: string
  confidence: number
  confidenceLevel?: string
  priorityScore?: number
  priorityLevel?: string
  horizon?: string
  status?: string
  why?: string[]
  recommendedProducts?: ProductReference[]
  generatedAt?: string
}

export interface DashboardNextAction {
  actionId?: string
  opportunityId?: string
  actionType: string
  dueAt?: string | null
  status?: string
  note?: string | null
}

export interface PortfolioCustomerSummary {
  customerId: string
  customerName: string
  industry?: string
  segment?: string
  relationshipManagerId?: string
  relationshipManagerName?: string
  branchId?: string
  branchName?: string
  combinedPriorityScore?: number
  propensityScore: number
  priorityLevel: CustomerPriority
  priorityReason?: string
  openOpportunities: DashboardOpportunitySummary[]
  nextActions: DashboardNextAction[]
}

export interface PriorityDistributionItem {
  priorityLevel: CustomerPriority
  count: number
  share?: number
}

export interface RelationshipManagerDashboard {
  scope: DashboardScope
  kpis: CommercialDashboardKpis
  priorityDistribution: PriorityDistributionItem[]
  portfolio: PortfolioCustomerSummary[]
  generatedAt?: string
}

export interface ConversionFunnelItem {
  stage: string
  count: number
  rate?: number
}

export interface RelationshipManagerPerformance {
  relationshipManagerId: string
  relationshipManagerName: string
  portfolioCustomers: number
  highPriorityCustomers: number
  openOpportunities: number
  actionsDue: number
  convertedOpportunities: number
  conversionRate: number
  averagePropensity?: number
}

export interface BreakdownItem {
  count: number
  share?: number
  opportunityType?: string
  sector?: string
  product?: string
  priorityLevel?: string
  relationshipManagerId?: string
  relationshipManagerName?: string
  actionType?: string
  outcome?: string
}

export interface TimelinePoint {
  date: string
  count: number
}

export interface BranchDashboard {
  scope: DashboardScope
  kpis: CommercialDashboardKpis
  priorityDistribution: PriorityDistributionItem[]
  conversionFunnel: ConversionFunnelItem[]
  relationshipManagers: RelationshipManagerPerformance[]
  opportunitiesByType?: BreakdownItem[]
  opportunitiesBySector?: BreakdownItem[]
  opportunitiesByProduct?: BreakdownItem[]
  opportunitiesByPriority?: BreakdownItem[]
  opportunitiesByRelationshipManager?: BreakdownItem[]
  opportunityTimeline?: TimelinePoint[]
  actionsByType?: BreakdownItem[]
  outcomes?: BreakdownItem[]
  actionTimeline?: TimelinePoint[]
  generatedAt?: string
}

export interface ActivityPoint {
  period: string
  inflow: number
  outflow: number
  net: number
  transactionCount: number
  supplierPayments: number
  internationalAmount: number
  internationalCount: number
}

export interface ActivitySeries {
  customerId: string
  granularity: 'DAY' | 'WEEK' | 'MONTH' | string
  currency: string
  fromDate?: string | null
  toDate?: string | null
  points: ActivityPoint[]
  source?: string
}

export interface MlModel {
  modelVersion: string
  scoreType: string
  algorithm: string
  status: 'ACTIVE' | 'CANDIDATE' | 'RETIRED' | string
  featureSetVersion: string
  featureOrder: string[]
  coefficients: Record<string, number>
  intercept: number
  threshold: number
  validationMetrics: Record<string, number | string | Record<string, unknown>>
  trainingDatasetVersion: string
  trainingCodeVersion: string
  deploymentMode: string
  productionPerformanceClaim?: boolean
  automaticTraining?: boolean
  createdAt?: string
  updatedAt?: string
}

export interface RuleSimulationHistoryEntry extends RuleSimulationResult {
  ruleVersion?: number | string
  population?: Record<string, unknown>
  createdBy?: string
}

export interface DevPersona {
  id: string
  label: string
  description: string
  subject: string
  username: string
  displayName: string
  roles: Role[]
  branchIds?: string[]
  relationshipManagerIds?: string[]
}

export type PropensityFactorDirection = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | string

export interface PropensityFactor {
  feature: string
  label: string
  value?: number | string | boolean | null
  direction: PropensityFactorDirection
  contribution?: number
  explanation: string
  source?: string
}

export interface PropensityModelMetadata {
  modelId?: string
  modelVersion: string
  featureSetVersion: string
  scoredAt?: string
  trainingCutoff?: string
}

export interface PropensityCombination {
  method: 'RULES_ONLY' | string
  mlObservationMode?: 'POC_SHADOW' | string
  mlScore: number
  rulesScore: number
  mlWeight: number
  rulesWeight: number
  combinedPriorityScore?: number
  shadowReadOnly?: boolean
  summary?: string
}

export interface CustomerPropensity {
  customerId: string
  score: number
  scoreMeaning?: string
  priorityLevel?: CustomerPriority
  model: PropensityModelMetadata
  combination: PropensityCombination
  factors: PropensityFactor[]
  warnings?: string[]
}

export interface RuleParameter {
  key: string
  value: string | number | boolean
  unit?: string
  label?: string
}

export interface RuleConfig {
  ruleId: string
  name?: string
  opportunityType?: string
  description?: string
  enabled: boolean
  version?: string
  ruleVersion?: string
  parameters?: RuleParameter[] | Record<string, string | number | boolean>
  lifecyclePolicy?: RuleLifecyclePolicy
  updatedAt?: string
  updatedBy?: string
}

export interface EngineInfo {
  engineVersion?: string
  activeRuleVersion?: string
  ruleVersion?: string
  status?: string
  lastRunAt?: string
  generatedAt?: string
  [key: string]: unknown
}

export interface ListQuery {
  pageSize?: number
  cursor?: string
  sort?: string
  q?: string
  [key: string]: string | number | boolean | undefined
}

export interface CreateActionInput {
  actionType: ActionType
  dueAt?: string
  note?: string
}

export interface UpdateActionInput {
  status?: string
  outcome?: Outcome
  dueAt?: string
  note?: string
}

export interface UpdateRuleInput {
  enabled?: boolean
  parameters?: Record<string, string | number | boolean>
  justification: string
  effectiveAt?: string
}

export type RuleStatus = 'DRAFT' | 'VALIDATED' | 'SIMULATED' | 'SUBMITTED' | 'APPROVED' | 'PUBLISHED' | 'ACTIVE' | 'DISABLED' | 'RETIRED'
export type RuleLogic = 'AND' | 'OR' | 'NOT'
export type RuleOperator = 'GREATER_THAN' | 'GREATER_THAN_OR_EQUAL' | 'LESS_THAN' | 'LESS_THAN_OR_EQUAL' | 'EQUAL' | 'NOT_EQUAL' | 'BETWEEN' | 'IN' | 'NOT_IN' | 'INCREASE_BY' | 'DECREASE_BY' | 'PERSISTENT_FOR'
export type RuleUnit = 'PERCENT' | 'MAD' | 'COUNT' | 'RATIO' | 'DAYS' | 'BOOLEAN'

export interface RuleConditionDefinition {
  id?: string
  type?: 'CONDITION'
  metric: string
  operator: RuleOperator
  value: number | string | boolean | Array<number | string>
  unit: RuleUnit | string
  period: string
  weight?: number
}

export interface RuleConditionGroup {
  id?: string
  type?: 'GROUP'
  logic: RuleLogic
  conditions: RuleExpression[]
}

export type RuleExpression = RuleConditionDefinition | RuleConditionGroup

export interface RuleScope {
  segment: string[]
  sectors: string[]
  regions?: string[]
}

export interface RuleRecommendation {
  opportunityType: string
  products: string[]
  horizon: string
}

export interface RuleConfidenceConfiguration {
  baseScore: number
  weights: Record<string, number>
  highThreshold?: number
  mediumThreshold?: number
}

export interface RuleLifecyclePolicy {
  validityDays: number
  dismissedCooldownDays: number
  convertedCooldownDays: number
  deferredCooldownDays: number
  expiredCooldownDays: number
}

export interface RuleDefinition {
  ruleId: string
  version: number | string
  name: string
  description?: string
  status: RuleStatus
  enabled?: boolean
  scope: RuleScope
  conditions: RuleExpression[]
  logic: RuleLogic
  recommendation: RuleRecommendation
  confidence: RuleConfidenceConfiguration
  lifecycle: RuleLifecyclePolicy
  createdBy?: string
  updatedBy?: string
  createdAt?: string
  updatedAt?: string
  submittedBy?: string
  approvedBy?: string
}

export interface SaveRuleInput {
  name: string
  description?: string
  scope: RuleScope
  conditions: RuleExpression[]
  logic: RuleLogic
  recommendation: RuleRecommendation
  confidence: RuleConfidenceConfiguration
  lifecycle: RuleLifecyclePolicy
  reason?: string
}

export interface RuleValidationResult {
  valid: boolean
  errors?: Array<{ path?: string; code?: string; message: string }>
  warnings?: Array<{ code?: string; message: string }>
  validatedAt?: string
}

export interface RulePreviewCustomer {
  customerId: string
  company?: string
  legalName?: string
  signals?: string[]
  values?: Record<string, number | string | boolean>
  confidence: number
  opportunityType?: string
}

export interface ImpactBucket {
  name?: string
  sector?: string
  region?: string
  segment?: string
  count: number
  rate?: number
}

export interface RuleSimulationResult {
  simulationId?: string
  status?: string
  period?: { from: string; to: string }
  populationAnalyzed: number
  matchedCustomers: number
  expectedMatches?: number
  highConfidence?: number
  mediumConfidence?: number
  lowConfidence?: number
  conversionRate?: number | 'NOT_AVAILABLE' | null
  potentialOpportunities?: number
  averageOpportunitiesPerRm?: number
  matchRate?: number
  topCustomers?: RulePreviewCustomer[]
  customers?: RulePreviewCustomer[]
  impact?: {
    populationAffected?: number
    opportunitiesGenerated?: number
    averageOpportunitiesPerRm?: number
    bySector?: ImpactBucket[]
    byRegion?: ImpactBucket[]
    bySegment?: ImpactBucket[]
  }
  warnings?: Array<{ code?: string; message: string; affectedRate?: number } | string>
  createdAt?: string
}

export interface RuleSimulationInput {
  period: { from: string; to: string }
  population: { segment: string; sectors?: string[]; regions?: string[] }
}

export interface RuleTestEvidence {
  conditionId?: string
  metric: string
  actual: number | string | boolean | null
  operator?: RuleOperator
  threshold: number | string | boolean | Array<number | string>
  unit?: string
  period?: string
  result: boolean
  message?: string
}

export interface RuleTestResult {
  matched: boolean
  ruleId: string
  ruleVersion: number | string
  engineVersion?: string
  customerId: string
  customerName?: string
  opportunityType?: string
  confidence: number
  evidence: RuleTestEvidence[]
  evaluatedAt?: string
}

export interface RuleVersionSummary {
  ruleId: string
  version: number | string
  status: RuleStatus
  createdAt?: string
  createdBy?: string
  reason?: string
  changes?: string[] | Record<string, unknown>
}

export interface RuleAuditEntry {
  id: string
  ruleId: string
  ruleVersion: number | string
  action: 'CREATED' | 'UPDATED' | 'VALIDATED' | 'SIMULATED' | 'SUBMITTED' | 'APPROVED' | 'PUBLISHED' | 'DISABLED' | 'ROLLED_BACK' | string
  userId: string
  timestamp: string
  oldValue?: unknown
  newValue?: unknown
  reason?: string
}

export interface RuleLifecycleInput {
  reason: string
  version?: number | string
}


export interface LabelCatalogEntry {
  namespace: string
  code: string
  locale: string
  label: string
  active: boolean
  version: number
  updatedAt: string
  updatedBy: string
  justification: string
}

export interface LabelCatalogResponse {
  locale: string
  labels: Record<string, string>
  data: LabelCatalogEntry[]
}

export interface LabelCatalogVersion {
  version: number
  label: string
  active: boolean
  createdAt: string
  createdBy: string
  justification: string
}


export interface NotificationDigestSubscription {
  relationshipManagerId: string
  recipientEmail: string
  timezone: string
  deliveryHour: number
  enabled: boolean
  lastDigestDate?: string | null
  updatedAt: string
}

export interface NotificationDelivery {
  notificationId: string
  type: 'ACTION_DUE_REMINDER' | 'PORTFOLIO_DAILY_DIGEST'
  recipient: string
  subject: string
  status: 'PENDING' | 'SENDING' | 'RETRY' | 'SENT' | 'DELIVERY_UNCERTAIN' | 'DEAD_LETTER'
  attemptCount: number
  maxAttempts: number
  nextAttemptAt: string
  sentAt?: string | null
  providerMessageId?: string | null
  lastError?: string | null
  correlationId: string
  createdAt: string
}
