import { ArrowDownRight, ArrowLeft, ArrowRight, Building2, CreditCard, Equal, Gauge, Landmark, PackageSearch, ShieldAlert, Sparkles, UserRound } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatDate, formatMoney, formatNumber, formatPercent, getCustomerName, label, metricUnit } from '../api/format'
import { useCustomer, useCustomerAccounts, useCustomerActions, useCustomerMetrics, useCustomerOpportunities, useCustomerProducts, useCustomerPropensity, useCustomerSignals, useCustomerTransactions } from '../api/hooks'
import type { FinancialMetric } from '../api/types'
import { OpportunityCard } from '../components/OpportunityCard'
import { Badge, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UI'

const trendMetricKeys = ['MONTHLY_INFLOW', 'MONTHLY_OUTFLOW', 'AVERAGE_BALANCE', 'INTERNATIONAL_FLOW_AMOUNT', 'CREDIT_LINE_UTILIZATION']
const normalized = (name: string) => name.toUpperCase()

function metricValue(metric: FinancialMetric) {
  const unit = metricUnit(metric.metric)
  return unit === 'percent' ? formatPercent(metric.currentValue, 1) : unit === 'money' ? formatMoney(metric.currentValue, metric.currency) : formatNumber(metric.currentValue)
}

export function Customer360Page() {
  const { customerId } = useParams()
  const customer = useCustomer(customerId)
  const accounts = useCustomerAccounts(customerId)
  const products = useCustomerProducts(customerId)
  const transactions = useCustomerTransactions(customerId, { pageSize: 10, sort: '-bookingDate' })
  const metrics = useCustomerMetrics(customerId)
  const propensity = useCustomerPropensity(customerId)
  const signals = useCustomerSignals(customerId)
  const opportunities = useCustomerOpportunities(customerId)
  const actions = useCustomerActions(customerId)
  if (customer.isPending) return <div className="page"><LoadingState label="Composition de la vue Customer 360…" /></div>
  if (customer.isError || !customer.data) return <div className="page"><ErrorState error={customer.error} onRetry={() => void customer.refetch()} /></div>
  const profile = customer.data
  const metricItems = metrics.data?.data ?? []
  const dates = [...new Set(metricItems.map((item) => item.asOf))].sort()
  const chartData = dates.map((date) => {
    const point: Record<string, string | number> = { date: formatDate(date) }
    metricItems.filter((item) => item.asOf === date && trendMetricKeys.includes(normalized(item.metric))).forEach((item) => { point[normalized(item.metric)] = item.currentValue })
    return point
  })
  const balance = accounts.data?.data.reduce((sum, account) => sum + (account.balance?.available || 0), 0)

  return <div className="page customer-360">
    <Link className="back-link" to="/clients"><ArrowLeft size={16} /> Retour au portefeuille</Link>
    <PageHeader eyebrow={`CUSTOMER 360 · ${profile.customerId}`} title={getCustomerName(profile)} description={`${label(profile.industry)} · ${label(profile.sector)} · ${label(profile.segment)}`} actions={<Badge value={profile.status} />} />
    <section className="profile-strip"><div className="profile-company"><span><Building2 /></span><div><strong>{profile.legalName}</strong><small>{profile.tradeName || profile.customerId}</small></div></div><div><UserRound /><span>Chargé d’affaires</span><strong>{profile.relationshipManagerName || profile.relationshipManagerId || '—'}</strong></div><div><Landmark /><span>Agence</span><strong>{profile.branchId || '—'}</strong></div><div><CreditCard /><span>Solde disponible agrégé</span><strong>{accounts.isPending ? '…' : formatMoney(balance, accounts.data?.data[0]?.currency)}</strong></div></section>

    <section className="panel propensity-panel" aria-labelledby="propensity-title">
      <header className="panel-header"><div><p className="eyebrow">PROPENSION COMMERCIALE</p><h2 id="propensity-title">Potentiel d’engagement commercial</h2></div><span>Score borné de 0 à 1</span></header>
      {propensity.isPending ? <LoadingState label="Calcul de la propension commerciale…" /> : propensity.isError || !propensity.data ? <ErrorState error={propensity.error} onRetry={() => void propensity.refetch()} /> : (() => {
        const assessment = propensity.data
        const score = Math.min(1, Math.max(0, assessment.score))
        const percent = Math.round(score * 100)
        return <>
          <div className="propensity-hero">
            <div className="propensity-score-card">
              <span className="propensity-score-icon" aria-hidden="true"><Gauge /></span>
              <div><span>Score de propension</span><strong>{score.toFixed(2)}</strong><small>{percent}% · {assessment.scoreMeaning || 'probabilité d’intérêt commercial estimée'}</small></div>
              {assessment.priorityLevel && <Badge value={assessment.priorityLevel} />}
              <div className="propensity-track large" aria-hidden="true"><i style={{ width: `${percent}%` }} /></div>
            </div>
            <div className="propensity-governance">
              <article><span>Version du modèle</span><strong>{assessment.model.modelVersion}</strong><small>{assessment.model.modelId || 'Modèle de propension'}</small></article>
              <article><span>Jeu de features</span><strong>{assessment.model.featureSetVersion}</strong><small>{assessment.model.scoredAt ? `Calculé le ${formatDate(assessment.model.scoredAt, true)}` : 'Version auditée'}</small></article>
            </div>
          </div>
          <div className="hybrid-explanation" role="note">
            <div><Sparkles aria-hidden="true" /><span><strong>ML</strong><small>{formatPercent(assessment.combination.mlScore, 1)} × {formatPercent(assessment.combination.mlWeight)}</small></span></div>
            <span className="hybrid-plus" aria-hidden="true">+</span>
            <div><ShieldAlert aria-hidden="true" /><span><strong>Règles métier</strong><small>{formatPercent(assessment.combination.rulesScore, 1)} × {formatPercent(assessment.combination.rulesWeight)}</small></span></div>
            <ArrowRight className="hybrid-arrow" aria-hidden="true" />
            <div className="hybrid-result"><Equal aria-hidden="true" /><span><strong>Score combiné {score.toFixed(2)}</strong><small>{assessment.combination.summary || 'Combinaison gouvernée du modèle et des règles actives'}</small></span></div>
          </div>
          <div className="factor-section">
            <div className="section-heading"><div><p className="eyebrow">EXPLICABILITÉ</p><h3>Facteurs qui influencent le score</h3></div><span className="section-context">{formatNumber(assessment.factors.length)} facteur{assessment.factors.length > 1 ? 's' : ''}</span></div>
            {!assessment.factors.length ? <EmptyState title="Aucun facteur disponible" message="Le service de propension n’a retourné aucun facteur explicatif." /> : <div className="factor-grid">{assessment.factors.map((factor) => {
              const positive = factor.direction === 'POSITIVE'
              const negative = factor.direction === 'NEGATIVE'
              const DirectionIcon = positive ? ArrowRight : negative ? ArrowDownRight : Equal
              return <article className={`factor-card ${positive ? 'positive' : negative ? 'negative' : 'neutral'}`} key={factor.feature}>
                <span className="factor-direction" aria-label={positive ? 'Impact positif' : negative ? 'Impact négatif' : 'Impact neutre'}><DirectionIcon /></span>
                <div><span>{factor.label}</span><strong>{factor.value == null ? '—' : typeof factor.value === 'number' ? formatNumber(factor.value, 2) : String(factor.value)}</strong><p>{factor.explanation}</p>{factor.contribution != null && <small>Contribution {factor.contribution > 0 ? '+' : ''}{formatNumber(factor.contribution, 3)}{factor.source ? ` · ${factor.source}` : ''}</small>}</div>
              </article>
            })}</div>}
          </div>
          <div className="credit-warning" role="note"><ShieldAlert aria-hidden="true" /><div><strong>Aucune décision de crédit</strong><span>Ce score priorise la relation commerciale. Il ne mesure pas le risque, ne détermine aucune éligibilité et doit être interprété par le chargé d’affaires.</span>{assessment.warnings?.map((warning) => <small key={warning}>{warning}</small>)}</div></div>
        </>
      })()}
    </section>

    <section className="panel"><header className="panel-header"><div><p className="eyebrow">TENDANCES FINANCIÈRES</p><h2>Évolution des indicateurs</h2></div><span>Données analytiques Gateway</span></header>{metrics.isPending ? <LoadingState label="Chargement des métriques…" /> : metrics.isError ? <ErrorState error={metrics.error} onRetry={() => void metrics.refetch()} /> : !metricItems.length ? <EmptyState title="Aucune métrique" message="Le service Analytics n’a retourné aucune série pour ce client." /> : <><div className="metric-snapshot">{trendMetricKeys.map((key) => { const item = [...metricItems].reverse().find((metric) => normalized(metric.metric) === key); return item ? <article key={key}><span>{label(key)}</span><strong>{metricValue(item)}</strong><small>{item.growthRate == null ? label(item.period) : `${formatPercent(item.growthRate, 1)} · ${label(item.period)}`}</small></article> : null })}</div>{chartData.length > 1 ? <ResponsiveContainer width="100%" height={330}><LineChart data={chartData} margin={{ top: 20, right: 30, left: 10, bottom: 10 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis yAxisId="money" tick={{ fontSize: 11 }} /><YAxis yAxisId="percent" orientation="right" tickFormatter={(value) => `${Math.round(value * 100)}%`} /><Tooltip /><Legend />{[
      ['MONTHLY_INFLOW', '#0c8b68', 'money'], ['MONTHLY_OUTFLOW', '#d49b2a', 'money'], ['AVERAGE_BALANCE', '#1b4d7a', 'money'], ['INTERNATIONAL_FLOW_AMOUNT', '#6b5aa6', 'money'], ['CREDIT_LINE_UTILIZATION', '#c75252', 'percent'],
    ].map(([key, color, axis]) => <Line key={key} type="monotone" dataKey={key} name={label(key)} stroke={color} strokeWidth={2.5} yAxisId={axis} dot={false} connectNulls />)}</LineChart></ResponsiveContainer> : <div className="chart-note">Une seule période a été retournée ; le graphique temporel nécessite au moins deux observations.</div>}</>}</section>

    <div className="two-column-sections"><section className="panel"><header className="panel-header"><div><p className="eyebrow">COMPTES & SOLDES</p><h2>Positions bancaires</h2></div></header>{accounts.isPending ? <LoadingState /> : accounts.isError ? <ErrorState error={accounts.error} /> : !accounts.data?.data.length ? <EmptyState /> : <div className="data-list">{accounts.data.data.map((account) => <article key={account.accountId}><div><strong>{label(account.accountType)}</strong><span>{account.accountId} · {account.currency}</span></div><div className="text-right"><strong>{formatMoney(account.balance?.available, account.balance?.currency || account.currency)}</strong><Badge value={account.status} /></div></article>)}</div>}</section>
      <section className="panel"><header className="panel-header"><div><p className="eyebrow">PRODUITS DÉTENUS</p><h2>Équipement</h2></div><PackageSearch /></header>{products.isPending ? <LoadingState /> : products.isError ? <ErrorState error={products.error} /> : !products.data?.data.length ? <EmptyState title="Aucun produit retourné" /> : <div className="data-list">{products.data.data.map((product) => <article key={product.productId}><div><strong>{product.name}</strong><span>{label(product.category)}</span></div><Badge value={product.active ? 'ACTIVE' : 'INACTIVE'} /></article>)}</div>}</section></div>

    <section className="panel"><header className="panel-header"><div><p className="eyebrow">TRANSACTIONS RÉCENTES</p><h2>Derniers mouvements</h2></div><span>10 résultats maximum</span></header>{transactions.isPending ? <LoadingState /> : transactions.isError ? <ErrorState error={transactions.error} /> : !transactions.data?.data.length ? <EmptyState /> : <div className="table-wrap"><table><thead><tr><th>Date</th><th>Libellé</th><th>Catégorie</th><th>Compte</th><th className="text-right">Montant</th></tr></thead><tbody>{transactions.data.data.map((transaction) => <tr key={transaction.transactionId}><td>{formatDate(transaction.bookingDate)}</td><td><strong>{transaction.counterpartyName || transaction.description || transaction.type}</strong>{transaction.international && <Badge value="International" tone="info" />}</td><td>{label(transaction.category)}</td><td>{transaction.accountId}</td><td className={`text-right amount ${transaction.direction === 'CREDIT' ? 'credit' : 'debit'}`}>{transaction.direction === 'CREDIT' ? '+' : '−'}{formatMoney(transaction.amount, transaction.currency)}</td></tr>)}</tbody></table></div>}</section>

    <section className="section-block"><div className="section-heading"><div><p className="eyebrow">OPPORTUNITÉS</p><h2>Recommandations pour ce client</h2></div></div>{opportunities.isPending ? <LoadingState /> : opportunities.isError ? <ErrorState error={opportunities.error} /> : !opportunities.data?.data.length ? <EmptyState title="Aucune opportunité" /> : <div className="opportunity-list">{opportunities.data.data.map((item) => <OpportunityCard key={item.opportunityId} opportunity={item} compact />)}</div>}</section>
    <div className="two-column-sections"><section className="panel"><header className="panel-header"><div><p className="eyebrow">SIGNAUX</p><h2>Événements détectés</h2></div></header>{signals.isPending ? <LoadingState /> : signals.isError ? <ErrorState error={signals.error} /> : !signals.data?.data.length ? <EmptyState /> : <div className="data-list">{signals.data.data.map((signal) => <article key={signal.signalId}><div><strong>{label(signal.type)}</strong><span>{formatDate(signal.detectedAt)} · {label(signal.period)}</span></div><Badge value={signal.severity} /></article>)}</div>}</section>
      <section className="panel"><header className="panel-header"><div><p className="eyebrow">ACTIONS</p><h2>Historique relationnel</h2></div></header>{actions.isPending ? <LoadingState /> : actions.isError ? <ErrorState error={actions.error} /> : !actions.data?.data.length ? <EmptyState /> : <div className="data-list">{actions.data.data.map((action) => <article key={action.actionId}><div><strong>{label(action.actionType)}</strong><span>{formatDate(action.createdAt, true)}</span></div>{action.outcome && <Badge value={action.outcome} />}</article>)}</div>}</section></div>
  </div>
}
