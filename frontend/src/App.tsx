import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { configureApiAuth } from './api/client'
import { AdminRoute, ProtectedRoute, RoleRoute, RuleStudioRoute } from './auth/ProtectedRoute'
import { AuthProvider, useAuth } from './auth/AuthProvider'
import { AppShell } from './layout/AppShell'
import { ActionsPage } from './pages/ActionsPage'
import { AdminPage } from './pages/AdminPage'
import { Customer360Page } from './pages/Customer360Page'
import { CustomersPage } from './pages/CustomersPage'
import { BranchManagerDashboard, RelationshipManagerDashboard } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { OpportunitiesPage } from './pages/OpportunitiesPage'
import { OpportunityDetailPage } from './pages/OpportunityDetailPage'
import { ProductsPage } from './pages/ProductsPage'
import { RelationshipManagerPortfolioPage } from './pages/RelationshipManagerPortfolioPage'
import { RuleDetailPage } from './pages/RuleDetailPage'
import { RuleEditorPage } from './pages/RuleEditorPage'
import { RuleStudioPage } from './pages/RuleStudioPage'
import { SignalsPage } from './pages/SignalsPage'
import { ForbiddenPage, NotFoundPage } from './pages/StatusPages'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: (count, error) => !(error instanceof Error && 'status' in error && [401, 403, 404].includes(Number((error as { status: number }).status))) && count < 2 },
    mutations: { retry: false },
  },
})

function ApiAuthBridge() {
  const auth = useAuth()
  const navigate = useNavigate()
  useEffect(() => {
    configureApiAuth(() => auth.token, () => navigate('/login', { replace: true }))
  }, [auth.token, navigate])
  return null
}

function RoleDashboardRoute() {
  const { hasRole } = useAuth()
  return hasRole('BRANCH_MANAGER') ? <BranchManagerDashboard /> : <RelationshipManagerDashboard />
}

function ApplicationRoutes() {
  return <>
    <ApiAuthBridge />
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/interdit" element={<ForbiddenPage />} />
      <Route path="/" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<RoleDashboardRoute />} />
        <Route path="opportunites" element={<OpportunitiesPage />} />
        <Route path="opportunites/:opportunityId" element={<OpportunityDetailPage />} />
        <Route path="clients" element={<CustomersPage />} />
        <Route path="portefeuilles/:relationshipManagerId" element={<RoleRoute roles={['BRANCH_MANAGER']}><RelationshipManagerPortfolioPage /></RoleRoute>} />
        <Route path="clients/:customerId" element={<Customer360Page />} />
        <Route path="signaux" element={<SignalsPage />} />
        <Route path="actions" element={<ActionsPage />} />
        <Route path="produits" element={<ProductsPage />} />
        <Route path="rule-studio" element={<RuleStudioRoute><RuleStudioPage /></RuleStudioRoute>} />
        <Route path="rule-studio/nouvelle" element={<RuleStudioRoute><RuleEditorPage /></RuleStudioRoute>} />
        <Route path="rule-studio/:ruleId" element={<RuleStudioRoute><RuleDetailPage /></RuleStudioRoute>} />
        <Route path="rule-studio/:ruleId/modifier" element={<RuleStudioRoute><RuleEditorPage /></RuleStudioRoute>} />
        <Route path="administration" element={<AdminRoute><AdminPage /></AdminRoute>} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  </>
}

export default function App() {
  return <QueryClientProvider client={queryClient}><BrowserRouter><AuthProvider><ApplicationRoutes /></AuthProvider></BrowserRouter></QueryClientProvider>
}
