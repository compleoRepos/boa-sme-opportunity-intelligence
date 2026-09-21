import { useMemo } from 'react'
import { matchPath, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

export interface Crumb { label: string; to?: string }

const staticLabels: Array<[string, string]> = [
  ['/opportunites', 'Opportunités'],
  ['/clients', 'PME'],
  ['/signaux', 'Signaux'],
  ['/actions', 'Actions'],
  ['/produits', 'Catalogue'],
  ['/back-office', 'Back office'],
  ['/back-office/regles', 'Rule Studio'],
  ['/back-office/studio-ml', 'Studio ML'],
  ['/back-office/simulations', 'Simulations'],
  ['/back-office/modeles', 'ML Governance'],
  ['/back-office/audit', 'Audit'],
  ['/back-office/opportunites', 'Opportunités'],
  ['/back-office/produits', 'Produits'],
  ['/back-office/seuils', 'Seuils moteur'],
]

export function useBreadcrumbs(): Crumb[] {
  const location = useLocation()
  const auth = useAuth()
  return useMemo(() => {
    const root: Crumb = { label: auth.hasRole('BRANCH_MANAGER') ? 'Pilotage agence' : auth.hasRole('RELATIONSHIP_MANAGER') ? 'Mon portefeuille PME' : 'Intelligence commerciale', to: '/' }
    const path = location.pathname
    const crumbs: Crumb[] = [root]
    if (path === '/') return crumbs
    const customer = matchPath('/clients/:customerId', path)
    if (customer) return [...crumbs, { label: 'PME', to: '/clients' }, { label: customer.params.customerId || '' }]
    const rm = matchPath('/agence/cc/:relationshipManagerId', path)
    if (rm) return [...crumbs, { label: 'Portefeuille CC' }, { label: rm.params.relationshipManagerId || '' }]
    const rule = matchPath('/back-office/regles/:ruleId/*', path) || matchPath('/back-office/regles/:ruleId', path)
    if (rule && rule.params.ruleId && rule.params.ruleId !== 'nouvelle') {
      const tail = path.endsWith('/modifier') ? [{ label: 'Modifier' }] : []
      return [...crumbs, { label: 'Back office', to: '/back-office' }, { label: 'Rule Studio', to: '/back-office/regles' }, { label: rule.params.ruleId, to: `/back-office/regles/${rule.params.ruleId}` }, ...tail]
    }
    if (path === '/back-office/regles/nouvelle') return [...crumbs, { label: 'Rule Studio', to: '/back-office/regles' }, { label: 'Nouvelle règle' }]
    const opportunity = matchPath('/opportunites/:opportunityId', path)
    if (opportunity) return [...crumbs, { label: 'Opportunités', to: '/opportunites' }, { label: 'Détail' }]
    const known = staticLabels.filter(([prefix]) => path === prefix || path.startsWith(`${prefix}/`)).sort((a, b) => b[0].length - a[0].length)[0]
    if (known) {
      const parent = known[0].startsWith('/back-office/') ? [{ label: 'Back office', to: '/back-office' }] : []
      return [...crumbs, ...parent, { label: known[1] }]
    }
    return crumbs
  }, [location.pathname, auth])
}
