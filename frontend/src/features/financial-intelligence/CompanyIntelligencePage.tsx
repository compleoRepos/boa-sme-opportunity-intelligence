import { Activity, Banknote, Eye, FileSearch, Radar } from 'lucide-react'
import { useParams, useSearchParams } from 'react-router-dom'
import { formatPercent, label } from '../../api/format'
import {
  useFiCompanyCashPosition,
  useFiCompanyFlowSummary,
  useFiCompanyOpportunities,
  useFiCompanySignals,
  useFiCompanySummary,
} from '../../api/financialIntelligence.hooks'
import type { FiCashPosition, FiEnvelope, FiFlowSummary, FiOpportunity, FiResponseMeta, FiSignal } from '../../api/financialIntelligence.types'
import { Badge, EmptyState, ErrorState, Panel, SkeletonStack } from '../../ui'
import { FiBlockedState, FiGovernance, FiMeta, FiMetricGrid, FiPartialWarning, FiSourceStatuses, FiValue } from './FinancialIntelligenceCommon'

interface QueryState<T> {
  data?: FiEnvelope<T>
  isPending: boolean
  isError: boolean
  error: unknown
  refetch: () => Promise<unknown>
}

function ResourceSection<T>({ query, emptyTitle, children }: { query: QueryState<T>; emptyTitle: string; children: (data: T, meta: FiResponseMeta) => React.ReactNode }) {
  if (query.isPending) return <SkeletonStack rows={3} kind="text" />
  if (query.isError) return <ErrorState compact error={query.error} onRetry={() => void query.refetch()} />
  if (!query.data) return <EmptyState compact title={emptyTitle} message="Le backend n’a renvoyé aucune enveloppe." />
  return <>{children(query.data.data, query.data.meta)}</>
}

function BlockedValue({ meta, capability }: { meta: FiResponseMeta; capability: string }) {
  return <FiBlockedState meta={meta} capabilities={[capability]} />
}

function SignalTable({ signals }: { signals: FiSignal[] }) {
  if (!signals.length) return <EmptyState compact title="Aucun signal" message="Le backend n’a renvoyé aucun signal pour ce point-in-time." />
  return <div className="table-wrap"><table className="table fi-table"><thead><tr><th>Signal</th><th>Sévérité</th><th className="text-right">Valeur</th><th className="text-right">Seuil</th><th>asOf</th></tr></thead><tbody>{signals.map((signal) => <tr key={signal.signalRef}><td><strong>{label(signal.type)}</strong><small>{signal.signalRef}{signal.ruleVersion ? ` · ${signal.ruleVersion}` : ''}</small></td><td><Badge value={signal.severity} /></td><td className="text-right"><FiValue value={signal.value} /></td><td className="text-right"><FiValue value={signal.threshold} /></td><td>{signal.asOf}</td></tr>)}</tbody></table></div>
}

function OpportunityList({ opportunities }: { opportunities: FiOpportunity[] }) {
  if (!opportunities.length) return <EmptyState compact title="Aucune opportunité" message="Aucune opportunité existante n’a été projetée par le backend." />
  return <ul className="fi-opportunity-list">{opportunities.map((opportunity) => <li key={opportunity.opportunityId}><span><strong>{label(opportunity.opportunityType)}</strong><small>{opportunity.opportunityId} · asOf {opportunity.asOf}{opportunity.ruleVersion ? ` · règle ${opportunity.ruleVersion}` : ''}{opportunity.scoringPolicyVersion != null ? ` · politique v${opportunity.scoringPolicyVersion}` : ''}</small></span><span className="row wrap"><Badge tone="outline">État historique non implémenté</Badge>{opportunity.priorityLevel && <Badge value={opportunity.priorityLevel} />}<span className="muted">Confiance {formatPercent(opportunity.confidence, 1)}</span></span></li>)}</ul>
}

function EvidenceReferences({ signals, opportunities }: { signals: FiSignal[]; opportunities: FiOpportunity[] }) {
  const references = [
    ...signals.flatMap((signal) => signal.evidenceRefs.map((reference) => ({ reference, owner: signal.signalRef, type: 'Signal' }))),
    ...opportunities.flatMap((opportunity) => opportunity.evidenceRefs.map((reference) => ({ reference, owner: opportunity.opportunityId, type: 'Opportunité' }))),
  ]
  if (!references.length) return <EmptyState compact title="Aucune evidence" message="Les endpoints backend n’ont renvoyé aucune référence de preuve." />
  return <ul className="fi-evidence-list">{references.map((item, index) => <li key={`${item.type}-${item.owner}-${item.reference}-${index}`}><FileSearch size={16} aria-hidden="true" /><span><strong>{item.reference}</strong><small>{item.type} · {item.owner}</small></span></li>)}</ul>
}

function CashPosition({ data, meta }: { data: FiCashPosition; meta: FiResponseMeta }) {
  return <div className="stack"><dl className="fi-metric-grid"><div><dt>Solde moyen</dt><dd><FiValue value={data.averageBalance} currency={data.currency} /></dd></div><div><dt>Solde minimum</dt><dd><FiValue value={data.minimumBalance} currency={data.currency} /></dd></div><div><dt>Solde maximum</dt><dd><FiValue value={data.maximumBalance} currency={data.currency} /></dd></div><div><dt>Tendance du solde</dt><dd><FiValue value={data.balanceTrend} unit="PERCENT" /></dd><small>{data.period}</small></div></dl><div className="grid cols-2"><BlockedValue meta={meta} capability="cash-concentration" /><BlockedValue meta={meta} capability="cash-volatility" /></div></div>
}

function FlowSummary({ data, meta }: { data: FiFlowSummary; meta: FiResponseMeta }) {
  return <div className="stack"><dl className="fi-metric-grid"><div><dt>Encaissements</dt><dd><FiValue value={data.inflows} currency={data.currency} /></dd><small>Tendance <FiValue value={data.inflowTrend} unit="PERCENT" /></small></div><div><dt>Décaissements</dt><dd><FiValue value={data.outflows} currency={data.currency} /></dd><small>Tendance <FiValue value={data.outflowTrend} unit="PERCENT" /></small></div><div><dt>Flux net</dt><dd><FiValue value={data.netFlow} currency={data.currency} /></dd><small>Ratio <FiValue value={data.netFlowRatio} unit="PERCENT" /></small></div><div><dt>Transactions</dt><dd><FiValue value={data.transactionCount} /></dd><small>Évolution <FiValue value={data.activityTrend} unit="PERCENT" /> · {data.period}</small></div></dl><div className="grid cols-2"><BlockedValue meta={meta} capability="flow-concentration" /><BlockedValue meta={meta} capability="flow-volatility" /></div><div className="state fi-blocked" role="status"><strong>NOT IMPLEMENTED — BLOCKED</strong><span>Le contrat fi.v1 renvoie des tendances agrégées, mais aucune série temporelle de flow evolution. Aucune série n’est reconstruite dans React.</span></div></div>
}

export function CompanyIntelligencePage() {
  const { companyId } = useParams()
  const [searchParams] = useSearchParams()
  const asOf = searchParams.get('asOf') || undefined
  const summary = useFiCompanySummary(companyId, asOf)
  const signals = useFiCompanySignals(companyId, asOf)
  const opportunities = useFiCompanyOpportunities(companyId, asOf)
  const cash = useFiCompanyCashPosition(companyId, asOf)
  const flows = useFiCompanyFlowSummary(companyId, asOf)

  if (!companyId || !asOf) return <div className="stack fi-page"><FiGovernance /><EmptyState title="Contexte point-in-time incomplet" message="L’URL société doit contenir un companyId et `?asOf=YYYY-MM-DD`. Aucune date par défaut n’est fabriquée." /></div>
  if (summary.isPending) return <div className="stack fi-page"><SkeletonStack rows={5} kind="block" /></div>
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
  if (!summary.data) return <EmptyState title="Société vide" message="Le backend n’a renvoyé aucune enveloppe de résumé société." />

  const { data, meta } = summary.data
  return <div className="stack fi-page">
    <header className="page-head"><div><p className="eyebrow accent">Financial Intelligence · Company</p><h1>{data.legalName ?? data.companyId}</h1><p className="subtitle">{data.companyId} · fonds {data.fundId} · portfolio {data.portfolioId} · asOf {meta.asOf}.</p></div><div className="page-actions"><Badge value={data.status} /><Badge tone="outline">{data.disclaimer}</Badge></div></header>
    <FiGovernance meta={meta} />
    <FiPartialWarning meta={meta} />

    <section className="grid cols-2">
      <Panel id="fi-financial-summary" eyebrow="Synthèse" title="Financial summary"><FiMetricGrid metrics={data.metrics} emptyTitle="Résumé financier indisponible" /></Panel>
      <Panel id="fi-cash-position" eyebrow="Trésorerie" title="Cash position" tools={<Banknote size={18} aria-hidden="true" />}><ResourceSection query={cash} emptyTitle="Position de trésorerie indisponible">{(position, responseMeta) => <CashPosition data={position} meta={responseMeta} />}</ResourceSection></Panel>
    </section>

    <Panel id="fi-company-flows" eyebrow="Flux" title="Flow evolution" tools={<Activity size={18} aria-hidden="true" />}><ResourceSection query={flows} emptyTitle="Synthèse des flux indisponible">{(flow, responseMeta) => <FlowSummary data={flow} meta={responseMeta} />}</ResourceSection></Panel>

    <section className="grid cols-2">
      <Panel id="fi-company-signals" eyebrow="Détections déterministes" title="Signals" tools={<Activity size={18} aria-hidden="true" />}><ResourceSection query={signals} emptyTitle="Signaux indisponibles">{(items) => <SignalTable signals={items} />}</ResourceSection></Panel>
      <Panel id="fi-company-opportunities" eyebrow="Références backend" title="Opportunities" tools={<Radar size={18} aria-hidden="true" />}><ResourceSection query={opportunities} emptyTitle="Opportunités indisponibles">{(items) => <OpportunityList opportunities={items} />}</ResourceSection></Panel>
    </section>

    <section className="grid cols-2">
      <Panel id="fi-company-visibility" eyebrow="Couverture" title="Multibank visibility" tools={<Eye size={18} aria-hidden="true" />}><dl className="fi-metric-grid"><div><dt>Niveau</dt><dd>{label(data.visibility.level)}</dd></div><div><dt>Part estimée</dt><dd>{formatPercent(data.visibility.estimatedShare, 1)}</dd></div><div><dt>Méthode</dt><dd>{label(data.visibility.method)}</dd></div><div><dt>Couverture catégorisation</dt><dd>{formatPercent(data.visibility.categorizationCoverage, 1)}</dd><small>fingerprints 90 j {data.visibility.fingerprintCount90d ?? '—'} · asOf {data.visibility.asOf ?? meta.asOf}</small></div></dl></Panel>
      <Panel id="fi-company-evidence" eyebrow="Traçabilité" title="Evidence"><ResourceSection query={signals} emptyTitle="Evidence indisponible">{(signalItems) => <ResourceSection query={opportunities} emptyTitle="Evidence indisponible">{(opportunityItems) => <EvidenceReferences signals={signalItems} opportunities={opportunityItems} />}</ResourceSection>}</ResourceSection></Panel>
    </section>

    <section className="grid cols-2">
      <Panel id="fi-company-provenance" eyebrow="Contrat" title="Provenance et asOf"><FiMeta meta={meta} /></Panel>
      <Panel id="fi-company-sources" eyebrow="Dépendances" title="État des sources"><FiSourceStatuses sources={meta.sourceStatus} /></Panel>
    </section>
  </div>
}
