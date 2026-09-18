import { Activity, Filter } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, formatPercent, label } from '../api/format'
import { useSignals } from '../api/hooks'
import { Badge, CursorPagination, EmptyState, ErrorState, PageHeader, SkeletonRows, type CursorState } from '../components/UI'

export function SignalsPage() {
  const [draft, setDraft] = useState({ customerId: '', type: '', severity: '', fromDate: '', toDate: '' })
  const [filters, setFilters] = useState(draft)
  const [pagination, setPagination] = useState<CursorState>({ cursors: [undefined], index: 0 })
  const query = useSignals({ ...filters, pageSize: 25, cursor: pagination.cursors[pagination.index], sort: '-detectedAt' })
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setPagination({ cursors: [undefined], index: 0 }) }
  const changePage = (next: CursorState) => next.index > pagination.index ? setPagination({ cursors: [...pagination.cursors.slice(0, pagination.index + 1), query.data?.meta.nextCursor || undefined], index: next.index }) : setPagination(next)
  return <div className="page"><PageHeader eyebrow="DÉTECTION" title="Signaux bancaires" description="Événements observés par le moteur analytique. Un signal n’est pas encore une opportunité commerciale." />
    <form className="compact-filters" onSubmit={submit}><input placeholder="Identifiant client" value={draft.customerId} onChange={(e) => setDraft({ ...draft, customerId: e.target.value })} /><select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}><option value="">Tous les types</option>{['INFLOW_GROWTH','OUTFLOW_GROWTH','SUPPLIER_PAYMENT_GROWTH','INTERNATIONAL_FLOW_GROWTH','BALANCE_SURPLUS','BALANCE_DECLINE','CREDIT_UTILIZATION_INCREASE','TRANSACTION_VOLUME_GROWTH'].map((v) => <option key={v} value={v}>{label(v)}</option>)}</select><select value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value })}><option value="">Toutes sévérités</option>{['HIGH','MEDIUM','LOW'].map((v) => <option key={v}>{label(v)}</option>)}</select><input type="date" value={draft.fromDate} onChange={(e) => setDraft({ ...draft, fromDate: e.target.value })} /><input type="date" value={draft.toDate} onChange={(e) => setDraft({ ...draft, toDate: e.target.value })} /><button className="button primary" type="submit"><Filter size={16} /> Filtrer</button></form>
    {query.isPending ? <SkeletonRows /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucun signal" /> : <><div className="signal-grid">{query.data.data.map((signal) => <article className="signal-card" key={signal.signalId}><header><span className="signal-icon"><Activity /></span><Badge value={signal.severity} /></header><small>{signal.signalId}</small><h2>{label(signal.type)}</h2><p><Link to={`/clients/${signal.customerId}`}>{signal.customerName || signal.customerId}</Link></p><div className="signal-measure"><div><span>Valeur observée</span><strong>{formatPercent(signal.value, 1)}</strong></div><div><span>Seuil appliqué</span><strong>{formatPercent(signal.threshold, 1)}</strong></div></div>{signal.evidence?.length ? <ul>{signal.evidence.slice(0, 2).map((evidence) => <li key={evidence}>{evidence}</li>)}</ul> : <p className="muted">Aucune preuve résumée.</p>}<footer><span>{formatDate(signal.detectedAt, true)}</span><span>{label(signal.period)}</span></footer></article>)}</div><CursorPagination state={pagination} hasMore={query.data.meta.hasMore} onChange={changePage} /></>}
  </div>
}
