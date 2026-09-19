import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, buildSearch } from './client'
import type {
  ApiPage,
  ListQuery,
  RuleAuditEntry,
  RuleDefinition,
  RuleLifecycleInput,
  RuleSimulationHistoryEntry,
  RuleSimulationInput,
  RuleSimulationResult,
  RuleTestResult,
  RuleValidationResult,
  RuleVersionSummary,
  SaveRuleInput,
} from './types'

const rulesKey = ['rule-studio', 'rules'] as const

function invalidateRule(queryClient: ReturnType<typeof useQueryClient>, ruleId?: string) {
  void queryClient.invalidateQueries({ queryKey: rulesKey })
  if (ruleId) void queryClient.invalidateQueries({ queryKey: ['rule-studio', 'rule', ruleId] })
}

export const useStudioRules = (params: ListQuery = {}) => useQuery({
  queryKey: [...rulesKey, params],
  queryFn: () => apiRequest<ApiPage<RuleDefinition>>(`/api/v1/rules${buildSearch(params)}`),
  placeholderData: keepPreviousData,
})

export const useStudioRule = (ruleId?: string) => useQuery({
  queryKey: ['rule-studio', 'rule', ruleId],
  queryFn: () => apiRequest<RuleDefinition>(`/api/v1/rules/${ruleId}`),
  enabled: Boolean(ruleId),
})

export const useRuleVersions = (ruleId?: string) => useQuery({
  queryKey: ['rule-studio', 'rule', ruleId, 'versions'],
  queryFn: () => apiRequest<ApiPage<RuleVersionSummary>>(`/api/v1/rules/${ruleId}/versions?pageSize=100`),
  enabled: Boolean(ruleId),
})

export const useRuleAudit = (ruleId?: string) => useQuery({
  queryKey: ['rule-studio', 'rule', ruleId, 'audit'],
  queryFn: () => apiRequest<ApiPage<RuleAuditEntry>>(`/api/v1/rules/${ruleId}/audit?pageSize=100&sort=-timestamp`),
  enabled: Boolean(ruleId),
})

export const useRuleSimulations = (ruleId?: string) => useQuery({
  queryKey: ['rule-studio', 'rule', ruleId, 'simulations'],
  queryFn: () => apiRequest<{ ruleId: string; simulations: RuleSimulationHistoryEntry[] }>(`/api/v1/rules/${ruleId}/simulations`),
  enabled: Boolean(ruleId),
})

export function useCreateStudioRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SaveRuleInput) => apiRequest<RuleDefinition>('/api/v1/rules', {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `rule-create-${crypto.randomUUID()}`,
    }),
    onSuccess: () => invalidateRule(queryClient),
  })
}

export function useUpdateStudioRule(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SaveRuleInput) => apiRequest<RuleDefinition>(`/api/v1/rules/${ruleId}`, {
      method: 'PUT',
      body: JSON.stringify(input),
      idempotencyKey: `rule-update-${ruleId}-${crypto.randomUUID()}`,
    }),
    onSuccess: () => invalidateRule(queryClient, ruleId),
  })
}

export function useDuplicateStudioRule(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { name: string; reason: string }) => apiRequest<RuleDefinition>(`/api/v1/rules/${ruleId}/duplicate`, {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `rule-duplicate-${ruleId}-${crypto.randomUUID()}`,
    }),
    onSuccess: () => invalidateRule(queryClient),
  })
}

export function useValidateRule(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiRequest<RuleValidationResult>(`/api/v1/rules/${ruleId}/validate`, { method: 'POST', body: '{}' }),
    onSuccess: () => invalidateRule(queryClient, ruleId),
  })
}

export function useSimulateRule(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: RuleSimulationInput) => apiRequest<RuleSimulationResult>(`/api/v1/rules/${ruleId}/simulate`, {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `rule-simulate-${ruleId}-${crypto.randomUUID()}`,
    }),
    onSuccess: () => {
      invalidateRule(queryClient, ruleId)
      void queryClient.invalidateQueries({ queryKey: ['rule-studio', 'rule', ruleId, 'simulations'] })
    },
  })
}

export function useTestRule(ruleId: string) {
  return useMutation({
    mutationFn: (customerId: string) => apiRequest<RuleTestResult>(`/api/v1/rules/${ruleId}/test`, {
      method: 'POST',
      body: JSON.stringify({ customerId }),
      idempotencyKey: `rule-test-${ruleId}-${customerId}-${crypto.randomUUID()}`,
    }),
  })
}

type LifecycleAction = 'submit' | 'approve' | 'publish' | 'disable' | 'rollback'

export function useRuleLifecycle(ruleId: string, action: LifecycleAction) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: RuleLifecycleInput) => apiRequest<RuleDefinition>(`/api/v1/rules/${ruleId}/${action}`, {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `rule-${action}-${ruleId}-${crypto.randomUUID()}`,
    }),
    onSuccess: () => {
      invalidateRule(queryClient, ruleId)
      void queryClient.invalidateQueries({ queryKey: ['rule-studio', 'rule', ruleId, 'versions'] })
      void queryClient.invalidateQueries({ queryKey: ['rule-studio', 'rule', ruleId, 'audit'] })
    },
  })
}
