import { Coins, PackageSearch } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { label, safeJson } from '../api/format'
import { useProducts } from '../api/hooks'
import { Badge, EmptyState, ErrorState, Panel, Segmented, SkeletonStack } from '../ui'

export function ProductsPage() {
  const [params, setParams] = useSearchParams()
  const active = params.get('active') || 'true'
  const query = useProducts({ pageSize: 100, active })
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Product directory</p><h1>Catalogue de produits</h1><p className="subtitle">Noms, catégories et règles d’éligibilité fournis par le Product Service : le moteur référence ces identifiants, jamais des libellés codés en dur.</p></div><div className="page-actions"><Segmented value={active} onChange={(value) => setParams(value ? { active: value } : {})} options={[{ value: 'true', label: 'Actifs' }, { value: 'false', label: 'Inactifs' }, { value: '', label: 'Tous' }]} /></div></header>
    {query.isPending ? <SkeletonStack rows={3} kind="block" /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucun produit" /> : <div className="grid cols-3">{query.data.data.map((product) => <Panel key={product.productId} eyebrow={label(product.category)} title={<span className="row" style={{ gap: 8 }}>{product.category?.includes('INVEST') ? <Coins size={16} /> : <PackageSearch size={16} />}{product.name}</span>} id={`product-${product.productId}`} tools={<Badge value={product.active ? 'ACTIVE' : 'INACTIVE'} />}><dl className="kv"><dt>Identifiant</dt><dd className="mono">{product.productId}</dd><dt>Segments</dt><dd>{Array.isArray(product.targetSegment) ? product.targetSegment.map(label).join(', ') : label(product.targetSegment)}</dd><dt>Devises</dt><dd>{Array.isArray(product.currency) ? product.currency.join(', ') : product.currency || '—'}</dd></dl><details style={{ marginTop: 10 }}><summary className="muted" style={{ cursor: 'pointer', fontSize: 12 }}>Règles d’éligibilité</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{safeJson(product.eligibilityRules)}</pre></details></Panel>)}</div>}
  </>
}
