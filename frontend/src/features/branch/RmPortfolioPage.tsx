import { ArrowLeft, Building2, Flame, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatNumber, formatPercent } from '../../api/format'
import { useRelationshipManagerPortfolio } from '../../api/hooks'
import { ErrorState, Kpi, NoResults, Panel, Segmented, SkeletonStack } from '../../ui'
import { PriorityStack, selectCustomers } from '../dashboard/CcDashboardPage'
import { ExportButton } from '../export/ExportButton'
import { PriorityRow } from '../dashboard/PriorityRow'

/** Drill-down responsable d'agence : Agence → CC → portefeuille → PME → opportunité. */
export function RmPortfolioPage() {
  const { relationshipManagerId = '' } = useParams()
  const portfolio = useRelationshipManagerPortfolio(relationshipManagerId)
  const [filter, setFilter] = useState<'all' | 'P1' | 'P2' | 'opportunities'>('all')
  const [query, setQuery] = useState('')
  const rows = useMemo(() => (portfolio.data ? selectCustomers(portfolio.data, filter, query, 'priority') : []), [portfolio.data, filter, query])
  if (portfolio.isPending) return <SkeletonStack rows={5} />
  if (portfolio.isError || !portfolio.data) return <ErrorState error={portfolio.error} onRetry={() => void portfolio.refetch()} />
  const data = portfolio.data
  return <>
    <Link to="/" className="btn ghost sm" style={{ justifySelf: 'start' }}><ArrowLeft size={14} /> Pilotage agence</Link>
    <header className="page-head"><div><p className="eyebrow accent">Portefeuille d’un chargé de clientèle</p><h1>{data.scope.relationshipManagerName || relationshipManagerId}</h1><p className="subtitle">Agence {data.scope.branchName} · {formatNumber(data.kpis.portfolioCustomers)} PME affectées · lecture responsable d’agence, périmètre contrôlé par le Gateway.</p></div><div className="page-actions"><ExportButton path={`/api/v1/exports/portfolio.xlsx?relationshipManagerId=${encodeURIComponent(relationshipManagerId)}`} /></div></header>
    <section className="grid cols-4">
      <Kpi label="PME affectées" value={data.kpis.portfolioCustomers} tone="navy" icon={<Building2 size={20} />} onClick={() => setFilter('all')} active={filter === 'all'} />
      <Kpi label="Priorités P1" value={data.kpis.highPriorityCustomers} tone="red" icon={<Flame size={20} />} note={formatPercent(data.kpis.portfolioCustomers ? data.kpis.highPriorityCustomers / data.kpis.portfolioCustomers : 0)} onClick={() => setFilter('P1')} active={filter === 'P1'} />
      <Kpi label="Opportunités" value={data.kpis.openOpportunities} tone="blue" onClick={() => setFilter('opportunities')} active={filter === 'opportunities'} />
      <Kpi label="Conversions" value={data.kpis.convertedOpportunities ?? 0} tone="green" note={`taux ${formatPercent(data.kpis.conversionRate, 0)}`} />
    </section>
    <div className="dashboard-columns">
      <Panel flush id="rm-portfolio">
        <header className="panel-head list-head"><div><p className="eyebrow">Portefeuille</p><h2>{formatNumber(rows.length)} PME</h2></div><div className="panel-tools"><div className="search"><Search size={14} /><input className="input sm" placeholder="Filtrer…" aria-label="Filtrer" value={query} onChange={(event) => setQuery(event.target.value)} /></div></div></header>
        <div className="list-filters"><Segmented value={filter} onChange={setFilter} options={[{ value: 'all', label: 'Toutes' }, { value: 'P1', label: 'P1' }, { value: 'P2', label: 'P2' }, { value: 'opportunities', label: 'Avec opportunité' }]} /></div>
        {!rows.length ? <NoResults /> : <div className="priority-list">{rows.map((customer, index) => <PriorityRow customer={customer} index={index} linkSuffix={`?cc=${encodeURIComponent(relationshipManagerId)}`} key={customer.customerId} />)}</div>}
      </Panel>
      <aside className="stack"><Panel eyebrow="Ordre de traitement" title="Priorités du portefeuille" id="rm-dist"><PriorityStack items={data.priorityDistribution} /></Panel></aside>
    </div>
  </>
}
