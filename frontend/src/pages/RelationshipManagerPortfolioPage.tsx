import { ArrowLeft, ArrowRight, Building2, Gauge } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { formatNumber, formatPercent, label } from '../api/format'
import { useRelationshipManagerPortfolio } from '../api/hooks'
import { Badge, EmptyState, ErrorState, PageHeader, SkeletonRows } from '../components/UI'

export function RelationshipManagerPortfolioPage() {
  const { relationshipManagerId } = useParams()
  const [searchParams] = useSearchParams()
  const managerName = searchParams.get('name') || relationshipManagerId || 'Chargé de clientèle'
  const dashboard = useRelationshipManagerPortfolio(relationshipManagerId)

  return <div className="page">
    <Link className="back-link" to="/"><ArrowLeft size={16} /> Retour au pilotage agence</Link>
    <PageHeader
      eyebrow="PORTEFEUILLE D’UN CC"
      title={dashboard.data?.scope.relationshipManagerName || managerName}
      description="Consultation, par le responsable d’agence, des seules PME affectées à ce chargé de clientèle dans son agence."
    />
    {dashboard.isPending ? <SkeletonRows /> : dashboard.isError || !dashboard.data ? <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} /> : <>
      <section className="kpi-grid" aria-label="Indicateurs du portefeuille CC">
        <article className="kpi-card"><span className="kpi-icon navy"><Building2 /></span><div><span>PME affectées</span><strong>{formatNumber(dashboard.data.kpis.portfolioCustomers)}</strong><small>Périmètre strict du CC</small></div></article>
        <article className="kpi-card"><span className="kpi-icon green"><Gauge /></span><div><span>Priorité P1</span><strong>{formatNumber(dashboard.data.kpis.highPriorityCustomers)}</strong><small>Ordre commercial ML + règles</small></div></article>
      </section>
      {!dashboard.data.portfolio.length ? <EmptyState title="Aucune PME affectée" message="Aucun client n’est retourné pour ce chargé de clientèle dans le périmètre de l’agence." /> : <div className="customer-grid">{dashboard.data.portfolio.map((customer) => <article className="customer-card" key={customer.customerId}>
        <div className="company-icon" aria-hidden="true"><Building2 /></div>
        <div>
          <small>{customer.customerId}</small>
          <h2>{customer.customerName}</h2>
          <p>{label(customer.industry)} · propension {customer.propensityScore.toFixed(2)}</p>
          <div className="customer-card-meta"><Badge value={customer.priorityLevel} /><span>{formatNumber(customer.openOpportunities.length)} opportunité(s) · {formatPercent(customer.propensityScore)}</span></div>
        </div>
        <Link className="button secondary" to={`/clients/${customer.customerId}`}>Fiche PME <ArrowRight size={16} /></Link>
      </article>)}</div>}
      <div className="credit-warning" role="note"><Gauge aria-hidden="true" /><div><strong>Pilotage commercial uniquement</strong><span>Cette priorisation ne constitue aucune décision de crédit.</span></div></div>
    </>}
  </div>
}
