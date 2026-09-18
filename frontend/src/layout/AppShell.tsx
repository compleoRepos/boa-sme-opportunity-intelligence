import { useState } from 'react'
import { Activity, BriefcaseBusiness, Building2, ChevronDown, ClipboardCheck, GitBranch, LayoutDashboard, LogOut, Menu, PackageSearch, Settings2, ShieldCheck, X } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

const globalNavigation = [
  { to: '/', label: 'Vue d’ensemble', icon: LayoutDashboard, end: true },
  { to: '/opportunites', label: 'Opportunités', icon: BriefcaseBusiness },
  { to: '/clients', label: 'Clients', icon: Building2 },
  { to: '/signaux', label: 'Signaux', icon: Activity },
  { to: '/actions', label: 'Actions', icon: ClipboardCheck },
  { to: '/produits', label: 'Catalogue', icon: PackageSearch },
]

const commercialNavigation = [
  { to: '/', label: 'Vue d’ensemble', icon: LayoutDashboard, end: true },
  { to: '/clients', label: 'Portefeuille PME', icon: Building2 },
]

export function AppShell() {
  const { displayName, username, roles, hasRole, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const initials = displayName.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  const canUseRuleStudio = hasRole('BUSINESS_ANALYST') || hasRole('RULE_APPROVER') || hasRole('ADMIN')
  const isBranchManager = hasRole('BRANCH_MANAGER')
  const isCommercial = isBranchManager || hasRole('RELATIONSHIP_MANAGER')
  const navigation = isCommercial ? commercialNavigation : globalNavigation
  const roleLabel = isBranchManager ? 'Responsable d’agence' : hasRole('RELATIONSHIP_MANAGER') ? 'Chargé de clientèle PME' : roles[0]?.replaceAll('_', ' ') || username

  return <div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Fermer le menu" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand">
        <div className="brand-mark" aria-hidden="true"><span>BOA</span></div>
        <div><strong>BANK OF AFRICA</strong><small>SME Opportunity Intelligence</small></div>
        <button type="button" className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Fermer"><X /></button>
      </div>
      <div className="scope-label">{isBranchManager ? 'PILOTAGE COMMERCIAL AGENCE' : 'MON PORTEFEUILLE PME'}</div>
      <nav className="sidebar-nav" aria-label="Navigation principale">
        {navigation.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={() => setMobileOpen(false)}><Icon size={19} /><span>{label}</span></NavLink>)}
        {canUseRuleStudio && <><div className="scope-label nav-separator">RÈGLES MÉTIER</div><NavLink to="/rule-studio" onClick={() => setMobileOpen(false)}><GitBranch size={19} /><span>Rule Studio</span></NavLink></>}
        {hasRole('ADMIN') && <><div className="scope-label nav-separator">GOUVERNANCE</div><NavLink to="/administration" onClick={() => setMobileOpen(false)}><Settings2 size={19} /><span>Administration</span></NavLink></>}
      </nav>
      <div className="sidebar-notice"><ShieldCheck size={18} /><div><strong>Données synthétiques</strong><span>Aucune décision de crédit</span></div></div>
    </aside>
    <div className="app-main">
      <header className="topbar">
        <button type="button" className="menu-button" onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu"><Menu /></button>
        <div className="topbar-context"><span>{isBranchManager ? 'Vue agence consolidée' : 'Mon portefeuille PME'}</span><strong>Intelligence commerciale</strong></div>
        <div className="profile-wrap">
          <button type="button" className="profile-button" onClick={() => setProfileOpen((value) => !value)} aria-expanded={profileOpen} aria-haspopup="menu" aria-label={`Menu du profil de ${displayName}`}>
            <span className="avatar">{initials}</span><span className="profile-copy"><strong>{displayName}</strong><small>{roleLabel}</small></span><ChevronDown size={16} />
          </button>
          {profileOpen && <div className="profile-menu"><div><strong>{displayName}</strong><span>{username}</span></div><button type="button" onClick={() => void logout()}><LogOut size={16} /> Se déconnecter</button></div>}
        </div>
      </header>
      <main className="content"><Outlet /></main>
    </div>
  </div>
}
