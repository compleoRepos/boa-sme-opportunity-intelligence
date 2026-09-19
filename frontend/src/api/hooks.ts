import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, buildSearch } from './client'
import type {
  Account,
  ActivitySeries,
  ApiPage,
  BranchDashboard,
  CreateActionInput,
  Customer,
  CustomerPropensity,
  DashboardKpis,
  EngineInfo,
  Explanation,
  FinancialMetric,
  LabelCatalogEntry,
  LabelCatalogResponse,
  ListQuery,
  MlModel,
  Opportunity,
  OpportunityAction,
  Product,
  RelationshipManagerDashboard,
  RuleConfig,
  Signal,
  Transaction,
  UpdateActionInput,
  UpdateRuleInput,
} from './types'

const pageQuery = <T,>(key: string, params: ListQuery = {}) => ({
  queryKey: [key, params],
  queryFn: () => apiRequest<ApiPage<T>>(`/api/v1/${key}${buildSearch(params)}`),
  placeholderData: keepPreviousData,
})

export const useDashboard = () => useQuery({
  queryKey: ['metrics', 'dashboard'],
  queryFn: () => apiRequest<DashboardKpis>('/api/v1/metrics/dashboard'),
})

export const useRelationshipManagerDashboard = (enabled = true) => useQuery({
  queryKey: ['dashboards', 'me'],
  queryFn: () => apiRequest<RelationshipManagerDashboard>('/api/v1/dashboards/me'),
  enabled,
})

export const useBranchDashboard = (enabled = true) => useQuery({
  queryKey: ['dashboards', 'branch'],
  queryFn: () => apiRequest<BranchDashboard>('/api/v1/dashboards/branch'),
  enabled,
})

export const useRelationshipManagerPortfolio = (relationshipManagerId?: string) => useQuery({
  queryKey: ['dashboards', 'relationship-manager', relationshipManagerId],
  queryFn: () => apiRequest<RelationshipManagerDashboard>(
    `/api/v1/dashboards/relationship-managers/${encodeURIComponent(relationshipManagerId || '')}`,
  ),
  enabled: Boolean(relationshipManagerId),
})

export const useOpportunities = (params: ListQuery) => useQuery(pageQuery<Opportunity>('opportunities', params))
export const useOpportunity = (id?: string) => useQuery({
  queryKey: ['opportunity', id],
  queryFn: () => apiRequest<Opportunity>(`/api/v1/opportunities/${id}`),
  enabled: Boolean(id),
})
export const useExplanation = (id?: string) => useQuery({
  queryKey: ['opportunity', id, 'explanation'],
  queryFn: () => apiRequest<Explanation>(`/api/v1/opportunities/${id}/explanation`),
  enabled: Boolean(id),
})
export const useOpportunityActions = (id?: string) => useQuery({
  queryKey: ['opportunity', id, 'actions'],
  queryFn: () => apiRequest<ApiPage<OpportunityAction>>(`/api/v1/opportunities/${id}/actions?pageSize=100`),
  enabled: Boolean(id),
})

export const useCustomers = (params: ListQuery) => useQuery(pageQuery<Customer>('customers', params))
export const useCustomer = (id?: string) => useQuery({
  queryKey: ['customer', id],
  queryFn: () => apiRequest<Customer>(`/api/v1/customers/${id}`),
  enabled: Boolean(id),
})
export const useCustomerPropensity = (id?: string) => useQuery({
  queryKey: ['customer', id, 'propensity'],
  queryFn: () => apiRequest<CustomerPropensity>(`/api/v1/customers/${id}/propensity`),
  enabled: Boolean(id),
})

function customerPage<T>(id: string | undefined, resource: string, params: ListQuery = {}) {
  return useQuery({
    queryKey: ['customer', id, resource, params],
    queryFn: () => apiRequest<ApiPage<T>>(`/api/v1/customers/${id}/${resource}${buildSearch(params)}`),
    enabled: Boolean(id),
  })
}

export const useCustomerAccounts = (id?: string) => customerPage<Account>(id, 'accounts', { pageSize: 100 })
export const useCustomerProducts = (id?: string) => customerPage<Product>(id, 'products', { pageSize: 100 })
export const useCustomerTransactions = (id?: string, params: ListQuery = {}) => customerPage<Transaction>(id, 'transactions', params)
export const useCustomerMetrics = (id?: string) => customerPage<FinancialMetric>(id, 'metrics', { pageSize: 100, sort: 'asOf' })
export const useCustomerSignals = (id?: string) => customerPage<Signal>(id, 'signals', { pageSize: 100, sort: '-detectedAt' })
export const useCustomerOpportunities = (id?: string) => customerPage<Opportunity>(id, 'opportunities', { pageSize: 100, sort: '-priorityScore' })
export const useCustomerActions = (id?: string) => customerPage<OpportunityAction>(id, 'actions', { pageSize: 100, sort: '-createdAt' })
export const useCustomerActivity = (id?: string, params: { granularity?: 'DAY' | 'WEEK' | 'MONTH'; fromDate?: string; toDate?: string } = {}) => useQuery({
  queryKey: ['customer', id, 'activity', params],
  queryFn: () => apiRequest<ActivitySeries>(`/api/v1/customers/${id}/activity${buildSearch(params)}`),
  enabled: Boolean(id),
  staleTime: 5 * 60_000,
})
export const useMlModels = () => useQuery({
  queryKey: ['ml', 'models'],
  queryFn: () => apiRequest<{ data: MlModel[]; meta: { totalCount: number } }>('/api/v1/ml/models'),
})
export const useActiveModel = () => useQuery({
  queryKey: ['ml', 'models', 'active'],
  queryFn: () => apiRequest<MlModel>('/api/v1/ml/models/active'),
})

export const useSignals = (params: ListQuery) => useQuery(pageQuery<Signal>('signals', params))
export const useProducts = (params: ListQuery) => useQuery(pageQuery<Product>('products', params))
export const useActions = (params: ListQuery) => useQuery(pageQuery<OpportunityAction>('actions', params))
export const useRules = () => useQuery({
  queryKey: ['admin', 'rules'],
  queryFn: () => apiRequest<ApiPage<RuleConfig>>('/api/v1/admin/rules?pageSize=100'),
})
export const useEngine = () => useQuery({
  queryKey: ['admin', 'engine'],
  queryFn: () => apiRequest<EngineInfo>('/api/v1/admin/engine'),
})

export const useLabelCatalog = (includeInactive = false, enabled = true) => useQuery({
  queryKey: ['labels', includeInactive],
  queryFn: () => apiRequest<LabelCatalogResponse>(`/api/v1/labels${includeInactive ? '?includeInactive=true' : ''}`),
  enabled,
})

export function useUpdateLabel(namespace: string, code: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { label: string; active: boolean; expectedVersion: number; justification: string }) => apiRequest<LabelCatalogEntry>(
      `/api/v1/admin/labels/${encodeURIComponent(namespace)}/${encodeURIComponent(code)}`,
      { method: 'PUT', body: JSON.stringify(input) },
    ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['labels'] }),
  })
}

export function useCreateAction(opportunityId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateActionInput) => apiRequest<OpportunityAction>(`/api/v1/opportunities/${opportunityId}/actions`, {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `ui-${opportunityId}-${input.actionType}-${crypto.randomUUID()}`,
    }),
    onSuccess: (action) => {
      void queryClient.invalidateQueries({ queryKey: ['opportunity', opportunityId] })
      void queryClient.invalidateQueries({ queryKey: ['opportunity', opportunityId, 'actions'] })
      void queryClient.invalidateQueries({ queryKey: ['actions'] })
      void queryClient.invalidateQueries({ queryKey: ['customer', action.customerId, 'actions'] })
      void queryClient.invalidateQueries({ queryKey: ['metrics', 'dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboards'] })
      void queryClient.invalidateQueries({ queryKey: ['customer', action.customerId, 'opportunities'] })
    },
  })
}

export function useUpdateAction(actionId: string, opportunityId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: UpdateActionInput) => apiRequest<OpportunityAction>(`/api/v1/actions/${actionId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),
    onSuccess: (action) => {
      void queryClient.invalidateQueries({ queryKey: ['actions'] })
      void queryClient.invalidateQueries({ queryKey: ['opportunity', opportunityId || action.opportunityId] })
      void queryClient.invalidateQueries({ queryKey: ['opportunity', opportunityId || action.opportunityId, 'actions'] })
      void queryClient.invalidateQueries({ queryKey: ['customer', action.customerId, 'actions'] })
      void queryClient.invalidateQueries({ queryKey: ['metrics', 'dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboards'] })
    },
  })
}

export function useUpdateRule(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: UpdateRuleInput) => apiRequest<RuleConfig>(`/api/v1/admin/rules/${ruleId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'rules'] })
      void queryClient.invalidateQueries({ queryKey: ['admin', 'engine'] })
    },
  })
}
