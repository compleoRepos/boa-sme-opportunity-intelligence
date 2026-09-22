import { CalendarClock, Check, History, PackageSearch, Radar, ShieldCheck, Target } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip as ChartTip, XAxis, YAxis } from 'recharts'
import { formatCompact, formatDate, formatMonth, formatNumber, formatPercent, label, opportunityTone } from '../../api/format'
import { useCustomerActivity, useExplanation, useOpportunity, useOpportunityActions } from '../../api/hooks'
import type { ActivityPoint, Explanation, Opportunity } from '../../api/types'
import { useAuth } from '../../auth/AuthProvider'
import { ChartTooltip } from '../../charts/ChartTooltip'
import { CHART, SERIES, axisProps } from '../../charts/theme'
import { Badge, Drawer, EmptyState, ErrorState, PriorityBadge, Ring, SkeletonStack, tabId, Tabs } from '../../ui'
import { ActionChoiceGrid } from './ActionPanel'

type SignalRow = Explanation['signals'][number]

const SIGNAL_SERIES: Record<string, { key: keyof ActivityPoint; color: string; money: boolean }> = {
  INFLOW_GROWTH: { key: 'inflow', color: SERIES.inflow, money: true },
  OUTFLOW_GROWTH: { key: 'outflow', color: SERIES.outflow, money: true },
  SUPPLIER_PAYMENT_GROWTH: { key: 'supplierPayments', color: SERIES.supplierPayments, money: true },
  TRANSACTION_VOLUME_GROWTH: { key: 'transactionCount', color: SERIES.transactionCount, money: false },
  INTERNATIONAL_FLOW_GROWTH: { key: 'internationalAmount', color: SERIES.internationalAmount, money: true },
}

export function OpportunityDrawer({ opportunityId, customerId, customerName, initialSignal, onClose, onPropensity }: { opportunityId: string; customerId: string; customerName?: string; initialSignal?: string; onClose: () => void; onPropensity?: () => void }) {
  const opportunity = useOpportunity(opportunityId)
  const explanation = useExplanation(opportunityId)
  const actions = useOpportunityActions(opportunityId)
  const activity = useCustomerActivity(customerId, { granularity: 'MONTH' })
  const [tab, setTab] = useState<'signals' | 'confidence' | 'history'>('signals')
  const [selectedSignal, setSelectedSignal] = useState<string | undefined>(initialSignal)
  const auth = useAuth()
  const canAct = auth.hasRole('RELATIONSHIP_MANAGER') || auth.hasRole('BRANCH_MANAGER')
  const item = opportunity.data
  const signals = explanation.data?.signals || []
  const active = useMemo(() => signals.find((signal) => signal.signalId === selectedSignal) || signals[0], [signals, selectedSignal])

  return <Drawer eyebrow={item ? `Opportunité · ${label(item.opportunityType)}` : 'Opportunité'} title={customerName || item?.customerName || opportunityId} onClose={onClose} size="wide" data-demo="opportunity"
    tools={item && <div className="row" style={{ gap: 6 }}><PriorityBadge level={item.priorityLevel} /><Badge value={item.status} /></div>}
    footer={item && canAct ? <><span className="muted" style={{ fontSize: 12 }}>Chaque choix crée une action auditée via l’API.</span><Link to={`/opportunites/${item.opportunityId}`} className="btn ghost sm">Vue détaillée</Link></> : undefined}>
    {opportunity.isPending ? <SkeletonStack rows={4} kind="block" /> : opportunity.isError || !item ? <ErrorState error={opportunity.error} onRetry={() => void opportunity.refetch()} /> : <>
      <section className="opp-hero">
        <div className="opp-hero-copy">
          <div className="row wrap" style={{ gap: 6 }}><Badge tone={opportunityTone(item.opportunityType)}>{label(item.opportunityType)}</Badge><Badge tone={item.recommendationNature === 'WIN_BACK' ? 'teal' : 'outline'}>{item.recommendationNature === 'WIN_BACK' ? 'Reconquête' : 'Besoin détecté'}</Badge></div>
          <h3>{item.what}</h3>
          <p className="muted"><CalendarClock size={13} /> {item.when} · horizon {label(item.horizon)} · détectée le {formatDate(item.generatedAt)}</p>
          <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>{item.recommendedProducts?.map((product) => <span className="chip product" key={product.productId}><PackageSearch size={12} /> {product.name}</span>)}</div>
        </div>
        <div className="opp-hero-scores">
          <div className="stat"><span className="stat-label">Confiance</span><Ring value={item.confidence} size="lg" label={`Confiance ${Math.round(item.confidence * 100)} %`} /></div>
          <div className="stat"><span className="stat-label">Priorité</span><span className="stat-value num">{formatNumber(item.priorityScore, 0)}<small className="muted" style={{ fontSize: 12 }}> /100</small></span><span className="stat-note">{label(item.priorityLevel)}</span></div>
          <button type="button" className="stat propensity-link" onClick={onPropensity} title="Explorer le score de propension"><span className="stat-label">Propension ML</span><span className="stat-value sm">Explorer →</span></button>
        </div>
      </section>

      {canAct && <section className="stack" style={{ gap: 8 }}>
        <div className="row between"><div><p className="eyebrow">Action commerciale</p><h3 style={{ fontSize: 14 }}>Quelle suite donnez-vous ?</h3></div><span className="muted" style={{ fontSize: 12 }}>Mise à jour immédiate du dashboard</span></div>
        <ActionChoiceGrid opportunity={{ ...item, customerName: customerName || item.customerName }} customerId={customerId} compact />
      </section>}

      <Tabs value={tab} onChange={(id) => setTab(id as typeof tab)} ariaLabel="Détail de l’opportunité" panelId="opportunity-tabpanel" items={[{ id: 'signals', label: 'Signaux & évidence', icon: <Radar size={14} />, count: signals.length || item.why?.length }, { id: 'confidence', label: 'Règle & confiance', icon: <ShieldCheck size={14} /> }, { id: 'history', label: 'Historique', icon: <History size={14} />, count: actions.data?.data.length }]} />

      <div id="opportunity-tabpanel" role="tabpanel" aria-labelledby={tabId('opportunity-tabpanel', tab)} tabIndex={0}>
      {tab === 'signals' && <section className="stack">
        {explanation.isPending ? <SkeletonStack rows={3} /> : explanation.isError ? <ErrorState error={explanation.error} compact /> : !signals.length ? <EmptyState title="Aucun signal détaillé" message={item.why?.join(' · ') || 'Le moteur n’a retourné aucun signal.'} compact /> : <>
          <div className="signal-tabs">{signals.map((signal) => <button type="button" key={signal.signalId} className={`signal-tab ${active?.signalId === signal.signalId ? 'active' : ''}`} onClick={() => setSelectedSignal(signal.signalId)} aria-pressed={active?.signalId === signal.signalId}><span>{label(signal.type)}</span><b className={`num ${signal.value >= 0 ? 'up' : 'down'}`}>{signal.value >= 0 ? '+' : ''}{formatPercent(signal.value, 0)}</b><small>seuil {formatPercent(signal.threshold, 0)} · {label(signal.period)}</small></button>)}</div>
          {active && <SignalDetail signal={active} points={activity.data?.points || []} loading={activity.isPending} />}
        </>}
      </section>}

      {tab === 'confidence' && <section className="stack">
        <dl className="kv">
          <dt>Règle déclenchée</dt><dd>{item.opportunityType} · version {item.ruleVersion || explanation.data?.ruleVersion || '—'}</dd>
          <dt>Moteur</dt><dd>{item.engineVersion || explanation.data?.engineVersion || '—'}</dd>
          <dt>Comparaison</dt><dd>{typeof explanation.data?.historicalComparison === 'object' && explanation.data?.historicalComparison ? `Période précédente + baseline ${String((explanation.data.historicalComparison as Record<string, unknown>).baselinePeriod || '')}` : 'Période précédente et baseline historique'}</dd>
          <dt>Seuils appliqués</dt><dd>{explanation.data?.thresholds ? Object.entries(explanation.data.thresholds).map(([key, value]) => `${label(key)} ${typeof value === 'number' ? formatPercent(value, 0) : String(value)}`).join(' · ') : '—'}</dd>
        </dl>
        <div><p className="eyebrow" style={{ marginBottom: 8 }}>Composantes de confiance</p>
          {explanation.data?.confidenceComponents?.length ? <ul className="component-list">{explanation.data.confidenceComponents.map((component) => <li key={component.name} className={component.name === 'visibility' ? 'visibility-component' : undefined}><span className={`score-check ${component.satisfied ? 'ok' : ''}`}>{component.satisfied ? <Check size={12} /> : '–'}</span><span className="component-label">{label(component.name)}{component.name === 'visibility' && <small>Visibilité des flux partielle : signal de niveau pondéré</small>}</span><span className="bar thin"><i style={{ width: `${component.maxPoints ? Math.min(100, (component.points / component.maxPoints) * 100) : 0}%` }} /></span><span className="num muted" style={{ fontSize: 12 }}>{formatNumber(component.points, 1)}/{formatNumber(component.maxPoints, 0)}</span></li>)}</ul> : <p className="faint">Aucune composante retournée.</p>}
        </div>
        <div className="notice info"><Target size={16} /><div><strong>Évidence, pas boîte noire</strong>Signaux, règle métier, features et propension ML sont tous versionnés et consultables. Le LLM n’intervient pas dans la décision.</div></div>
      </section>}

      {tab === 'history' && <section>
        {actions.isPending ? <SkeletonStack rows={3} kind="text" /> : actions.isError ? <ErrorState error={actions.error} compact /> : !actions.data?.data.length ? <EmptyState title="Aucune action" message="Aucune suite commerciale n’a encore été enregistrée sur cette opportunité." compact /> : <div className="timeline">{actions.data.data.map((action) => <article key={action.actionId} className={action.outcome ? 'done' : ''}><strong>{label(action.actionType)}{action.outcome ? <Badge value={action.outcome} className="ml" /> : null}</strong><small>{formatDate(action.createdAt, true)} · {action.assignedTo || action.createdBy || '—'}{action.dueAt ? ` · échéance ${formatDate(action.dueAt)}` : ''}</small>{action.note && <p>{action.note}</p>}</article>)}</div>}
      </section>}
      </div>
    </>}
  </Drawer>
}

function SignalDetail({ signal, points, loading }: { signal: SignalRow; points: ActivityPoint[]; loading: boolean }) {
  const series = SIGNAL_SERIES[signal.type]
  const evidence = (signal.evidence || []) as Array<string | { text?: string }>
  const data = points.map((point) => ({ label: formatMonth(point.period), value: series ? Number(point[series.key]) : 0 }))
  const baseline = data.length >= 6 ? data.slice(0, data.length - 3).reduce((sum, item) => sum + item.value, 0) / Math.max(1, data.length - 3) : undefined
  return <div className="signal-detail">
    <div className="row between wrap">
      <div><h3 style={{ fontSize: 14 }}>{label(signal.type)} · {label(signal.period)}</h3><p className="muted" style={{ fontSize: 12 }}>Valeur observée <b className="num">{formatPercent(signal.value, 1)}</b> contre un seuil de <b className="num">{formatPercent(signal.threshold, 0)}</b> · détecté le {formatDate(signal.detectedAt)} · règle v{signal.ruleVersion || '1'}</p></div>
      <Badge value={signal.severity} />
    </div>
    {series ? loading ? <div className="skeleton block" /> : data.length ? <div className="chart-card"><ResponsiveContainer width="100%" height={180}><AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
      <defs><linearGradient id="sigFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={series.color} stopOpacity={0.18} /><stop offset="100%" stopColor={series.color} stopOpacity={0} /></linearGradient></defs>
      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={20} />
      <YAxis {...axisProps} width={46} tickFormatter={(value: number) => series.money ? formatCompact(value).replace(/\s?(M|k)?MAD$/, ' $1').trim() : formatNumber(value)} />
      {baseline != null && <ReferenceLine y={baseline} stroke={CHART.axis} strokeDasharray="4 4" label={{ value: 'baseline', position: 'insideTopLeft', fontSize: 10, fill: CHART.text }} />}
      <ChartTip content={({ payload }) => { const point = payload?.[0]?.payload as { label: string; value: number } | undefined; return point ? <ChartTooltip title={point.label} rows={[{ name: label(signal.type), value: series.money ? formatCompact(point.value) : formatNumber(point.value), color: series.color }]} /> : null }} />
      <Area type="monotone" dataKey="value" stroke={series.color} strokeWidth={2} fill="url(#sigFill)" dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} />
    </AreaChart></ResponsiveContainer><p className="faint" style={{ fontSize: 11, marginTop: 4 }}>Évolution mensuelle sur 12 mois, agrégée depuis les transactions importées. Les 3 derniers mois sont comparés à la baseline des mois précédents.</p></div> : <div className="chart-empty">Aucune série disponible.</div> : <div className="notice neutral"><Radar size={16} /><div><strong>Signal de niveau</strong>Ce signal porte sur un niveau (solde, utilisation de ligne) et non sur un flux ; consultez les positions bancaires de la fiche.</div></div>}
    {evidence.length > 0 && <ul className="evidence-list">{evidence.map((entry, index) => <li key={index}><Check size={12} /> {typeof entry === 'string' ? entry : entry.text}</li>)}</ul>}
  </div>
}
