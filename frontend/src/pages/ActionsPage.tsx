import { ArrowRight, CalendarClock, Filter } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, label } from '../api/format'
import { useActions, useUpdateAction } from '../api/hooks'
import type { OpportunityAction, Outcome } from '../api/types'
import { Badge, Button, EmptyState, ErrorState, Panel, SkeletonStack, useToast } from '../ui'

const OUTCOMES: Outcome[] = ['CONTACTED', 'MEETING_SCHEDULED', 'OFFER_CREATED', 'CONVERTED', 'REJECTED', 'NOT_RELEVANT']

function OutcomeControl({ action }: { action: OpportunityAction }) {
  const mutation = useUpdateAction(action.actionId, action.opportunityId)
  const toast = useToast()
  return <select className="select sm" aria-label={`Résultat de ${action.actionId}`} value={action.outcome || ''} disabled={mutation.isPending} onChange={(event) => { const outcome = event.target.value as Outcome; if (outcome) mutation.mutate({ outcome, status: 'COMPLETED' }, { onSuccess: () => toast.push('success', 'Résultat enregistré', label(outcome)), onError: (error) => toast.push('error', 'Mise à jour refusée', error.message) }) }}><option value="">Enregistrer un résultat…</option>{OUTCOMES.map((outcome) => <option key={outcome} value={outcome}>{label(outcome)}</option>)}</select>
}

export function ActionsPage() {
  const [draft, setDraft] = useState({ actionType: '', outcome: '' })
  const [filters, setFilters] = useState(draft)
  const [cursors, setCursors] = useState<Array<string | undefined>>([undefined])
  const query = useActions({ ...filters, pageSize: 25, cursor: cursors[cursors.length - 1], sort: '-createdAt' })
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setCursors([undefined]) }
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Suivi commercial</p><h1>Actions & résultats</h1><p className="subtitle">Chaque action alimente la boucle de feedback : recommandation → action → réponse client → outcome.</p></div></header>
    <Panel flush id="actions">
      <form className="panel-body filter-row" onSubmit={submit}>
        <label className="field">Type d’action<select className="select sm" value={draft.actionType} onChange={(event) => setDraft({ ...draft, actionType: event.target.value })}><option value="">Toutes</option>{['ACCEPT_OPPORTUNITY', 'DISMISS_OPPORTUNITY', 'CONTACT_CUSTOMER', 'CREATE_FOLLOW_UP', 'SCHEDULE_MEETING', 'MARK_CONVERTED'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label className="field">Résultat<select className="select sm" value={draft.outcome} onChange={(event) => setDraft({ ...draft, outcome: event.target.value })}><option value="">Tous</option>{OUTCOMES.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <Button size="sm" variant="primary" type="submit" icon={<Filter size={14} />} style={{ alignSelf: 'flex-end' }}>Filtrer</Button>
      </form>
      {query.isPending ? <div className="panel-body"><SkeletonStack rows={4} /></div> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState icon={<CalendarClock />} title="Aucune action" message="Enregistrez une action depuis une opportunité : elle apparaîtra ici avec son résultat." /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Action</th><th>Client</th><th>Note</th><th>Échéance</th><th>Résultat</th><th /></tr></thead><tbody>{query.data.data.map((action) => <tr key={action.actionId}><td><strong>{label(action.actionType)}</strong><small>{formatDate(action.createdAt, true)} · {action.assignedTo || '—'}</small></td><td><Link to={`/clients/${action.customerId}`}>{action.customerId}</Link></td><td className="muted" style={{ maxWidth: 320 }}>{action.note || '—'}</td><td>{action.dueAt ? formatDate(action.dueAt) : '—'}</td><td>{action.outcome ? <Badge value={action.outcome} /> : <OutcomeControl action={action} />}</td><td><Link to={`/clients/${action.customerId}?opportunite=${action.opportunityId}`} className="btn ghost sm">Opportunité <ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>}
      {query.data && <div className="row between" style={{ padding: '10px 20px', borderTop: '1px solid var(--border)' }}><span className="muted" style={{ fontSize: 12 }}>Page {cursors.length}</span><div className="row" style={{ gap: 6 }}><Button size="sm" disabled={cursors.length === 1} onClick={() => setCursors((list) => list.slice(0, -1))}>Précédent</Button><Button size="sm" disabled={!query.data.meta.hasMore} onClick={() => setCursors((list) => [...list, query.data?.meta.nextCursor || undefined])}>Suivant</Button></div></div>}
    </Panel>
  </>
}
