import { useQuery } from '@tanstack/react-query'
import { apiRequest } from './client'
import {
  fiCompanyPath,
  fiPortfolioCatalogPath,
  fiPortfolioSummaryPath,
  parseFiEnvelope,
  type FiCashPosition,
  type FiCompanySummary,
  type FiEnvelope,
  type FiFlowSummary,
  type FiOpportunity,
  type FiPortfolioCatalog,
  type FiPortfolioSummary,
  type FiSignal,
} from './financialIntelligence.types'

async function getFiEnvelope<T>(path: string) {
  return parseFiEnvelope<T>(await apiRequest<unknown>(path))
}

export const useFiPortfolioSummary = (portfolioId?: string, asOf?: string) => useQuery<FiEnvelope<FiPortfolioSummary>>({
  queryKey: ['financial-intelligence', 'portfolio', portfolioId, 'summary', asOf],
  queryFn: () => getFiEnvelope<FiPortfolioSummary>(fiPortfolioSummaryPath(portfolioId || '', asOf || '')),
  enabled: Boolean(portfolioId && asOf),
})

export const useFiPortfolioCatalog = (asOf?: string) => useQuery<FiEnvelope<FiPortfolioCatalog>>({
  queryKey: ['financial-intelligence', 'portfolios', asOf],
  queryFn: () => getFiEnvelope<FiPortfolioCatalog>(fiPortfolioCatalogPath(asOf || '')),
  enabled: Boolean(asOf),
})

export const useFiCompanySummary = (companyId?: string, asOf?: string) => useQuery<FiEnvelope<FiCompanySummary>>({
  queryKey: ['financial-intelligence', 'company', companyId, 'summary', asOf],
  queryFn: () => getFiEnvelope<FiCompanySummary>(fiCompanyPath(companyId || '', 'summary', asOf || '')),
  enabled: Boolean(companyId && asOf),
})

export const useFiCompanySignals = (companyId?: string, asOf?: string) => useQuery<FiEnvelope<FiSignal[]>>({
  queryKey: ['financial-intelligence', 'company', companyId, 'signals', asOf],
  queryFn: () => getFiEnvelope<FiSignal[]>(fiCompanyPath(companyId || '', 'signals', asOf || '')),
  enabled: Boolean(companyId && asOf),
})

export const useFiCompanyOpportunities = (companyId?: string, asOf?: string) => useQuery<FiEnvelope<FiOpportunity[]>>({
  queryKey: ['financial-intelligence', 'company', companyId, 'opportunities', asOf],
  queryFn: () => getFiEnvelope<FiOpportunity[]>(fiCompanyPath(companyId || '', 'opportunities', asOf || '')),
  enabled: Boolean(companyId && asOf),
})

export const useFiCompanyCashPosition = (companyId?: string, asOf?: string) => useQuery<FiEnvelope<FiCashPosition>>({
  queryKey: ['financial-intelligence', 'company', companyId, 'cash-position', asOf],
  queryFn: () => getFiEnvelope<FiCashPosition>(fiCompanyPath(companyId || '', 'cash-position', asOf || '')),
  enabled: Boolean(companyId && asOf),
})

export const useFiCompanyFlowSummary = (companyId?: string, asOf?: string) => useQuery<FiEnvelope<FiFlowSummary>>({
  queryKey: ['financial-intelligence', 'company', companyId, 'flow-summary', asOf],
  queryFn: () => getFiEnvelope<FiFlowSummary>(fiCompanyPath(companyId || '', 'flow-summary', asOf || '')),
  enabled: Boolean(companyId && asOf),
})
