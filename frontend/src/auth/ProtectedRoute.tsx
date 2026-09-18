import { Navigate, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import { LoadingState } from '../components/UI'
import { useAuth } from './AuthProvider'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth()
  const location = useLocation()
  if (!auth.initialized) return <div className="center-screen"><LoadingState label="Vérification de votre session…" /></div>
  if (!auth.authenticated) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  return children
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const auth = useAuth()
  if (!auth.hasRole('ADMIN')) return <Navigate to="/interdit" replace />
  return children
}

export function RoleRoute({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const auth = useAuth()
  if (!roles.some((role) => auth.hasRole(role))) return <Navigate to="/interdit" replace />
  return children
}

export function RuleStudioRoute({ children }: { children: React.ReactNode }) {
  return <RoleRoute roles={['BUSINESS_ANALYST', 'RULE_APPROVER', 'ADMIN']}>{children}</RoleRoute>
}
