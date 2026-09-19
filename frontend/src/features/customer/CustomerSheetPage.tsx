import { ArrowLeft, ArrowRight, Building2, CreditCard, Landmark, PackageSearch, PhoneCall, Radar, ShieldAlert, UserRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { formatCompact, formatDate, formatMoney, formatNumber, formatPercent, initials, label, opportunityTone } from '../../api/format'
import { useCustomer, useCustomerAccounts, useCustomerActions, useCustomerActivity, useCustomerMetrics, useCustomerOpportunities, useCustomerProducts, useCustomerPropensity, useCustomerSignals, useCustomerTransactions, useExplanation, useRelationshipManagerDashboard, useRelationshipManagerPortfolio } from '../../api/hooks'
import type { ActivityPoint, FinancialMetric, Opportunity, PortfolioCustomerSummary } from '../../api/types'
import { useAuth } from '../../auth/AuthProvider'
import { ActivityChart } from '../../charts/ActivityChart'
import { Sparkline } from '../../charts/Sparkline'
import { SERIES } from '../../charts/theme'
import { Badge, Button, Delta, EmptyState, ErrorState, Panel, PriorityBadge, Ring, Segmented, Skeleton, SkeletonStack, Tabs, Tooltip } from '../../ui'
import { ActionChoiceGrid } from './ActionPanel'
import { OpportunityDrawer } from './OpportunityDrawer'
import { PropensityDrawer } from './PropensityDrawer'
import { WhyChain } from './WhyChain'

type Period = '30' | '90' | '180' | '365'
type Mode = 'flows' | 'volume' | 'international'

const PERIODS: Array<{ value: Period; label: string; granularity: 'DAY' | 'WEEK' | 'MONTH' }> = [
  { value: '30', label: '30 jours', granularity: 'DAY' },
  { value: '90', label: '90 jours', granularity: 'WEEK' },
  { value: '180', label: '6 mois', granularity: 'WEEK' },
  { value: '365', label: '12 mois', granularity: 'MONTH' },
]

const metricByCode = (metrics: FinancialMetric[], code: string, period = '90D') => metrics.find((metric) => metric.metric === code && metric.period === period)

function sparkFor(points: ActivityPoint[], key: keyof ActivityPoint) {
  return points.map((point) => Number(point[key]) || 0)
}

export function CustomerSheetPage() {
  const { customerId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const auth = useAuth()
  const isRm = auth.hasRole('RELATIONSHIP_MANAGER') && !auth.hasRole('BRANCH_MANAGER')
  const railManager = params.get('cc') || undefined
  const dashboard = useRelationshipManagerDashboard(isRm)
  const managerPortfolio = useRelationshipManagerPortfolio(auth.hasRole('BRANCH_MANAGER') ? railManager : undefined)
  const customer = useCustomer(customerId)
  const propensity = useCustomerPropensity(customerId)
  const opportunities = useCustomerOpportunities(customerId)
  const metrics = useCustomerMetrics(customerId)
  const accounts = useCustomerAccounts(customerId)
  const products = useCustomerProducts(customerId)
  const signals = useCustomerSignals(customerId)
  const actions = useCustomerActions(customerId)
  const transactions = useCustomerTransactions(customerId, { pageSize: 8, sort: '-valueDate' })
  const [period, setPeriod] = useState<Period>('365')
  const [mode, setMode] = useState<Mode>('flows')
  const [tab, setTab] = useState<'actions' | 'positions' | 'transactions' | 'signals'>('actions')
  const selectedPeriod = PERIODS.find((item) => item.value === period)!
  // Date de référence = dernière observation analytique (asOf), jamais une date codée en dur.
  const asOfIso = metrics.data?.data[0]?.asOf
  const asOf = useMemo(() => (asOfIso ? new Date(asOfIso) : new Date()), [asOfIso])
  const fromDate = useMemo(() => new Date(asOf.getTime() - Number(period) * 86_400_000).toISOString().slice(0, 10), [asOf, period])
  const activity = useCustomerActivity(metrics.isPending ? undefined : customerId, { granularity: selectedPeriod.granularity, fromDate, toDate: asOf.toISOString().slice(0, 10) })
  const monthly = useCustomerActivity(customerId, { granularity: 'MONTH' })

  const opportunityList = useMemo(() => [...(opportunities.data?.data || [])].filter((item) => ['OPEN', 'ACCEPTED', 'CONTACTED'].includes(item.status)).sort((a, b) => b.priorityScore - a.priorityScore), [opportunities.data])
  const primary: Opportunity | undefined = opportunityList[0]
  const explanation = useExplanation(primary?.opportunityId)
  const drawerOpportunity = params.get('opportunite') || undefined
  const drawerPanel = params.get('panneau') || undefined
  const signalParam = params.get('signal') || undefined

  useEffect(() => { window.scrollTo({ top: 0 }) }, [customerId])

  const openOpportunity = (id: string, signal?: string) => { const next = new URLSearchParams(params); next.set('opportunite', id); if (signal) next.set('signal', signal); else next.delete('signal'); next.delete('panneau'); setParams(next) }
  const openPropensity = () => { const next = new URLSearchParams(params); next.set('panneau', 'propension'); next.delete('opportunite'); next.delete('signal'); setParams(next) }
  const closeDrawers = () => { const next = new URLSearchParams(params); next.delete('opportunite'); next.delete('panneau'); next.delete('signal'); setParams(next) }

  const rail: PortfolioCustomerSummary[] | undefined = isRm ? dashboard.data?.portfolio : managerPortfolio.data?.portfolio
  const railTitle = isRm ? 'À regarder aujourd’hui' : managerPortfolio.data?.scope.relationshipManagerName ? `Portefeuille de ${managerPortfolio.data.scope.relationshipManagerName}` : undefined
  const profile = customer.data
  const metricRows = metrics.data?.data || []
  const monthlyPoints = monthly.data?.points || []
  const health = [
    { key: 'transaction_count', title: 'Activité', spark: 'transactionCount' as const, color: SERIES.transactionCount, hint: 'Nombre de transactions sur 90 jours vs période précédente' },
    { key: 'inflow_amount', title: 'Encaissements', spark: 'inflow' as const, color: SERIES.inflow, hint: 'Montant encaissé sur 90 jours vs période précédente' },
    { key: 'supplier_payment_amount', title: 'Fournisseurs', spark: 'supplierPayments' as const, color: SERIES.supplierPayments, hint: 'Paiements fournisseurs sur 90 jours' },
    { key: 'outflow_amount', title: 'Décaissements', spark: 'outflow' as const, color: SERIES.outflow, hint: 'Montant décaissé sur 90 jours' },
    { key: 'international_flow_amount', title: 'International', spark: 'internationalAmount' as const, color: SERIES.internationalAmount, hint: 'Flux internationaux sur 90 jours' },
  ]
  const balance = accounts.data?.data.reduce((sum, account) => sum + (account.balance?.available || 0), 0)
  const relationSince = accounts.data?.data.map((account) => account.openedAt).filter(Boolean).sort()[0]

  return <div className={`cockpit ${rail ? '' : 'single'}`}>
    {rail && <aside className="rail" aria-label={railTitle}>
      <div className="rail-head"><h2>{railTitle}</h2><Link to={isRm ? '/' : railManager ? `/agence/cc/${railManager}` : '/'} className="btn ghost sm"><ArrowLeft size={14} /> Retour</Link></div>
      <div className="rail-list">{rail.map((item) => <button type="button" key={item.customerId} className={`rail-item ${item.customerId === customerId ? 'active' : ''}`} onClick={() => navigate(`/clients/${item.customerId}${railManager ? `?cc=${railManager}` : ''}`)} aria-current={item.customerId === customerId ? 'page' : undefined}><strong>{item.customerName}</strong><small>{label(item.industry)} · {item.openOpportunities[0] ? label(item.openOpportunities[0].opportunityType) : 'Suivi standard'}</small><span className="rail-score"><PriorityBadge level={item.priorityLevel} /></span></button>)}</div>
    </aside>}

    <div className="scene" key={customerId}>
      {customer.isPending ? <div className="stack"><Skeleton kind="block" /><SkeletonStack rows={3} /></div> : customer.isError || !profile ? <ErrorState error={customer.error} onRetry={() => void customer.refetch()} /> : <>
        <header className="sheet-head panel">
          <div className="sheet-identity">
            <span className="avatar company lg">{initials(profile.legalName)}</span>
            <div>
              <div className="row" style={{ gap: 8 }}><h1>{profile.legalName}</h1>{propensity.data?.priorityLevel && <PriorityBadge level={propensity.data.priorityLevel} />}<Badge value={profile.status} /></div>
              <p className="muted sheet-meta"><span><Building2 size={13} /> PME · {label(profile.industry)} · {label(profile.segment)}</span><span><Landmark size={13} /> Agence {profile.branchName || profile.branchId}</span><span><UserRound size={13} /> CC {profile.relationshipManagerName || profile.relationshipManagerId}</span>{relationSince && <span>Relation depuis {new Date(relationSince).getFullYear()}</span>}{profile.incorporatedOn && <span>Créée en {new Date(profile.incorporatedOn).getFullYear()}</span>}<span className="mono">{profile.customerId}</span></p>
            </div>
          </div>
          <div className="sheet-actions">
            <Tooltip content={<><strong>Propension commerciale</strong>Cliquer pour explorer les facteurs du score.</>}>
              {propensity.data ? <Ring value={propensity.data.score} size="lg" onClick={openPropensity} label={`Propension ${Math.round(propensity.data.score * 100)} %`} /> : <div className="ring lg" style={{ background: 'var(--ink-200)' }}><span className="faint" style={{ fontSize: 11 }}>{propensity.isPending ? '…' : 'n/a'}</span></div>}
            </Tooltip>
            <div className="stack" style={{ gap: 6 }}>
              {primary ? <>
                <span className="muted" style={{ fontSize: 12 }}>Opportunité principale</span>
                <Badge tone={opportunityTone(primary.opportunityType)}>{label(primary.opportunityType)} · {formatPercent(primary.confidence, 0)}</Badge>
                <div className="row" style={{ gap: 6 }}><Button variant="primary" size="sm" icon={<PhoneCall size={14} />} onClick={() => openOpportunity(primary.opportunityId)}>Action commerciale</Button><Button size="sm" onClick={() => openOpportunity(primary.opportunityId)} icon={<ArrowRight size={14} />}>Voir l’opportunité</Button></div>
              </> : <span className="muted" style={{ fontSize: 12 }}>Aucune opportunité ouverte</span>}
            </div>
          </div>
        </header>

        <Panel eyebrow="Santé de la relation" title="Ce qui change dans son activité" id="health" data-demo="health" tools={<span className="muted" style={{ fontSize: 12 }}>90 jours vs période précédente{asOfIso ? ` · au ${formatDate(asOfIso)}` : ''}</span>}>
          {metrics.isPending ? <div className="grid cols-4"><Skeleton kind="block" /><Skeleton kind="block" /><Skeleton kind="block" /><Skeleton kind="block" /></div> : metrics.isError ? <ErrorState error={metrics.error} compact /> : <div className="health-grid">
            {health.map((item) => { const metric = metricByCode(metricRows, item.key); return <Tooltip key={item.key} content={<><strong>{item.title}</strong>{item.hint}{metric?.historicalBaselineValue != null ? ` · baseline ${item.key === 'transaction_count' ? formatNumber(metric.historicalBaselineValue) : formatCompact(metric.historicalBaselineValue)}` : ''}</>}><article className="health-tile"><span className="stat-label">{item.title}</span><span className="health-value"><Delta value={metric?.growthRate} plain digits={0} /></span><span className="health-current num">{metric ? item.key === 'transaction_count' ? `${formatNumber(metric.currentValue)} op.` : formatCompact(metric.currentValue) : '—'}</span><Sparkline values={sparkFor(monthlyPoints, item.spark)} color={item.color} /></article></Tooltip> })}
            <article className="health-tile"><span className="stat-label">Trésorerie</span><span className="health-value num" style={{ fontSize: 17 }}>{accounts.isPending ? '…' : formatCompact(balance)}</span><span className="health-current">{accounts.data?.data.length ?? 0} compte(s) · solde disponible</span><span className="muted" style={{ fontSize: 11 }}>{(() => { const balanceMetric = metricByCode(metricRows, 'average_balance'); return balanceMetric ? <>Solde moyen <Delta value={balanceMetric.growthRate} plain /></> : null })()}</span></article>
          </div>}
        </Panel>

        <Panel eyebrow="Activité" title={mode === 'flows' ? 'Encaissements et décaissements' : mode === 'volume' ? 'Activité transactionnelle' : 'Flux internationaux'} id="activity" tools={<div className="row" style={{ gap: 8 }}><Tabs pill value={mode} onChange={(id) => setMode(id as Mode)} items={[{ id: 'flows', label: 'Flux' }, { id: 'volume', label: 'Volume' }, { id: 'international', label: 'International' }]} /><Segmented value={period} onChange={setPeriod} options={PERIODS.map((item) => ({ value: item.value, label: item.label }))} ariaLabel="Période" /></div>}>
          {activity.isPending ? <Skeleton kind="block" style={{ height: 240 }} /> : activity.isError ? <ErrorState error={activity.error} compact /> : <>
            <ActivityChart points={activity.data?.points || []} granularity={activity.data?.granularity || selectedPeriod.granularity} mode={mode} />
            <div className="legend" style={{ marginTop: 8 }}>{mode === 'flows' ? <><span><i style={{ background: SERIES.inflow }} /> Encaissements</span><span><i style={{ background: SERIES.outflow }} /> Décaissements</span></> : mode === 'volume' ? <span><i style={{ background: SERIES.transactionCount }} /> Transactions par {selectedPeriod.granularity === 'DAY' ? 'jour' : selectedPeriod.granularity === 'WEEK' ? 'semaine' : 'mois'}</span> : <span><i style={{ background: SERIES.internationalAmount }} /> Montant international</span>}<span className="faint">Source : transaction-service (agrégation SQL)</span></div>
          </>}
        </Panel>

        {primary ? <Panel eyebrow="Pourquoi cette opportunité ?" title={<>Chaîne d’évidence — {label(primary.opportunityType)}</>} id="why" tools={<Button size="sm" variant="soft" onClick={() => openOpportunity(primary.opportunityId)} icon={<ArrowRight size={14} />}>Voir l’opportunité</Button>}>
          <WhyChain opportunity={primary} explanation={explanation.data} propensity={propensity.data} loading={explanation.isPending} onSignal={(signalId) => openOpportunity(primary.opportunityId, signalId)} onMl={openPropensity} onOpportunity={() => openOpportunity(primary.opportunityId)} />
          {opportunityList.length > 1 && <div className="stack" style={{ marginTop: 16 }}><p className="eyebrow">Autres opportunités ouvertes</p><div className="opp-mini-list">{opportunityList.slice(1).map((item) => <button type="button" key={item.opportunityId} className="opp-mini" onClick={() => openOpportunity(item.opportunityId)}><Badge tone={opportunityTone(item.opportunityType)}>{label(item.opportunityType)}</Badge><span className="muted">{item.recommendedProducts?.[0]?.name || item.what}</span><b className="num">{formatPercent(item.confidence, 0)}</b><ArrowRight size={14} /></button>)}</div></div>}
        </Panel> : <Panel eyebrow="Opportunités" title="Aucune opportunité ouverte" id="why"><EmptyState compact icon={<Radar />} title="Rien à signaler pour le moment" message="Le moteur n’a détecté aucune combinaison de signaux justifiant une recommandation sur les 90 derniers jours. Les signaux isolés ou saisonniers sont volontairement écartés." /></Panel>}

        {primary && (auth.hasRole('RELATIONSHIP_MANAGER') || auth.hasRole('BRANCH_MANAGER')) && <Panel eyebrow="Action commerciale" title="Quelle suite donnez-vous ?" id="action" tools={<span className="muted" style={{ fontSize: 12 }}>Enregistré via l’API · audité · dashboard mis à jour</span>}>
          <ActionChoiceGrid opportunity={{ ...primary, customerName: profile.legalName }} customerId={customerId} />
        </Panel>}

        <Panel flush id="details">
          <div style={{ padding: '0 20px' }}><Tabs value={tab} onChange={(id) => setTab(id as typeof tab)} ariaLabel="Détails" items={[{ id: 'actions', label: 'Historique des actions', count: actions.data?.data.length }, { id: 'positions', label: 'Comptes & produits', count: (accounts.data?.data.length ?? 0) + (products.data?.data.length ?? 0) }, { id: 'transactions', label: 'Dernières transactions' }, { id: 'signals', label: 'Signaux', count: signals.data?.data.length }]} /></div>
          <div className="panel-body">
            {tab === 'actions' && (actions.isPending ? <SkeletonStack rows={3} kind="text" /> : !actions.data?.data.length ? <EmptyState compact title="Aucune action enregistrée" message="Les actions commerciales apparaîtront ici avec leur résultat." /> : <div className="timeline">{actions.data.data.map((action) => <article key={action.actionId} className={action.outcome ? 'done' : ''}><strong>{label(action.actionType)} {action.outcome && <Badge value={action.outcome} />}</strong><small>{formatDate(action.createdAt, true)} · {action.assignedTo || '—'}{action.dueAt ? ` · échéance ${formatDate(action.dueAt)}` : ''}</small>{action.note && <p>{action.note}</p>}</article>)}</div>)}
            {tab === 'positions' && <div className="grid cols-2">
              <div className="stack"><p className="eyebrow">Comptes</p>{accounts.isPending ? <SkeletonStack rows={2} kind="text" /> : !accounts.data?.data.length ? <p className="faint">Aucun compte.</p> : accounts.data.data.map((account) => <div className="row between position-row" key={account.accountId}><span><CreditCard size={14} /> <strong>{label(account.accountType)}</strong><small className="muted"> · {account.accountId}</small></span><span className="num"><strong>{formatMoney(account.balance?.available, account.currency)}</strong> <Badge value={account.status} /></span></div>)}</div>
              <div className="stack"><p className="eyebrow">Produits détenus</p>{products.isPending ? <SkeletonStack rows={2} kind="text" /> : !products.data?.data.length ? <p className="faint">Aucun produit détenu : équipement à construire.</p> : products.data.data.map((product) => <div className="row between position-row" key={product.productId}><span><PackageSearch size={14} /> <strong>{product.name}</strong><small className="muted"> · {label(product.category)}</small></span><Badge value={product.active ? 'ACTIVE' : 'INACTIVE'} /></div>)}</div>
            </div>}
            {tab === 'transactions' && (transactions.isPending ? <SkeletonStack rows={4} kind="text" /> : !transactions.data?.data.length ? <EmptyState compact title="Aucune transaction" /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Date</th><th>Catégorie</th><th>Type</th><th className="text-right">Montant</th></tr></thead><tbody>{transactions.data.data.map((tx) => <tr key={tx.transactionId}><td>{formatDate(tx.valueDate || tx.bookingDate)}</td><td><strong>{label(tx.category)}</strong>{tx.international && <small>International · {tx.countryCode}</small>}</td><td className="muted">{label(tx.type)}</td><td className={`text-right num ${tx.direction === 'CREDIT' ? 'up' : 'down'}`}>{tx.direction === 'CREDIT' ? '+' : '−'}{formatMoney(tx.amount, tx.currency)}</td></tr>)}</tbody></table></div>)}
            {tab === 'signals' && (signals.isPending ? <SkeletonStack rows={3} kind="text" /> : !signals.data?.data.length ? <EmptyState compact title="Aucun signal actif" /> : <div className="table-wrap"><table className="table"><thead><tr><th>Signal</th><th>Période</th><th className="text-right">Valeur</th><th className="text-right">Seuil</th><th>Sévérité</th><th>Détecté</th></tr></thead><tbody>{signals.data.data.map((signal) => <tr key={signal.signalId}><td><strong>{label(signal.type)}</strong></td><td>{label(signal.period)}</td><td className="text-right num">{formatPercent(signal.value, 1)}</td><td className="text-right num muted">{formatPercent(signal.threshold, 0)}</td><td><Badge value={signal.severity} /></td><td className="muted">{formatDate(signal.detectedAt)}</td></tr>)}</tbody></table></div>)}
          </div>
        </Panel>

        <div className="notice neutral"><ShieldAlert size={16} /><div><strong>Cadre d’usage</strong>Cette fiche organise le travail commercial. Elle ne constitue ni une notation de risque ni une décision de crédit ; le signal de tension financière, s’il existe, est un signal relationnel à examiner par le chargé de clientèle.</div></div>
      </>}
    </div>

    {drawerOpportunity && <OpportunityDrawer opportunityId={drawerOpportunity} customerId={customerId} customerName={profile?.legalName} initialSignal={signalParam} onClose={closeDrawers} onPropensity={openPropensity} />}
    {drawerPanel === 'propension' && <PropensityDrawer customerId={customerId} customerName={profile?.legalName} opportunity={primary} onClose={closeDrawers} />}
  </div>
}
