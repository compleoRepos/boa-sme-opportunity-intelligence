import { ExternalLink, Landmark } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { familyLabel, familyRank, label, safeJson } from '../api/format'
import { useProducts } from '../api/hooks'
import type { Product } from '../api/types'
import { Badge, EmptyState, ErrorState, Panel, Segmented, SkeletonStack } from '../ui'

function groupByFamily(products: Product[]): Array<[string, Product[]]> {
  const groups = new Map<string, Product[]>()
  const sorted = [...products].sort((a, b) => familyRank(a.family) - familyRank(b.family) || a.name.localeCompare(b.name, 'fr'))
  for (const product of sorted) {
    const key = product.family || product.productId
    groups.set(key, [...(groups.get(key) || []), product])
  }
  return [...groups.entries()]
}

export function ProductsPage() {
  const [params, setParams] = useSearchParams()
  const active = params.get('active') || 'true'
  const query = useProducts({ pageSize: 100, active })
  const groups = query.data ? groupByFamily(query.data.data) : []
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Référentiel indicatif</p><h1>Produits BANK OF AFRICA visibles publiquement</h1><p className="subtitle">Noms, descriptions et liens relevés sur bankofafrica.ma. Les ciblages et critères restent à valider avec BOA avant un pilote réel. Le moteur raisonne par famille ; les règles recommandent des produits précis sans automatiser une décision de crédit.</p></div><div className="page-actions"><Segmented value={active} onChange={(value) => setParams(value ? { active: value } : {})} options={[{ value: 'true', label: 'Actifs' }, { value: 'false', label: 'Inactifs' }, { value: '', label: 'Tous' }]} /></div></header>
    {query.isPending ? <SkeletonStack rows={3} kind="block" /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucun produit" /> : groups.map(([family, products]) => <section key={family} className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: 'baseline' }}><h2 style={{ margin: 0 }}>{familyLabel(family)}</h2><span className="muted" style={{ fontSize: 12 }}>{products.length} produit{products.length > 1 ? 's' : ''} · famille <span className="mono">{family}</span></span></div>
      <div className="grid cols-3">{products.map((product) => <Panel key={product.productId} eyebrow={label(product.category)} title={<span className="row" style={{ gap: 8 }}><Landmark size={16} />{product.name}</span>} id={`product-${product.productId}`} tools={<Badge value={product.active ? 'ACTIVE' : 'INACTIVE'} />}>
        {product.description && <p style={{ margin: '0 0 10px', fontSize: 13, lineHeight: 1.5 }}>{product.description}</p>}
        <dl className="kv"><dt>Identifiant</dt><dd className="mono">{product.productId}</dd><dt>Ciblage public relevé</dt><dd>{Array.isArray(product.targetSegment) ? (product.targetSegment.length ? product.targetSegment.map(label).join(', ') : 'À valider avec BOA') : label(product.targetSegment)}</dd><dt>Devises</dt><dd>{Array.isArray(product.currency) ? product.currency.join(', ') : product.currency || '—'}</dd></dl>
        <div className="row" style={{ gap: 12, marginTop: 10, alignItems: 'center' }}>
          {product.sourceUrl && <a href={product.sourceUrl} target="_blank" rel="noreferrer" className="row" style={{ gap: 4, fontSize: 12 }}><ExternalLink size={13} /> Fiche produit bankofafrica.ma</a>}
          {product.eligibilityRules && Object.keys(product.eligibilityRules).length > 0 && <details><summary className="muted" style={{ cursor: 'pointer', fontSize: 12 }}>Informations publiques à confirmer</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{safeJson(product.eligibilityRules)}</pre></details>}
        </div>
      </Panel>)}</div>
    </section>)}
  </>
}
