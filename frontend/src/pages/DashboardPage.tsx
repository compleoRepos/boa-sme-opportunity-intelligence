import {
  ArrowRight,
  BriefcaseBusiness,
  Building2,
  CalendarCheck2,
  CheckCircle2,
  Gauge,
  Target,
  TrendingUp,
  UserRound,
  UsersRound,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useBranchDashboard, useRelationshipManagerDashboard } from '../api/hooks'
import { formatDate, formatNumber, formatPercent, label } from '../api/format'
import type {
  CommercialDashboardKpis,
  DashboardNextAction,
  PortfolioCustomerSummary,
  PriorityDistributionItem,
} from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { Badge, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UI'

const clampScore = (score: number) => Math.min(1, Math.max(0, score))

function KpiGrid({ kpis, manager = false }: { kpis: CommercialDashboardKpis; manager?: boolean }) {
  const items = manager
    ? [
        { label: 'Clients PME agence', value: formatNumber(kpis.portfolioCustomers), note: 'Périmètre consolidé', icon: UsersRound, tone: 'navy' },
        { label: 'Clients priorité P1', value: formatNumber(kpis.highPriorityCustomers), note: 'À piloter en premier', icon: Target, tone: 'green' },
        { label: 'Opportunités ouvertes', value: formatNumber(kpis.openOpportunities), note: 'Tous CC de l’agence', icon: BriefcaseBusiness, tone: 'gold' },
        { label: 'Taux de conversion', value: formatPercent(kpis.conversionRate, 1), note: `${formatNumber(kpis.convertedOpportunities)} opportunités converties`, icon: TrendingUp, tone: 'blue' },
      ]
    : [
        { label: 'PME dans mon portefeuille', value: formatNumber(kpis.portfolioCustomers), note: 'Périmètre exclusivement affecté', icon: Building2, tone: 'navy' },
        { label: 'Clients priorité P1', value: formatNumber(kpis.highPriorityCustomers), note: 'À engager en premier', icon: Target, tone: 'green' },
        { label: 'Opportunités ouvertes', value: formatNumber(kpis.openOpportunities), note: 'À qualifier commercialement', icon: BriefcaseBusiness, tone: 'gold' },
        { label: 'Actions à réaliser', value: formatNumber(kpis.actionsDue), note: 'Échéance atteinte ou proche', icon: CalendarCheck2, tone: 'blue' },
      ]
  return <section className="kpi-grid" aria-label="Indicateurs clés">
    {items.map(({ label: itemLabel, value, note, icon: Icon, tone }) => <article className="kpi-card" key={itemLabel}>
      <span className={`kpi-icon ${tone}`} aria-hidden="true"><Icon /></span>
      <div><span>{itemLabel}</span><strong>{value}</strong><small>{note}</small></div>
    </article>)}
  </section>
}

function PropensityScore({ value }: { value: number }) {
  const score = clampScore(value)
  const percent = Math.round(score * 100)
  return <div className="propensity-inline" aria-label={`Propension commerciale ${percent} pour cent`}>
    <div><span>Propension</span><strong>{score.toFixed(2)}</strong></div>
    <div className="propensity-track" aria-hidden="true"><i style={{ width: `${percent}%` }} /></div>
  </div>
}

function ActionPreview({ action }: { action: DashboardNextAction }) {
  return <li>
    <CalendarCheck2 size={15} aria-hidden="true" />
    <span><strong>{label(action.actionType)}</strong>{action.dueAt && <small>Échéance {formatDate(action.dueAt, true)}</small>}</span>
  </li>
}

function PortfolioCustomerCard({ customer }: { customer: PortfolioCustomerSummary }) {
  const firstOpportunity = customer.openOpportunities[0]
  return <article className="portfolio-priority-card" data-priority={customer.priorityLevel}>
    <header>
      <div><span className="customer-id">{customer.customerId}</span><h3>{customer.customerName}</h3><p>{label(customer.industry)}</p></div>
      <Badge value={customer.priorityLevel} />
    </header>
    <PropensityScore value={customer.propensityScore} />
    {customer.priorityReason && <p className="priority-reason">{customer.priorityReason}</p>}
    <div className="portfolio-card-columns">
      <div>
        <span className="field-label">Opportunités</span>
        <strong>{formatNumber(customer.openOpportunities.length)} ouverte{customer.openOpportunities.length > 1 ? 's' : ''}</strong>
        {firstOpportunity && <small>{label(firstOpportunity.opportunityType)} · confiance {formatPercent(firstOpportunity.confidence)}</small>}
      </div>
      <div>
        <span className="field-label">Prochaine action</span>
        {customer.nextActions.length ? <ul className="next-action-list">{customer.nextActions.slice(0, 1).map((action, index) => <ActionPreview action={action} key={action.actionId || `${action.actionType}-${index}`} />)}</ul> : <small>Aucune action planifiée</small>}
      </div>
    </div>
    <footer>
      <Link className="button secondary" to={`/clients/${customer.customerId}`}>Ouvrir la fiche PME <ArrowRight size={16} /></Link>
      {firstOpportunity && <Link className="button primary" to={`/opportunites/${firstOpportunity.opportunityId}`}>Traiter l’opportunité <ArrowRight size={16} /></Link>}
    </footer>
  </article>
}

function PriorityDistribution({ items }: { items: PriorityDistributionItem[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0)
  return <div className="priority-distribution" aria-label="Distribution des priorités clients">
    {items.map((item) => {
      const share = item.share ?? (total ? item.count / total : 0)
      return <div className="priority-row" key={item.priorityLevel}>
        <Badge value={item.priorityLevel} />
        <div className="priority-bar" aria-hidden="true"><i data-priority={item.priorityLevel} style={{ width: `${Math.min(100, share * 100)}%` }} /></div>
        <strong>{formatNumber(item.count)}</strong><span>{formatPercent(share)}</span>
      </div>
    })}
  </div>
}

export function RelationshipManagerDashboard() {
  const dashboard = useRelationshipManagerDashboard()
  if (dashboard.isPending) return <div className="page"><LoadingState label="Chargement de votre portefeuille PME…" /></div>
  if (dashboard.isError || !dashboard.data) return <div className="page"><PageHeader eyebrow="MON PORTEFEUILLE PME" title="Mes priorités commerciales" description="Cette vue affiche uniquement les PME affectées à votre portefeuille." /><ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} /></div>
  const data = dashboard.data
  return <div className="page dashboard-page">
    <PageHeader
      eyebrow="MON PORTEFEUILLE PME"
      title={`Bonjour${data.scope.relationshipManagerName ? ` ${data.scope.relationshipManagerName}` : ''}, voici vos priorités`}
      description="Cette vue est strictement limitée à vos PME affectées. La propension organise le travail commercial ; elle ne constitue ni un score de risque ni une décision de crédit."
      actions={<Link className="button secondary" to="/actions">Voir toutes mes actions <ArrowRight size={16} /></Link>}
    />
    <div className="scope-banner" role="note"><UserRound aria-hidden="true" /><div><strong>Périmètre personnel sécurisé</strong><span>{formatNumber(data.kpis.portfolioCustomers)} PME affectées à {data.scope.relationshipManagerName || 'votre identifiant'}{data.scope.branchName ? ` · ${data.scope.branchName}` : ''}</span></div></div>
    <KpiGrid kpis={data.kpis} />
    <section className="dashboard-grid">
      <div className="panel">
        <header className="panel-header"><div><p className="eyebrow">ORDRE DE TRAITEMENT</p><h2>Distribution des priorités clients</h2></div><span>Priorité commerciale, pas risque de crédit</span></header>
        {data.priorityDistribution.length ? <PriorityDistribution items={data.priorityDistribution} /> : <EmptyState title="Aucune priorité calculée" />}
      </div>
      <aside className="panel principles-panel"><p className="eyebrow">REPÈRES</p><h2>Un score pour agir</h2><p>Le score de propension, compris entre 0 et 1, estime l’intérêt commercial potentiel à partir du modèle et des règles métier.</p><ul><li><CheckCircle2 /> Prioriser les contacts</li><li><CheckCircle2 /> Examiner les facteurs explicatifs</li><li><CheckCircle2 /> Conserver le jugement du CC</li></ul></aside>
    </section>
    <section className="section-block" aria-labelledby="my-portfolio-heading">
      <div className="section-heading"><div><p className="eyebrow">À TRAITER</p><h2 id="my-portfolio-heading">Mes PME par priorité</h2></div><span className="section-context">{formatNumber(data.portfolio.length)} client{data.portfolio.length > 1 ? 's' : ''} dans cette file</span></div>
      {!data.portfolio.length ? <EmptyState title="Aucune PME prioritaire" message="Votre portefeuille ne contient aucune recommandation à traiter pour le moment." /> : <div className="portfolio-priority-list">{data.portfolio.map((customer) => <PortfolioCustomerCard customer={customer} key={customer.customerId} />)}</div>}
    </section>
  </div>
}

export function BranchManagerDashboard() {
  const dashboard = useBranchDashboard()
  if (dashboard.isPending) return <div className="page"><LoadingState label="Consolidation des portefeuilles de l’agence…" /></div>
  if (dashboard.isError || !dashboard.data) return <div className="page"><PageHeader eyebrow="PILOTAGE AGENCE" title="Performance commerciale consolidée" /><ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} /></div>
  const data = dashboard.data
  return <div className="page dashboard-page">
    <PageHeader eyebrow="PILOTAGE AGENCE" title={data.scope.branchName || 'Performance commerciale consolidée'} description="Suivez les portefeuilles de vos chargés de clientèle, la pression commerciale et les conversions sur le périmètre de l’agence." />
    <KpiGrid kpis={data.kpis} manager />
    <section className="dashboard-grid branch-overview-grid">
      <div className="panel"><header className="panel-header"><div><p className="eyebrow">PRIORITÉS CLIENTS</p><h2>Distribution de l’agence</h2></div><span>{formatNumber(data.kpis.portfolioCustomers)} PME</span></header>{data.priorityDistribution.length ? <PriorityDistribution items={data.priorityDistribution} /> : <EmptyState title="Aucune priorité calculée" />}</div>
      <div className="panel"><header className="panel-header"><div><p className="eyebrow">CONVERSIONS</p><h2>Progression commerciale</h2></div></header>{data.conversionFunnel.length ? <div className="conversion-funnel">{data.conversionFunnel.map((stage) => <article key={stage.stage}><span>{label(stage.stage)}</span><strong>{formatNumber(stage.count)}</strong>{stage.rate != null && <small>{formatPercent(stage.rate, 1)} du point de départ</small>}<div aria-hidden="true"><i style={{ width: `${Math.min(100, (stage.rate ?? 0) * 100)}%` }} /></div></article>)}</div> : <EmptyState title="Aucune conversion disponible" />}</div>
    </section>
    <section className="section-block" aria-labelledby="rm-performance-heading">
      <div className="section-heading"><div><p className="eyebrow">ÉQUIPE COMMERCIALE</p><h2 id="rm-performance-heading">KPIs par chargé de clientèle</h2></div><span className="section-context">{formatNumber(data.relationshipManagers.length)} CC consolidés</span></div>
      {!data.relationshipManagers.length ? <EmptyState title="Aucun portefeuille CC" /> : <div className="panel rm-table-panel"><div className="table-wrap"><table className="rm-performance-table"><thead><tr><th>Chargé de clientèle</th><th>Portefeuille</th><th>Priorité P1</th><th>Opportunités</th><th>Actions dues</th><th>Conversions</th><th>Taux</th><th><span className="sr-only">Accès</span></th></tr></thead><tbody>{data.relationshipManagers.map((manager) => <tr key={manager.relationshipManagerId}><td><strong>{manager.relationshipManagerName}</strong><small>{manager.relationshipManagerId}</small></td><td>{formatNumber(manager.portfolioCustomers)}</td><td>{formatNumber(manager.highPriorityCustomers)}</td><td>{formatNumber(manager.openOpportunities)}</td><td>{formatNumber(manager.actionsDue)}</td><td>{formatNumber(manager.convertedOpportunities)}</td><td><strong>{formatPercent(manager.conversionRate, 1)}</strong></td><td><Link className="button secondary" to={`/portefeuilles/${encodeURIComponent(manager.relationshipManagerId)}?name=${encodeURIComponent(manager.relationshipManagerName)}`} aria-label={`Accéder au portefeuille de ${manager.relationshipManagerName}`}>Portefeuille <ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div></div>}
    </section>
    <div className="credit-warning" role="note"><Gauge aria-hidden="true" /><div><strong>Pilotage commercial uniquement</strong><span>Les priorités et conversions ne déclenchent aucune décision de crédit et ne remplacent pas l’analyse humaine.</span></div></div>
  </div>
}

export function DashboardPage() {
  const { hasRole } = useAuth()
  if (hasRole('BRANCH_MANAGER')) return <BranchManagerDashboard />
  return <RelationshipManagerDashboard />
}
