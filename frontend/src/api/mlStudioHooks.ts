import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, buildSearch } from './client'
import type {
  ApiPage,
  MlDatasetManifest,
  MlDatasetManifestInput,
  MlGovernanceAudit,
  MlGovernanceRun,
  MlModelComparison,
  MlOutcomeMaterializationInput,
  MlOutcomeMaterializationResult,
  MlStudioSummary,
  MlTrainingJob,
  ScoringPolicyView,
  ScoringPolicyVersionView,
} from './types'

const governancePath = '/api/v1/admin/ml/governance'
export const ML_TRAINING_POLL_INTERVAL_MS = 2_000
export const ML_TERMINAL_STATUSES = ['SUCCEEDED', 'FAILED', 'INSUFFICIENT_DATA', 'CANCELLED'] as const

export const trainingPollInterval = (job?: Pick<MlTrainingJob, 'terminal' | 'status'>) => (
  job && !job.terminal && !ML_TERMINAL_STATUSES.includes(job.status as typeof ML_TERMINAL_STATUSES[number])
    ? ML_TRAINING_POLL_INTERVAL_MS
    : false
)

export const useMlStudioSummary = () => useQuery({
  queryKey: ['ml-studio', 'summary'],
  queryFn: () => apiRequest<MlStudioSummary>(`${governancePath}/studio-summary`),
})

export const useMlManifests = () => useQuery({
  queryKey: ['ml-studio', 'manifests'],
  queryFn: () => apiRequest<ApiPage<MlDatasetManifest>>('/api/v1/admin/ml/datasets/manifests'),
})

export function useMaterializeMlOutcomes() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: MlOutcomeMaterializationInput) => apiRequest<MlOutcomeMaterializationResult>('/api/v1/admin/ml/outcomes/materialize', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'summary'] }),
  })
}

export function useCreateMlManifest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: MlDatasetManifestInput) => apiRequest<MlDatasetManifest>('/api/v1/admin/ml/datasets/manifests', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'manifests'] }),
  })
}

export const useMlTrainingHistory = () => useQuery({
  queryKey: ['ml-studio', 'trainings'],
  queryFn: () => apiRequest<ApiPage<MlTrainingJob>>(`${governancePath}/trainings?pageSize=100`),
})

export const useMlTraining = (jobId?: string) => useQuery({
  queryKey: ['ml-studio', 'training', jobId],
  queryFn: () => apiRequest<MlTrainingJob>(`${governancePath}/trainings/${encodeURIComponent(jobId || '')}`),
  enabled: Boolean(jobId),
  refetchInterval: (query) => trainingPollInterval(query.state.data),
})

export function useStartMlTraining() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { manifestId: string; algorithm: 'LOGISTIC_REGRESSION'; seed: number; justification: string }) => apiRequest<MlTrainingJob>(`${governancePath}/trainings`, {
      method: 'POST',
      body: JSON.stringify(input),
      idempotencyKey: `ml-training-${input.manifestId}-${crypto.randomUUID()}`,
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'trainings'] }),
  })
}

export function useCancelMlTraining() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => apiRequest<MlTrainingJob>(`${governancePath}/trainings/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
    onSuccess: (job) => {
      queryClient.setQueryData(['ml-studio', 'training', job.id], job)
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'trainings'] })
    },
  })
}

export function useRegisterMlRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (result: NonNullable<MlTrainingJob['result']>) => apiRequest<{ run: MlGovernanceRun }>(`${governancePath}/runs`, {
      method: 'POST',
      body: JSON.stringify(result),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'runs'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'summary'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'audits'] })
    },
  })
}

export const useMlGovernanceRuns = () => useQuery({
  queryKey: ['ml-studio', 'runs'],
  queryFn: () => apiRequest<{ runs: MlGovernanceRun[]; count: number; mode?: string }>(`${governancePath}/runs`),
})

export const useMlModelComparison = (left?: string, right?: string) => useQuery({
  queryKey: ['ml-studio', 'comparison', left, right],
  queryFn: () => apiRequest<MlModelComparison>(`${governancePath}/model-comparisons${buildSearch({ left, right })}`),
  enabled: Boolean(left && right && left !== right),
})

export const useMlGovernanceAudits = () => useQuery({
  queryKey: ['ml-studio', 'audits'],
  queryFn: () => apiRequest<{ audits: MlGovernanceAudit[] }>(`${governancePath}/audits`),
})

export const useScoringPolicies = () => useQuery({
  queryKey: ['ml-studio', 'scoring-policies'],
  queryFn: () => apiRequest<ApiPage<ScoringPolicyView>>('/api/v1/admin/scoring-policies?pageSize=100'),
})

export const useActiveScoringPolicy = () => useQuery({
  queryKey: ['ml-studio', 'scoring-policy', 'active'],
  queryFn: () => apiRequest<ScoringPolicyVersionView>('/api/v1/admin/scoring-policies/active'),
  retry: false,
})

export function useCreateScoringPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { policyId: string; weights: { rules: number; ml: number }; reason: string }) => apiRequest<ScoringPolicyView>('/api/v1/admin/scoring-policies', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'scoring-policies'] }),
  })
}

export function useCreateScoringPolicyVersion(policyId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { weights: { rules: number; ml: number }; reason: string }) => apiRequest<ScoringPolicyVersionView>(`/api/v1/admin/scoring-policies/${encodeURIComponent(policyId)}/versions`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'scoring-policies'] }),
  })
}

export function useTransitionScoringPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ policyId, version, transition, ...input }: { policyId: string; version: number; transition: 'simulate' | 'submit' | 'approve' | 'publish' | 'activate'; reason: string; simulationId?: string; effectiveFrom?: string }) => apiRequest<ScoringPolicyVersionView>(`/api/v1/admin/scoring-policies/${encodeURIComponent(policyId)}/versions/${version}/${transition}`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'scoring-policies'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'scoring-policy', 'active'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'summary'] })
    },
  })
}

export function useTransitionMlRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ modelId, modelVersion, transition, reason }: { modelId: string; modelVersion: string; transition: 'submit' | 'approve' | 'promote'; reason: string }) => apiRequest<{ run: MlGovernanceRun }>(`${governancePath}/runs/${encodeURIComponent(modelId)}/${encodeURIComponent(modelVersion)}/${transition}`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'runs'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'audits'] })
      void queryClient.invalidateQueries({ queryKey: ['ml-studio', 'summary'] })
    },
  })
}
