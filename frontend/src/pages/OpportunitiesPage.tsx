import { Filter, Search, X } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useOpportunities } from '../api/hooks'
import { label } from '../api/format'
import type { ListQuery } from '../api/types'
import { OpportunityCard } from '../components/OpportunityCard'
import { CursorPagination, EmptyState, ErrorState, PageHeader, SkeletonRows, type CursorState } from '../components/UI'

interface Filters { q: string; type: string; confidence: string; priority: string; sector: string; segment: string; relationshipManagerId: string; horizon: string; fromDate: string; toDate: string; sort: string }
const initial: Filters = { q: '', type: '', confidence: '', priority: '', sector: '', segment: '', relationshipManagerId: '', horizon: '', fromDate: '', toDate: '', sort: '-priorityScore' }

export function OpportunitiesPage() {
  const [draft, setDraft] = useState(initial)
  const [filters, setFilters] = useState(initial)
  const [pagination, setPagination] = useState<CursorState>({ cursors: [undefined], index: 0 })
  const params = useMemo<ListQuery>(() => ({ pageSize: 20, cursor: pagination.cursors[pagination.index], q: filters.q, type: filters.type, minConfidence: filters.confidence, priorityLevel: filters.priority, sector: filters.sector, customerSegment: filters.segment, relationshipManagerId: filters.relationshipManagerId, horizon: filters.horizon, fromDate: filters.fromDate, toDate: filters.toDate, sort: filters.sort }), [filters, pagination])
  const query = useOpportunities(params)
  const set = (key: keyof Filters, value: string) => setDraft((current) => ({ ...current, [key]: value }))
  const submit = (event: FormEvent) => { event.preventDefault(); setFilters(draft); setPagination({ cursors: [undefined], index: 0 }) }
  const reset = () => { setDraft(initial); setFilters(initial); setPagination({ cursors: [undefined], index: 0 }) }
  const changePage = (next: CursorState) => {
    if (next.index > pagination.index) {
      const cursor = query.data?.meta.nextCursor || undefined
      setPagination({ cursors: [...pagination.cursors.slice(0, pagination.index + 1), cursor], index: next.index })
    } else setPagination(next)
  }

  return <div className="page">
    <PageHeader eyebrow="PIPELINE COMMERCIAL" title="Opportunités" description="Filtrez et priorisez les recommandations calculées par le moteur, sans charger l’ensemble du portefeuille dans le navigateur." />
    <form className="filter-panel" onSubmit={submit}>
      <div className="search-control"><Search size={18} /><input value={draft.q} onChange={(event) => set('q', event.target.value)} placeholder="Entreprise, identifiant client, compte, industrie…" aria-label="Rechercher" /></div>
      <div className="filter-grid">
        <label>Type<select value={draft.type} onChange={(event) => set('type', event.target.value)}><option value="">Tous</option>{['INVESTMENT_FINANCING', 'TRADE_FINANCE', 'CASH_INVESTMENT', 'FINANCIAL_STRESS_SIGNAL'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Confiance minimale<select value={draft.confidence} onChange={(event) => set('confidence', event.target.value)}><option value="">Toutes</option><option value="0.75">75 %</option><option value="0.5">50 %</option></select></label>
        <label>Priorité<select value={draft.priority} onChange={(event) => set('priority', event.target.value)}><option value="">Toutes</option>{['P1', 'P2', 'P3', 'P4'].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Secteur<input value={draft.sector} onChange={(event) => set('sector', event.target.value)} placeholder="Ex. MANUFACTURING" /></label>
        <label>Segment<input value={draft.segment} onChange={(event) => set('segment', event.target.value)} placeholder="Ex. SME" /></label>
        <label>Chargé d’affaires<input value={draft.relationshipManagerId} onChange={(event) => set('relationshipManagerId', event.target.value)} placeholder="Identifiant RM" /></label>
        <label>Horizon<select value={draft.horizon} onChange={(event) => set('horizon', event.target.value)}><option value="">Tous</option>{['0-1_MONTH', '0-3_MONTHS', '1-3_MONTHS'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Du<input type="date" value={draft.fromDate} onChange={(event) => set('fromDate', event.target.value)} /></label>
        <label>Au<input type="date" value={draft.toDate} onChange={(event) => set('toDate', event.target.value)} /></label>
        <label>Trier par<select value={draft.sort} onChange={(event) => set('sort', event.target.value)}><option value="-priorityScore">Priorité décroissante</option><option value="-confidence">Confiance décroissante</option><option value="-generatedAt">Plus récentes</option><option value="generatedAt">Plus anciennes</option></select></label>
      </div>
      <div className="filter-actions"><button type="button" className="button ghost" onClick={reset}><X size={16} /> Réinitialiser</button><button type="submit" className="button primary"><Filter size={16} /> Appliquer les filtres</button></div>
    </form>
    <div className="results-bar"><span><strong>{query.data?.meta.totalCount ?? query.data?.data.length ?? '—'}</strong> résultat(s) {query.data?.meta.totalCount == null && 'sur cette page'}</span><span>Page de {query.data?.meta.pageSize ?? 20}</span></div>
    {query.isPending ? <SkeletonRows count={6} /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucune opportunité trouvée" message="Modifiez les filtres ou vérifiez que le moteur a généré des opportunités pour votre périmètre." /> : <><div className="opportunity-list">{query.data.data.map((opportunity) => <OpportunityCard key={opportunity.opportunityId} opportunity={opportunity} />)}</div><CursorPagination state={pagination} hasMore={query.data.meta.hasMore} onChange={changePage} /></>}
  </div>
}
