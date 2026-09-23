import { useState } from 'react'
import { Activity, Building2, CalendarDays, Eye, Radar } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { formatNumber, formatPercent, label } from '../../api/format'
import { useFiPortfolioCatalog, useFiPortfolioSummary } from '../../api/financialIntelligence.hooks'
import { EmptyState, ErrorState, Kpi, Panel, SkeletonStack } from '../../ui'
import { FiGovernance, FiMeta, FiPartialWarning, FiSourceStatuses, FiValue } from './FinancialIntelligenceCommon'

function BlockedIndicator({ title, message }: { title: string; message: string }) {
  return <div className="state error fi-blocked" role="status"><strong>NOT IMPLEMENTED — BLOCKED</strong><span><b>{title}.</b> {message} Aucune valeur n’est calculée dans React.</span></div>
}

export function PortfolioIntelligencePage() {
  const { portfolioId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const asOf = searchParams.get('asOf') || undefined
  const [selectedAsOf, setSelectedAsOf] = useState('')
  const catalog = useFiPortfolioCatalog(asOf)
  const summary = useFiPortfolioSummary(portfolioId, asOf)

  if (!asOf) return <div className="stack fi-page">
    <header className="page-head"><div><p className="eyebrow accent">Financial Intelligence</p><h1>Portfolio Intelligence overview</h1><p className="subtitle">Ouvrez un portefeuille autorisé avec un `portfolioId` et un `asOf` explicites.</p></div></header>
    <FiGovernance />
    <Panel id="fi-as-of-selection" eyebrow="Point-in-time" title="Choisir la date de référence">
      <p className="muted">La date n’est jamais choisie implicitement. Elle sera transmise au backend pour découvrir uniquement les portfolios autorisés.</p>
      <form className="row wrap" onSubmit={(event) => { event.preventDefault(); if (selectedAsOf) navigate(`/financial-intelligence/portfolios?asOf=${encodeURIComponent(selectedAsOf)}`) }}>
        <label className="field"><span>Date asOf</span><input type="date" required value={selectedAsOf} onChange={(event) => setSelectedAsOf(event.target.value)} /></label>
        <button className="btn primary" type="submit" disabled={!selectedAsOf}><CalendarDays size={16} />Afficher les portfolios autorisés</button>
      </form>
    </Panel>
  </div>
  if (!portfolioId) {
    if (catalog.isPending) return <div className="stack fi-page"><SkeletonStack rows={4} kind="block" /></div>
    if (catalog.isError) return <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} />
    if (!catalog.data) return <EmptyState title="Catalogue indisponible" message="Le backend n’a renvoyé aucune enveloppe de portfolios autorisés." />
    return <div className="stack fi-page">
      <header className="page-head"><div><p className="eyebrow accent">Financial Intelligence</p><h1>Portfolios autorisés</h1><p className="subtitle">Périmètre résolu côté backend pour asOf {catalog.data.meta.asOf}.</p></div></header>
      <FiGovernance meta={catalog.data.meta} />
      <FiPartialWarning meta={catalog.data.meta} />
      <Panel id="fi-portfolio-catalog" eyebrow="Autorisation explicite" title="Sélectionner un portfolio">
        {!catalog.data.data.portfolios.length ? <EmptyState compact title="Aucun portfolio" message="Aucun DataAccessGrant actif ne permet d’afficher un portfolio à cette identité." /> : <ul className="fi-source-list">{catalog.data.data.portfolios.map((portfolio) => <li key={portfolio.portfolioId}><Building2 size={18} aria-hidden="true" /><span><strong>{portfolio.name}</strong><small>{portfolio.portfolioId} · {portfolio.fundId} · {formatNumber(portfolio.companyCount)} PME</small></span><Link className="btn secondary sm" to={`/financial-intelligence/portfolios/${encodeURIComponent(portfolio.portfolioId)}?asOf=${encodeURIComponent(catalog.data.meta.asOf)}`}>Ouvrir</Link></li>)}</ul>}
      </Panel>
      <Panel id="fi-catalog-sources" eyebrow="Dépendances" title="État des sources"><FiSourceStatuses sources={catalog.data.meta.sourceStatus} /></Panel>
    </div>
  }
  if (summary.isPending) return <div className="stack fi-page"><SkeletonStack rows={5} kind="block" /></div>
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
  if (!summary.data) return <EmptyState title="Portfolio vide" message="Le backend n’a renvoyé aucune enveloppe Financial Intelligence." />

  const { data, meta } = summary.data
  return <div className="stack fi-page">
    <header className="page-head"><div><p className="eyebrow accent">Financial Intelligence · Portfolio</p><h1>{data.portfolioId}</h1><p className="subtitle">Fonds {data.fundId} · vue agrégée autorisée par le backend · asOf {meta.asOf}.</p></div></header>
    <FiGovernance meta={meta} />
    <FiPartialWarning meta={meta} />

    <section className="grid cols-4" aria-label="Indicateurs de portefeuille">
      <Kpi label="Sociétés" value={data.companyCount} icon={<Building2 size={18} />} note="Valeur backend" />
      <Kpi label="Sociétés avec signaux" value={data.companiesWithSignals} icon={<Activity size={18} />} tone="amber" note={`${data.signalCount} signaux au total`} />
      <Kpi label="Opportunités" value={data.opportunityCount} icon={<Radar size={18} />} tone="green" note="Références existantes uniquement" />
      <Kpi label="Périmètre multibancaire" value={data.companies.length} icon={<Eye size={18} />} tone="violet" note="Sociétés projetées par le backend" />
    </section>

    <section className="grid cols-2">
      <Panel id="fi-flow-aggregates" eyebrow="Flux" title="Agrégats de flux"><dl className="fi-metric-grid"><div><dt>Encaissements</dt><dd><FiValue value={data.totalInflows} currency="MAD" /></dd></div><div><dt>Décaissements</dt><dd><FiValue value={data.totalOutflows} currency="MAD" /></dd></div><div><dt>Flux net</dt><dd><FiValue value={data.totalNetFlow} currency="MAD" /></dd></div></dl></Panel>
      <Panel id="fi-flow-evolution" eyebrow="Point-in-time" title="Évolution des flux"><BlockedIndicator title="Évolution des flux" message="Le contrat fi.v1 ne renvoie pas de série temporelle de portefeuille." /></Panel>
    </section>
    <section className="grid cols-2">
      <Panel id="fi-companies-with-signals" eyebrow="Couverture signaux" title="Sociétés avec signaux"><dl className="fi-metric-grid"><div><dt>Sociétés concernées</dt><dd>{formatNumber(data.companiesWithSignals)}</dd></div><div><dt>Signaux exposés</dt><dd>{formatNumber(data.signalCount)}</dd></div></dl></Panel>
      <Panel id="fi-opportunity-distribution" eyebrow="Opportunités backend" title="Distribution des opportunités">{Object.keys(data.opportunityDistribution).length ? <ul className="fi-source-list">{Object.entries(data.opportunityDistribution).map(([type, count]) => <li key={type}><Radar size={15} aria-hidden="true" /><span><strong>{label(type)}</strong><small>Type calculé par l’Opportunity Engine existant</small></span><b>{formatNumber(count)}</b></li>)}</ul> : <EmptyState compact title="Aucune opportunité" message="Le backend n’a renvoyé aucune opportunité dans ce portefeuille." />}</Panel>
    </section>

    <Panel id="fi-companies" eyebrow="Périmètre autorisé" title="Sociétés et visibilité multibancaire">
      {!data.companies.length ? <EmptyState compact title="Aucune société" message="Le backend n’a renvoyé aucune société accessible." /> : <div className="table-wrap"><table className="table hover fi-table"><thead><tr><th>Société</th><th>Flux 90 j</th><th>Visibilité</th><th>Couverture</th><th>Accès</th></tr></thead><tbody>
        {data.companies.map((company) => <tr key={company.companyId}><td><strong>{company.legalName ?? company.companyId}</strong><small>{company.companyId} · {company.sector ?? 'secteur non fourni'}</small></td><td><FiValue value={company.flowSummary.netFlow} currency={company.flowSummary.currency} /><small>{company.flowSummary.period}</small></td><td>{label(company.visibility.level)}<small>{label(company.visibility.method)}</small></td><td>{formatPercent(company.visibility.categorizationCoverage, 1)}</td><td><Link className="btn secondary sm" to={`/financial-intelligence/companies/${encodeURIComponent(company.companyId)}?asOf=${encodeURIComponent(meta.asOf)}`}>Ouvrir</Link></td></tr>)}
      </tbody></table></div>}
    </Panel>

    <section className="grid cols-2">
      <Panel id="fi-provenance" eyebrow="Contrat" title="Provenance et horodatage"><FiMeta meta={meta} /></Panel>
      <Panel id="fi-sources" eyebrow="Dépendances" title="État des sources"><FiSourceStatuses sources={meta.sourceStatus} /></Panel>
    </section>
    <p className="muted fi-contract-note">Contrat {meta.contractVersion} · {formatNumber(data.companyCount)} sociétés · disclaimer backend {data.disclaimer}.</p>
  </div>
}
