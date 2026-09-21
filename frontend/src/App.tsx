import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { configureApiAuth } from './api/client'
import { setRuntimeLabels } from './api/format'
import { useLabelCatalog } from './api/hooks'
import { AuthProvider, useAuth } from './auth/AuthProvider'
import { MlStudioRoute, ProtectedRoute, RoleRoute, RuleStudioRoute } from './auth/ProtectedRoute'
import { AuditPage, BackOfficeHomePage, EngineThresholdsPage, LabelsPage, ModelsPage, NotificationsPage, SimulationsPage } from './features/backoffice/BackOfficePages'
import { BranchDashboardPage } from './features/branch/BranchDashboardPage'
import { RmPortfolioPage } from './features/branch/RmPortfolioPage'
import { CustomerSheetPage } from './features/customer/CustomerSheetPage'
import { CcDashboardPage } from './features/dashboard/CcDashboardPage'
import { DemoProvider } from './features/demo/DemoGuide'
import { MlStudioPage } from './features/ml-studio/MlStudioPage'
import { RuleBuilderPage } from './features/rules/RuleBuilderPage'
import { RuleDetailPage } from './features/rules/RuleDetailPage'
import { RuleStudioPage } from './features/rules/RuleStudioPage'
import { AppShell } from './layout/AppShell'
import { ActionsPage } from './pages/ActionsPage'
import { CustomersPage } from './pages/CustomersPage'
import { LoginPage } from './pages/LoginPage'
import { OpportunitiesPage, OpportunityRedirectPage } from './pages/OpportunitiesPage'
import { ProductsPage } from './pages/ProductsPage'
import { SignalsPage } from './pages/SignalsPage'
import { ForbiddenPage, NotFoundPage } from './pages/StatusPages'
import { ToastProvider } from './ui'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 45_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof Error && 'status' in error && [400, 401, 403, 404, 409, 422].includes(Number((error as { status: number }).status))) && count < 2,
    },
    mutations: { retry: false },
  },
})

function ApiAuthBridge() {
  const auth = useAuth()
  const navigate = useNavigate()
  configureApiAuth(() => auth.token, () => navigate('/login', { replace: true }), () => auth.devPersonaHeader)
  const catalog = useLabelCatalog(false, auth.authenticated)
  useEffect(() => setRuntimeLabels(auth.authenticated ? catalog.data?.labels : undefined), [auth.authenticated, catalog.data])
  return null
}

function HomeRoute() {
  const { hasRole } = useAuth()
  if (hasRole('BRANCH_MANAGER')) return <BranchDashboardPage />
  if (hasRole('RELATIONSHIP_MANAGER')) return <CcDashboardPage />
  return <Navigate to="/back-office" replace />
}

function DemoRoot() {
  const auth = useAuth()
  return <DemoProvider onPersona={(persona) => { if (auth.devMode && persona && auth.persona?.id !== persona) auth.selectPersona(persona) }}>
    <AppShell />
  </DemoProvider>
}

function ApplicationRoutes() {
  return <>
    <ApiAuthBridge />
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/interdit" element={<ForbiddenPage />} />
      <Route path="/" element={<ProtectedRoute><DemoRoot /></ProtectedRoute>}>
        <Route index element={<HomeRoute />} />
        <Route path="clients" element={<CustomersPage />} />
        <Route path="clients/:customerId" element={<CustomerSheetPage />} />
        <Route path="agence/cc/:relationshipManagerId" element={<RoleRoute roles={['BRANCH_MANAGER']}><RmPortfolioPage /></RoleRoute>} />
        <Route path="opportunites" element={<OpportunitiesPage />} />
        <Route path="opportunites/:opportunityId" element={<OpportunityRedirectPage />} />
        <Route path="signaux" element={<SignalsPage />} />
        <Route path="actions" element={<ActionsPage />} />
        <Route path="produits" element={<ProductsPage />} />
        <Route path="back-office" element={<RuleStudioRoute><BackOfficeHomePage /></RuleStudioRoute>} />
        <Route path="back-office/opportunites" element={<RuleStudioRoute><OpportunitiesPage /></RuleStudioRoute>} />
        <Route path="back-office/produits" element={<RuleStudioRoute><ProductsPage /></RuleStudioRoute>} />
        <Route path="back-office/seuils" element={<RoleRoute roles={['ADMIN']}><EngineThresholdsPage /></RoleRoute>} />
        <Route path="back-office/regles" element={<RuleStudioRoute><RuleStudioPage /></RuleStudioRoute>} />
        <Route path="back-office/regles/nouvelle" element={<RuleStudioRoute><RuleBuilderPage /></RuleStudioRoute>} />
        <Route path="back-office/regles/:ruleId" element={<RuleStudioRoute><RuleDetailPage /></RuleStudioRoute>} />
        <Route path="back-office/regles/:ruleId/modifier" element={<RuleStudioRoute><RuleBuilderPage /></RuleStudioRoute>} />
        <Route path="back-office/studio-ml" element={<MlStudioRoute><MlStudioPage /></MlStudioRoute>} />
        <Route path="back-office/simulations" element={<RuleStudioRoute><SimulationsPage /></RuleStudioRoute>} />
        <Route path="back-office/modeles" element={<RuleStudioRoute><ModelsPage /></RuleStudioRoute>} />
        <Route path="back-office/audit" element={<RuleStudioRoute><AuditPage /></RuleStudioRoute>} />
        <Route path="back-office/libelles" element={<RoleRoute roles={['ADMIN']}><LabelsPage /></RoleRoute>} />
        <Route path="back-office/notifications" element={<RoleRoute roles={['ADMIN']}><NotificationsPage /></RoleRoute>} />
        <Route path="rule-studio/*" element={<Navigate to="/back-office/regles" replace />} />
        <Route path="administration" element={<Navigate to="/back-office/seuils" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  </>
}

export default function App() {
  return <QueryClientProvider client={queryClient}><BrowserRouter><AuthProvider><ToastProvider><ApplicationRoutes /></ToastProvider></AuthProvider></BrowserRouter></QueryClientProvider>
}
