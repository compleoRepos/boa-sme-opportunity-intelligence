import { ArrowRight, Filter, X } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { formatDate, formatNumber, formatPercent, getCustomerName, label, opportunityTone } from '../api/format'
import { useOpportunities, useOpportunity } from '../api/hooks'
import type { ListQuery } from '../api/types'
import { Badge, Button, ErrorState, NoResults, Panel, PriorityBadge, SkeletonStack } from '../ui'

const initial = { type: '', confidence: '', priority: '', horizon: '', status: '', sort: '-priorityScore' }

export function OpportunitiesPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState(initial)
  const [filters, setFilters] = useState(initial)
  const [cursors, setCursors] = useState<Array<string | undefined>>([undefined])
  const params = useMemo<ListQuery>(() => ({ pageSize: 25, cursor: cursors[cursors.length - 1], type: filters.type, minConfidence: filters.confidence, priorityLevel: filters.priority, horizon: filters.horizon, status: filters.status, sort: filters.sort }), [filters, cursors])
  const query = useOpportunities(params)
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setCursors([undefined]) }
  const set = (key: keyof typeof initial, value: string) => setDraft((current) => ({ ...current, [key]: value }))
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Pipeline commercial</p><h1>Opportunités</h1><p className="subtitle">Recommandations calculées par le moteur, filtrées et paginées côté serveur.</p></div></header>
    <Panel flush id="opportunities">
      <form className="panel-body filter-row" onSubmit={submit}>
        <label className="field">Type<select className="select sm" value={draft.type} onChange={(event) => set('type', event.target.value)}><option value="">Tous</option>{['INVESTMENT_FINANCING', 'TRADE_FINANCE', 'CASH_INVESTMENT', 'FINANCIAL_STRESS_SIGNAL'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label className="field">Confiance min.<select className="select sm" value={draft.confidence} onChange={(event) => set('confidence', event.target.value)}><option value="">Toutes</option><option value="0.75">75 %</option><option value="0.5">50 %</option></select></label>
        <label className="field">Priorité<select className="select sm" value={draft.priority} onChange={(event) => set('priority', event.target.value)}><option value="">Toutes</option>{['P1', 'P2', 'P3', 'P4'].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="field">Horizon<select className="select sm" value={draft.horizon} onChange={(event) => set('horizon', event.target.value)}><option value="">Tous</option>{['0-1_MONTH', '0-3_MONTHS', '1-3_MONTHS'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label className="field">Statut<select className="select sm" value={draft.status} onChange={(event) => set('status', event.target.value)}><option value="">Tous</option>{['OPEN', 'ACCEPTED', 'CONTACTED', 'DISMISSED', 'DEFERRED', 'CONVERTED', 'EXPIRED'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label className="field">Tri<select className="select sm" value={draft.sort} onChange={(event) => set('sort', event.target.value)}><option value="-priorityScore">Priorité</option><option value="-confidence">Confiance</option><option value="-generatedAt">Plus récentes</option></select></label>
        <div className="row" style={{ gap: 6, alignSelf: 'flex-end' }}><Button size="sm" variant="ghost" icon={<X size={14} />} onClick={() => { setDraft(initial); setFilters(initial); setCursors([undefined]) }}>Réinitialiser</Button><Button size="sm" variant="primary" type="submit" icon={<Filter size={14} />}>Appliquer</Button></div>
      </form>
      {query.isPending ? <div className="panel-body"><SkeletonStack rows={6} /></div> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <NoResults /> : <div className="table-wrap"><table className="table hover clickable"><thead><tr><th>PME</th><th>Opportunité</th><th>Produit</th><th className="num">Confiance</th><th className="num">Priorité</th><th>Horizon</th><th>Statut</th><th>Détectée</th><th /></tr></thead><tbody>{query.data.data.map((item) => <tr key={item.opportunityId} onClick={() => navigate(`/clients/${item.customerId}?opportunite=${item.opportunityId}`)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') navigate(`/clients/${item.customerId}?opportunite=${item.opportunityId}`) }}><td><strong>{getCustomerName(item)}</strong><small className="mono">{item.customerId}</small></td><td><Badge tone={opportunityTone(item.opportunityType)}>{label(item.opportunityType)}</Badge></td><td className="muted">{item.recommendedProducts?.[0]?.name || '—'}</td><td className="num"><strong>{formatPercent(item.confidence, 0)}</strong> <small className="muted">{label(item.confidenceLevel)}</small></td><td className="num"><PriorityBadge level={item.priorityLevel} /> <span className="muted">{formatNumber(item.priorityScore, 0)}</span></td><td>{label(item.horizon)}</td><td><Badge value={item.status} /></td><td className="muted">{formatDate(item.generatedAt)}</td><td><ArrowRight size={14} className="muted" /></td></tr>)}</tbody></table></div>}
      {query.data && <div className="row between" style={{ padding: '10px 20px', borderTop: '1px solid var(--border)' }}><span className="muted" style={{ fontSize: 12 }}>Page {cursors.length} · {query.data.data.length} résultat(s)</span><div className="row" style={{ gap: 6 }}><Button size="sm" disabled={cursors.length === 1} onClick={() => setCursors((list) => list.slice(0, -1))}>Précédent</Button><Button size="sm" disabled={!query.data.meta.hasMore} onClick={() => setCursors((list) => [...list, query.data?.meta.nextCursor || undefined])}>Suivant</Button></div></div>}
    </Panel>
  </>
}

/** Lien profond vers une opportunité : redirige vers la fiche PME avec le drawer ouvert (cockpit unique). */
export function OpportunityRedirectPage() {
  const { opportunityId = '' } = useParams()
  const query = useOpportunity(opportunityId)
  const navigate = useNavigate()
  if (query.isPending) return <SkeletonStack rows={3} kind="block" />
  if (query.isError || !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  navigate(`/clients/${query.data.customerId}?opportunite=${opportunityId}`, { replace: true })
  return <p className="muted">Ouverture de la fiche PME… <Link to={`/clients/${query.data.customerId}?opportunite=${opportunityId}`}>continuer</Link></p>
}
