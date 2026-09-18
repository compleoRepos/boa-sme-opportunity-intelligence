import { ArrowRight, CheckCircle2, Filter } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, label } from '../api/format'
import { useActions, useUpdateAction } from '../api/hooks'
import type { OpportunityAction, Outcome } from '../api/types'
import { Badge, CursorPagination, EmptyState, ErrorState, PageHeader, SkeletonRows, type CursorState } from '../components/UI'

function OutcomeControl({ action }: { action: OpportunityAction }) {
  const mutation = useUpdateAction(action.actionId, action.opportunityId)
  const outcomes: Outcome[] = ['CONTACTED','MEETING_SCHEDULED','OFFER_CREATED','CONVERTED','REJECTED','NOT_RELEVANT']
  return <div className="outcome-control"><select aria-label={`Résultat de ${action.actionId}`} defaultValue={action.outcome || ''} onChange={(event) => { const outcome = event.target.value as Outcome; if (outcome) mutation.mutate({ outcome, status: 'COMPLETED' }) }} disabled={mutation.isPending}><option value="">Enregistrer un résultat…</option>{outcomes.map((outcome) => <option key={outcome} value={outcome}>{label(outcome)}</option>)}</select>{mutation.isPending && <span>Enregistrement…</span>}{mutation.isError && <span className="form-error">{mutation.error.message}</span>}</div>
}

export function ActionsPage() {
  const [draft, setDraft] = useState({ opportunityId: '', customerId: '', actionType: '', outcome: '' })
  const [filters, setFilters] = useState(draft)
  const [pagination, setPagination] = useState<CursorState>({ cursors: [undefined], index: 0 })
  const query = useActions({ ...filters, pageSize: 25, cursor: pagination.cursors[pagination.index], sort: '-createdAt' })
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setPagination({ cursors: [undefined], index: 0 }) }
  const changePage = (next: CursorState) => next.index > pagination.index ? setPagination({ cursors: [...pagination.cursors.slice(0, pagination.index + 1), query.data?.meta.nextCursor || undefined], index: next.index }) : setPagination(next)
  return <div className="page"><PageHeader eyebrow="SUIVI COMMERCIAL" title="Actions & résultats" description="Les actions et outcomes alimentent la boucle de feedback du moteur." />
    <form className="compact-filters" onSubmit={submit}><input placeholder="ID opportunité" value={draft.opportunityId} onChange={(e) => setDraft({ ...draft, opportunityId: e.target.value })} /><input placeholder="ID client" value={draft.customerId} onChange={(e) => setDraft({ ...draft, customerId: e.target.value })} /><select value={draft.actionType} onChange={(e) => setDraft({ ...draft, actionType: e.target.value })}><option value="">Toutes les actions</option>{['ACCEPT_OPPORTUNITY','DISMISS_OPPORTUNITY','CONTACT_CUSTOMER','CREATE_FOLLOW_UP','SCHEDULE_MEETING','MARK_CONVERTED'].map((v) => <option key={v} value={v}>{label(v)}</option>)}</select><select value={draft.outcome} onChange={(e) => setDraft({ ...draft, outcome: e.target.value })}><option value="">Tous les résultats</option>{['CONTACTED','MEETING_SCHEDULED','OFFER_CREATED','CONVERTED','REJECTED','NOT_RELEVANT'].map((v) => <option key={v} value={v}>{label(v)}</option>)}</select><button type="submit" className="button primary"><Filter size={16} /> Filtrer</button></form>
    {query.isPending ? <SkeletonRows /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucune action" /> : <><div className="action-list">{query.data.data.map((action) => <article className="action-item" key={action.actionId}><span className="action-state"><CheckCircle2 /></span><div className="action-copy"><small>{action.actionId}</small><h2>{label(action.actionType)}</h2><p>{action.note || 'Aucune note associée'}</p><div><span>Créée le {formatDate(action.createdAt, true)}</span>{action.dueAt && <span>Échéance {formatDate(action.dueAt, true)}</span>}<Link to={`/opportunites/${action.opportunityId}`}>Ouvrir l’opportunité <ArrowRight size={14} /></Link></div></div><div className="action-outcome">{action.outcome && <Badge value={action.outcome} tone="success" />}<OutcomeControl action={action} /></div></article>)}</div><CursorPagination state={pagination} hasMore={query.data.meta.hasMore} onChange={changePage} /></>}
  </div>
}
