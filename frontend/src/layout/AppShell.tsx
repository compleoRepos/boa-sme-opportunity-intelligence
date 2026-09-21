import { Activity, BriefcaseBusiness, Building2, ChevronDown, ChevronRight, ClipboardCheck, Cpu, Database, FlaskConical, GitBranch, LayoutDashboard, LogOut, Menu, PackageSearch, Search, ShieldCheck, UserRound, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useRelationshipManagerDashboard } from '../api/hooks'
import { initials } from '../api/format'
import { useAuth } from '../auth/AuthProvider'
import { DemoLauncher } from '../features/demo/DemoGuide'
import { useDialogA11y } from '../ui/useDialogA11y'
import { useBreadcrumbs } from './breadcrumbs'

export function AppShell() {
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [mobileViewport, setMobileViewport] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [search, setSearch] = useState('')
  const profileRef = useRef<HTMLDivElement>(null)
  const mainRef = useRef<HTMLDivElement>(null)
  const skipLinkRef = useRef<HTMLAnchorElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const mobileModal = mobileViewport && mobileOpen
  const sidebarRef = useDialogA11y<HTMLElement>(() => setMobileOpen(false), { active: mobileModal, inertAppRoot: false })
  const isBranchManager = auth.hasRole('BRANCH_MANAGER')
  const isRm = auth.hasRole('RELATIONSHIP_MANAGER') && !isBranchManager
  const canMlStudio = auth.hasRole('ML_STEWARD') || auth.hasRole('RULE_APPROVER') || auth.hasRole('ADMIN')
  const canBackOffice = auth.hasRole('ADMIN') || auth.hasRole('BUSINESS_ANALYST') || auth.hasRole('RULE_APPROVER') || auth.hasRole('DATA_ANALYST') || auth.hasRole('ML_STEWARD')
  const dashboard = useRelationshipManagerDashboard(isRm)
  const crumbs = useBreadcrumbs()

  useEffect(() => { setMobileOpen(false); setProfileOpen(false) }, [location.pathname])
  useEffect(() => {
    const media = window.matchMedia('(max-width: 860px)')
    const update = () => setMobileViewport(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (!mobileModal) return
    const main = mainRef.current
    const skipLink = skipLinkRef.current
    const previousMainAriaHidden = main?.getAttribute('aria-hidden')
    const previousMainInert = main?.inert ?? false
    const previousSkipAriaHidden = skipLink?.getAttribute('aria-hidden')
    const previousSkipInert = skipLink?.inert ?? false
    if (main) {
      main.inert = true
      main.setAttribute('aria-hidden', 'true')
    }
    if (skipLink) {
      skipLink.inert = true
      skipLink.setAttribute('aria-hidden', 'true')
    }
    return () => {
      if (main) {
        main.inert = previousMainInert
        if (previousMainAriaHidden == null) main.removeAttribute('aria-hidden')
        else main.setAttribute('aria-hidden', previousMainAriaHidden)
      }
      if (skipLink) {
        skipLink.inert = previousSkipInert
        if (previousSkipAriaHidden == null) skipLink.removeAttribute('aria-hidden')
        else skipLink.setAttribute('aria-hidden', previousSkipAriaHidden)
      }
      menuButtonRef.current?.focus()
    }
  }, [mobileModal])
  useEffect(() => {
    if (!profileOpen) return
    const onClick = (event: MouseEvent) => { if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [profileOpen])

  const roleLabel = isBranchManager ? 'Responsable d’agence' : isRm ? 'Chargé de clientèle PME' : auth.hasRole('ML_STEWARD') ? 'Responsable modèles · Digital Factory' : auth.hasRole('ADMIN') || auth.hasRole('BUSINESS_ANALYST') ? 'Digital Factory · Back office' : auth.hasRole('RULE_APPROVER') ? 'Approbation des règles' : canBackOffice ? 'Analyse de données' : auth.roles[0]?.replaceAll('_', ' ') || auth.username
  const priorities = dashboard.data?.kpis.highPriorityCustomers
  const actionsDue = dashboard.data?.kpis.actionsDue

  const navigation = useMemo(() => {
    const items: Array<{ to: string; label: string; icon: typeof LayoutDashboard; end?: boolean; count?: number; section?: string }> = []
    if (isRm) {
      items.push({ to: '/', label: 'Mon portefeuille', icon: LayoutDashboard, end: true, count: priorities, section: 'Portefeuille PME' })
      items.push({ to: '/clients', label: 'Mes PME', icon: Building2 })
      items.push({ to: '/actions', label: 'Mes actions', icon: ClipboardCheck, count: actionsDue })
    } else if (isBranchManager) {
      items.push({ to: '/', label: 'Pilotage agence', icon: LayoutDashboard, end: true, section: 'Agence' })
      items.push({ to: '/clients', label: 'PME de l’agence', icon: Building2 })
      items.push({ to: '/actions', label: 'Actions & résultats', icon: ClipboardCheck })
    } else {
      items.push({ to: '/', label: 'Vue d’ensemble', icon: LayoutDashboard, end: true, section: 'Intelligence commerciale' })
      items.push({ to: '/opportunites', label: 'Opportunités', icon: BriefcaseBusiness })
      items.push({ to: '/clients', label: 'Clients PME', icon: Building2 })
      items.push({ to: '/signaux', label: 'Signaux', icon: Activity })
      items.push({ to: '/actions', label: 'Actions', icon: ClipboardCheck })
      items.push({ to: '/produits', label: 'Catalogue', icon: PackageSearch })
    }
    if (canBackOffice) {
      items.push({ to: '/back-office', label: 'Back office métier', icon: Database, end: true, section: 'Gouvernance' })
      items.push({ to: '/back-office/regles', label: 'Rule Studio', icon: GitBranch })
      if (canMlStudio) items.push({ to: '/back-office/studio-ml', label: 'Studio ML', icon: Cpu })
      items.push({ to: '/back-office/simulations', label: 'Simulations', icon: FlaskConical })
      items.push({ to: '/back-office/modeles', label: 'ML Governance', icon: Cpu })
      items.push({ to: '/back-office/audit', label: 'Audit', icon: ShieldCheck })
    }
    return items
  }, [isRm, isBranchManager, canBackOffice, canMlStudio, priorities, actionsDue])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    if (!search.trim()) return
    navigate(`/clients?q=${encodeURIComponent(search.trim())}`)
  }

  return <div className="app">
    <a ref={skipLinkRef} className="skip-link" href="#main">Aller au contenu principal</a>
    {mobileOpen && <div className="sidebar-scrim" aria-hidden="true" onClick={() => setMobileOpen(false)} />}
    <aside ref={sidebarRef} id="primary-navigation" className={`sidebar ${mobileOpen ? 'open' : ''}`} role={mobileViewport ? 'dialog' : undefined} aria-modal={mobileViewport && mobileOpen ? true : undefined} aria-label={mobileViewport ? 'Menu principal' : undefined} inert={mobileViewport && !mobileOpen ? true : undefined}>
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">BOA</span>
        <div><strong>BANK OF AFRICA</strong><small>SME Opportunity Intelligence</small></div>
        <button type="button" className="btn icon sm mobile-close" onClick={() => setMobileOpen(false)} aria-label="Fermer" style={{ marginLeft: 'auto', color: '#fff' }}><X size={16} /></button>
      </div>
      <nav aria-label="Navigation principale">
        {navigation.map((item, index) => <div key={item.to}>
          {item.section && (index === 0 || navigation[index - 1]?.section !== item.section) && <div className="sidebar-section">{item.section}</div>}
          <div className="nav"><NavLink to={item.to} end={item.end}><item.icon size={18} /><span>{item.label}</span>{item.count != null && item.count > 0 && <span className="count">{item.count}</span>}</NavLink></div>
        </div>)}
      </nav>
      <div className="sidebar-footer">
        <div className="env-badge"><ShieldCheck size={16} /><div>Environnement de démonstration<span>Données synthétiques · aucune décision de crédit</span></div></div>
      </div>
    </aside>

    <div ref={mainRef} className="main">
      <header className="topbar">
        <button ref={menuButtonRef} type="button" className="btn icon menu-btn" onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu" aria-controls="primary-navigation" aria-expanded={mobileOpen}><Menu size={18} /></button>
        <nav className="crumbs" aria-label="Fil d’Ariane">
          {crumbs.map((crumb, index) => <span key={`${crumb.label}-${index}`} className="row" style={{ gap: 6 }}>
            {index > 0 && <ChevronRight size={14} />}
            {crumb.to && index < crumbs.length - 1 ? <Link to={crumb.to}>{crumb.label}</Link> : <strong>{crumb.label}</strong>}
          </span>)}
        </nav>
        <div className="topbar-spacer" />
        <form className="search global-search" onSubmit={submitSearch} role="search"><Search size={16} /><input className="input sm" placeholder="Rechercher une PME (nom, identifiant)…" aria-label="Rechercher une PME" value={search} onChange={(event) => setSearch(event.target.value)} /></form>
        {auth.devMode && <DemoLauncher />}
        <div className="profile" ref={profileRef}>
          <button type="button" className="profile-btn" onClick={() => setProfileOpen((open) => !open)} aria-expanded={profileOpen} aria-haspopup="menu">
            <span className="avatar">{initials(auth.displayName)}</span>
            <span><strong>{auth.displayName}</strong><small>{roleLabel}</small></span>
            <ChevronDown size={14} />
          </button>
          {profileOpen && <div className="profile-menu" role="menu">
            <div className="menu-head"><strong>{auth.displayName}</strong><span>{auth.username} · {auth.roles.map((role) => role.replaceAll('_', ' ').toLowerCase()).join(', ')}</span></div>
            {auth.devMode && <>
              <div className="menu-label">Persona de démonstration</div>
              {auth.personas.map((persona) => <button type="button" role="menuitem" key={persona.id} className={auth.persona?.id === persona.id ? 'active' : ''} onClick={() => { auth.selectPersona(persona.id); navigate('/') }}><UserRound size={15} />{persona.label}<small className="muted" style={{ marginLeft: 'auto' }}>{persona.roles[0]?.replaceAll('_', ' ').toLowerCase()}</small></button>)}
            </>}
            <button type="button" role="menuitem" onClick={() => void auth.logout()}><LogOut size={15} /> Se déconnecter</button>
          </div>}
        </div>
      </header>
      <main className="content" id="main" tabIndex={-1}><Outlet /></main>
    </div>
  </div>
}
