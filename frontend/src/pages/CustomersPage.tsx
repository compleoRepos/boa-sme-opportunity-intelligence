import { ArrowRight, Building2, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useCustomers } from '../api/hooks'
import { getCustomerName, label } from '../api/format'
import { Badge, CursorPagination, EmptyState, ErrorState, PageHeader, SkeletonRows, type CursorState } from '../components/UI'

export function CustomersPage() {
  const [draft, setDraft] = useState('')
  const [q, setQ] = useState('')
  const [pagination, setPagination] = useState<CursorState>({ cursors: [undefined], index: 0 })
  const query = useCustomers({ q, pageSize: 25, cursor: pagination.cursors[pagination.index], sort: 'legalName' })
  const submit = (event: FormEvent) => { event.preventDefault(); setQ(draft); setPagination({ cursors: [undefined], index: 0 }) }
  const changePage = (next: CursorState) => {
    if (next.index > pagination.index) setPagination({ cursors: [...pagination.cursors.slice(0, pagination.index + 1), query.data?.meta.nextCursor || undefined], index: next.index })
    else setPagination(next)
  }
  return <div className="page"><PageHeader eyebrow="PORTEFEUILLE" title="Clients PME" description="Recherchez par raison sociale, identifiant client, compte ou industrie. Les résultats sont paginés par le Gateway." />
    <form className="inline-search" onSubmit={submit}><Search /><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Rechercher un client…" aria-label="Rechercher un client" /><button className="button primary" type="submit">Rechercher</button></form>
    {query.isPending ? <SkeletonRows /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucun client trouvé" /> : <><div className="customer-grid">{query.data.data.map((customer) => <article className="customer-card" key={customer.customerId}><div className="company-icon"><Building2 /></div><div><small>{customer.customerId}</small><h2>{getCustomerName(customer)}</h2><p>{label(customer.industry)} · {label(customer.segment)}</p><div className="customer-card-meta"><Badge value={customer.status} /><span>{customer.relationshipManagerName || customer.relationshipManagerId || 'RM non renseigné'}</span></div></div><Link className="button secondary" to={`/clients/${customer.customerId}`}>Vue 360 <ArrowRight size={16} /></Link></article>)}</div><CursorPagination state={pagination} hasMore={query.data.meta.hasMore} onChange={changePage} /></>}
  </div>
}
