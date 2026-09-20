import { BriefcaseBusiness, Building2, CalendarCheck2, Flame, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { formatNumber, formatPercent, label } from '../../api/format'
import { useRelationshipManagerDashboard } from '../../api/hooks'
import type { PortfolioCustomerSummary, RelationshipManagerDashboard } from '../../api/types'
import { ExportButton } from '../export/ExportButton'
import { EmptyState, ErrorState, Kpi, NoResults, Panel, Segmented, SkeletonStack } from '../../ui'
import { PriorityRow } from './PriorityRow'

type Filter = 'today' | 'all' | 'P1' | 'P2' | 'opportunities' | 'actions'
type Sort = 'priority' | 'name'

const greeting = () => {
  const hour = new Date().getHours()
  return hour < 12 ? 'Bonjour' : hour < 18 ? 'Bon après-midi' : 'Bonsoir'
}

export function selectCustomers(data: RelationshipManagerDashboard, filter: Filter, query: string, sort: Sort) {
  const text = query.trim().toLowerCase()
  const rows = data.portfolio.filter((customer) => {
    if (text && !`${customer.customerName} ${customer.customerId} ${customer.industry}`.toLowerCase().includes(text)) return false
    switch (filter) {
      case 'today': return customer.priorityLevel === 'P1' || customer.nextActions.length > 0
      case 'P1': return customer.priorityLevel === 'P1'
      case 'P2': return customer.priorityLevel === 'P2'
      case 'opportunities': return customer.openOpportunities.length > 0
      case 'actions': return customer.nextActions.length > 0
      default: return true
    }
  })
  const by: Record<Sort, (a: PortfolioCustomerSummary, b: PortfolioCustomerSummary) => number> = {
    priority: (a, b) => (b.combinedPriorityScore ?? 0) - (a.combinedPriorityScore ?? 0) || a.customerId.localeCompare(b.customerId),
    name: (a, b) => a.customerName.localeCompare(b.customerName, 'fr'),
  }
  return [...rows].sort(by[sort])
}

export function CcDashboardPage() {
  const dashboard = useRelationshipManagerDashboard()
  const [filter, setFilter] = useState<Filter>('today')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>('priority')
  const data = dashboard.data
  const rows = useMemo(() => (data ? selectCustomers(data, filter, query, sort) : []), [data, filter, query, sort])

  if (dashboard.isPending) return <div className="stack" aria-busy="true"><div className="grid cols-4"><div className="skeleton block" /><div className="skeleton block" /><div className="skeleton block" /><div className="skeleton block" /></div><SkeletonStack rows={5} /></div>
  if (dashboard.isError || !data) return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />

  const { kpis, scope } = data
  const withSignal = data.portfolio.filter((customer) => customer.openOpportunities.length > 0).length
  const todayCount = data.portfolio.filter((customer) => customer.priorityLevel === 'P1' || customer.nextActions.length > 0).length

  return <>
    <header className="page-head">
      <div>
        <p className="eyebrow accent">Mon portefeuille PME</p>
        <h1>{greeting()} {scope.relationshipManagerName?.split(' ')[0] || ''}</h1>
        <p className="subtitle">Agence {scope.branchName || scope.branchId} · Votre portefeuille PME — <strong>{formatNumber(kpis.portfolioCustomers)} clients</strong>, dont <strong>{formatNumber(withSignal)}</strong> présentent au moins un signal commercial.</p>
      </div>
      <div className="page-actions"><ExportButton path="/api/v1/exports/portfolio.xlsx" /><span className="badge outline"><span className="dot live" /> Données Gateway · {new Date(data.generatedAt || Date.now()).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span></div>
    </header>

    <section className="grid cols-4" aria-label="Indicateurs clés" data-demo="kpis">
      <Kpi label="Clients PME" value={kpis.portfolioCustomers} tone="navy" icon={<Building2 size={20} />} note="Périmètre affecté, contrôlé par le Gateway" onClick={() => setFilter('all')} active={filter === 'all'} />
      <Kpi label="Opportunités" value={kpis.openOpportunities} tone="blue" icon={<BriefcaseBusiness size={20} />} note={<>{formatNumber(withSignal)} PME concernées</>} onClick={() => setFilter('opportunities')} active={filter === 'opportunities'} />
      <Kpi label="Priorités du jour" value={kpis.highPriorityCustomers} tone="red" icon={<Flame size={20} />} note={<>{formatPercent(kpis.portfolioCustomers ? kpis.highPriorityCustomers / kpis.portfolioCustomers : 0)} du portefeuille en P1</>} onClick={() => setFilter('P1')} active={filter === 'P1'} />
      <Kpi label="Actions à traiter" value={kpis.actionsDue} tone="amber" icon={<CalendarCheck2 size={20} />} note={kpis.actionsDue ? 'Échéance sous 7 jours' : 'Aucune échéance proche'} onClick={() => setFilter('actions')} active={filter === 'actions'} />
    </section>

    <div className="dashboard-columns">
      <Panel className="priorities-panel" flush data-demo="priorities" id="priorities">
        <header className="panel-head list-head">
          <div><p className="eyebrow">À regarder aujourd’hui</p><h2>{filter === 'today' ? `${formatNumber(todayCount)} PME à examiner` : `${formatNumber(rows.length)} PME`}</h2></div>
          <div className="panel-tools">
            <div className="search"><Search size={14} /><input className="input sm" placeholder="Filtrer la liste…" aria-label="Filtrer la liste" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
            <select className="select sm" aria-label="Trier" value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="priority">Priorité règles</option><option value="name">Nom</option></select>
          </div>
        </header>
        <div className="list-filters">
          <Segmented ariaLabel="Filtre de priorité" value={filter} onChange={setFilter} options={[{ value: 'today', label: `Aujourd’hui · ${todayCount}` }, { value: 'P1', label: `P1 · ${kpis.highPriorityCustomers}` }, { value: 'P2', label: 'P2' }, { value: 'opportunities', label: 'Avec opportunité' }, { value: 'actions', label: 'Actions dues' }, { value: 'all', label: `Toutes · ${kpis.portfolioCustomers}` }]} />
        </div>
        {!data.portfolio.length ? <EmptyState title="Aucune PME affectée" message="Votre portefeuille ne contient aucune PME active pour le moment." /> : !rows.length ? <NoResults /> : <div className="priority-list">{rows.map((customer, index) => <PriorityRow customer={customer} index={index} key={customer.customerId} />)}</div>}
      </Panel>

      <aside className="stack">
        <Panel eyebrow="Ordre de traitement" title="Distribution des priorités" id="distribution">
          <PriorityStack items={data.priorityDistribution} onSelect={(level) => setFilter(level as Filter)} />
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>Priorité = règles métier publiées uniquement. La propension ML est observée en shadow, hors classement et sans notation de risque.</p>
        </Panel>
        <Panel eyebrow="Repères" title="Comment lire cette vue" id="help">
          <ul className="help-list">
            <li><Sparkles size={15} /> <span><strong>Signaux chiffrés</strong> issus des flux réels des 90 derniers jours, comparés à l’historique.</span></li>
            <li><ShieldCheck size={15} /> <span><strong>Règle métier déclenchée</strong> et version du moteur consultables sur chaque opportunité.</span></li>
            <li><Flame size={15} /> <span><strong>Propension shadow</strong> : observation expérimentale affichée séparément, sans effet sur l’ordre des contacts.</span></li>
          </ul>
        </Panel>
      </aside>
    </div>
  </>
}

export function PriorityStack({ items, onSelect }: { items: Array<{ priorityLevel: string; count: number; share?: number }>; onSelect?: (level: string) => void }) {
  const total = items.reduce((sum, item) => sum + item.count, 0)
  return <div className="priority-stack">
    <div className="priority-stack-bar" aria-hidden="true">{items.map((item) => item.count > 0 && <i key={item.priorityLevel} data-level={item.priorityLevel} style={{ width: `${(item.count / Math.max(total, 1)) * 100}%` }} />)}</div>
    <ul>
      {items.map((item) => <li key={item.priorityLevel}><button type="button" onClick={onSelect ? () => onSelect(item.priorityLevel) : undefined} disabled={!onSelect || !['P1', 'P2'].includes(item.priorityLevel)}><i data-level={item.priorityLevel} /><span>{label(item.priorityLevel)}</span><b className="num">{formatNumber(item.count)}</b><small className="num">{formatPercent(item.share ?? (total ? item.count / total : 0))}</small></button></li>)}
    </ul>
  </div>
}
