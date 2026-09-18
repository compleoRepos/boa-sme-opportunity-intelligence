import { Coins, Filter, PackageSearch } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { formatNumber, label, safeJson } from '../api/format'
import { useProducts } from '../api/hooks'
import { Badge, EmptyState, ErrorState, PageHeader, SkeletonRows } from '../components/UI'

export function ProductsPage() {
  const [params, setParams] = useSearchParams()
  const category = params.get('category') || ''
  const active = params.get('active') || 'true'
  const productId = params.get('productId') || ''
  const query = useProducts({ pageSize: 100, category, active, productId })
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); setParams(next) }
  return <div className="page"><PageHeader eyebrow="PRODUCT DIRECTORY" title="Catalogue de produits" description="Les noms, catégories et règles d’éligibilité sont fournis par le Product Service. Ils ne sont pas codés dans l’interface." />
    <div className="compact-filters"><select value={category} onChange={(e) => update('category', e.target.value)}><option value="">Toutes catégories</option><option value="FINANCING">Financement</option><option value="TRADE_FINANCE">Trade finance</option><option value="CASH_MANAGEMENT">Cash management</option><option value="INVESTMENT">Placement</option></select><select value={active} onChange={(e) => update('active', e.target.value)}><option value="true">Produits actifs</option><option value="false">Produits inactifs</option><option value="">Tous les produits</option></select><span className="filter-readonly"><Filter size={16} /> Filtrage serveur</span></div>
    {query.isPending ? <SkeletonRows /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucun produit" /> : <div className="product-grid">{query.data.data.map((product) => <article className="product-card" key={product.productId}><header><span className="product-icon">{product.category?.includes('INVEST') ? <Coins /> : <PackageSearch />}</span><Badge value={product.active ? 'ACTIVE' : 'INACTIVE'} /></header><small>{product.productId}</small><h2>{product.name}</h2><p>{product.description || label(product.category)}</p><dl><div><dt>Catégorie</dt><dd>{label(product.category)}</dd></div><div><dt>Segment cible</dt><dd>{Array.isArray(product.targetSegment) ? product.targetSegment.map(label).join(', ') : label(product.targetSegment)}</dd></div><div><dt>Devise</dt><dd>{Array.isArray(product.currency) ? product.currency.join(', ') : product.currency || '—'}</dd></div></dl><details><summary>Règles d’éligibilité</summary><pre>{safeJson(product.eligibilityRules)}</pre></details></article>)}</div>}
    {query.data?.meta.totalCount != null && <p className="results-foot">{formatNumber(query.data.meta.totalCount)} produit(s) retourné(s)</p>}
  </div>
}
