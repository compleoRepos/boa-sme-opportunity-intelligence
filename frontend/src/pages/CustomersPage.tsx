import { ArrowRight, Building2, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getCustomerName, initials, label } from '../api/format'
import { useCustomers } from '../api/hooks'
import { Badge, Button, ErrorState, NoResults, Panel, SkeletonStack } from '../ui'

export function CustomersPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') || ''
  const [draft, setDraft] = useState(q)
  const [cursors, setCursors] = useState<Array<string | undefined>>([undefined])
  const cursor = cursors[cursors.length - 1]
  const query = useCustomers({ q, pageSize: 25, cursor, sort: 'legalName' })
  const submit = (event: FormEvent) => { event.preventDefault(); setCursors([undefined]); setParams(draft ? { q: draft } : {}) }
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Portefeuille</p><h1>Clients PME</h1><p className="subtitle">Recherche par raison sociale ou identifiant, paginée et filtrée par le Gateway selon votre périmètre.</p></div></header>
    <Panel flush id="customers">
      <form className="panel-head list-head" onSubmit={submit} role="search"><div className="search" style={{ flex: 1, maxWidth: 480 }}><Search size={14} /><input className="input" placeholder="Raison sociale, identifiant SME-…" aria-label="Rechercher un client" value={draft} onChange={(event) => setDraft(event.target.value)} /></div><Button type="submit" variant="primary" size="sm">Rechercher</Button></form>
      {query.isPending ? <div className="panel-body"><SkeletonStack rows={5} /></div> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <NoResults message="Aucune PME ne correspond dans votre périmètre." /> : <div className="table-wrap"><table className="table hover clickable"><thead><tr><th>PME</th><th>Secteur</th><th>Segment</th><th>Agence</th><th>Chargé de clientèle</th><th>Statut</th><th /></tr></thead><tbody>{query.data.data.map((customer) => <tr key={customer.customerId} onClick={() => navigate(`/clients/${customer.customerId}`)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') navigate(`/clients/${customer.customerId}`) }}><td><div className="row"><span className="avatar company">{initials(customer.legalName)}</span><span><strong>{getCustomerName(customer)}</strong><small className="mono">{customer.customerId}</small></span></div></td><td>{label(customer.industry)}</td><td>{label(customer.segment)}</td><td>{customer.branchName || customer.branchId || '—'}</td><td>{customer.relationshipManagerName || customer.relationshipManagerId || '—'}</td><td><Badge value={customer.status} /></td><td><Link to={`/clients/${customer.customerId}`} className="btn ghost sm" onClick={(event) => event.stopPropagation()}>Fiche <ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>}
      {query.data && <div className="row between" style={{ padding: '10px 20px', borderTop: '1px solid var(--border)' }}><span className="muted" style={{ fontSize: 12 }}><Building2 size={12} /> Page {cursors.length}</span><div className="row" style={{ gap: 6 }}><Button size="sm" disabled={cursors.length === 1} onClick={() => setCursors((list) => list.slice(0, -1))}>Précédent</Button><Button size="sm" disabled={!query.data.meta.hasMore} onClick={() => setCursors((list) => [...list, query.data?.meta.nextCursor || undefined])}>Suivant</Button></div></div>}
    </Panel>
  </>
}
