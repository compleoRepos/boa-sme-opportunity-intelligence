import { Activity, Filter } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, formatPercent, label } from '../api/format'
import { useSignals } from '../api/hooks'
import { Badge, Button, EmptyState, ErrorState, Panel, SkeletonStack } from '../ui'

export function SignalsPage() {
  const [draft, setDraft] = useState({ type: '', severity: '' })
  const [filters, setFilters] = useState(draft)
  const [cursors, setCursors] = useState<Array<string | undefined>>([undefined])
  const query = useSignals({ ...filters, pageSize: 25, cursor: cursors[cursors.length - 1], sort: '-detectedAt' })
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setCursors([undefined]) }
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Détection</p><h1>Signaux bancaires</h1><p className="subtitle">Événements observés par le moteur analytique. Un signal n’est pas encore une opportunité : il doit être confirmé et combiné par une règle.</p></div></header>
    <Panel flush id="signals">
      <form className="panel-body filter-row" onSubmit={submit}>
        <label className="field">Type<select className="select sm" value={draft.type} onChange={(event) => setDraft({ ...draft, type: event.target.value })}><option value="">Tous</option>{['INFLOW_GROWTH', 'OUTFLOW_GROWTH', 'SUPPLIER_PAYMENT_GROWTH', 'INTERNATIONAL_FLOW_GROWTH', 'BALANCE_SURPLUS', 'BALANCE_DECLINE', 'CREDIT_UTILIZATION_INCREASE', 'TRANSACTION_VOLUME_GROWTH'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label className="field">Sévérité<select className="select sm" value={draft.severity} onChange={(event) => setDraft({ ...draft, severity: event.target.value })}><option value="">Toutes</option>{['HIGH', 'MEDIUM', 'LOW'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <Button size="sm" variant="primary" type="submit" icon={<Filter size={14} />} style={{ alignSelf: 'flex-end' }}>Filtrer</Button>
      </form>
      {query.isPending ? <div className="panel-body"><SkeletonStack rows={5} /></div> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState icon={<Activity />} title="Aucun signal" /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Signal</th><th>Client</th><th>Période</th><th className="num">Valeur</th><th className="num">Seuil</th><th>Sévérité</th><th>Statut</th><th>Détecté</th></tr></thead><tbody>{query.data.data.map((signal) => <tr key={signal.signalId}><td><strong>{label(signal.type)}</strong></td><td><Link to={`/clients/${signal.customerId}`}>{signal.customerName || signal.customerId}</Link></td><td>{label(signal.period)}</td><td className="num">{formatPercent(signal.value, 1)}</td><td className="num muted">{formatPercent(signal.threshold, 0)}</td><td><Badge value={signal.severity} /></td><td><Badge value={signal.status} tone="outline" /></td><td className="muted">{formatDate(signal.detectedAt)}</td></tr>)}</tbody></table></div>}
      {query.data && <div className="row between" style={{ padding: '10px 20px', borderTop: '1px solid var(--border)' }}><span className="muted" style={{ fontSize: 12 }}>Page {cursors.length}</span><div className="row" style={{ gap: 6 }}><Button size="sm" disabled={cursors.length === 1} onClick={() => setCursors((list) => list.slice(0, -1))}>Précédent</Button><Button size="sm" disabled={!query.data.meta.hasMore} onClick={() => setCursors((list) => [...list, query.data?.meta.nextCursor || undefined])}>Suivant</Button></div></div>}
    </Panel>
  </>
}
