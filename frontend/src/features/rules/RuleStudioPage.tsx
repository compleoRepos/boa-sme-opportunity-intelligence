import { Copy, FilePlus2, Search, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { formatDate, label } from '../../api/format'
import { useDuplicateStudioRule, useStudioRules } from '../../api/ruleStudioHooks'
import type { RuleDefinition } from '../../api/types'
import { Badge, Button, EmptyState, ErrorState, Modal, NoResults, Panel, Segmented, SkeletonStack } from '../../ui'
import { LIFECYCLE_LABELS, countConditions } from './ruleModel'

const STATUS_FILTERS = ['ALL', 'DRAFT', 'VALIDATED', 'SIMULATED', 'SUBMITTED', 'APPROVED', 'ACTIVE', 'DISABLED'] as const

export function RuleStudioPage() {
  const navigate = useNavigate()
  const query = useStudioRules({ pageSize: 100, sort: '-updatedAt' })
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>('ALL')
  const [duplicate, setDuplicate] = useState<RuleDefinition>()
  const rules = useMemo(() => (query.data?.data || []).filter((rule) => (status === 'ALL' || rule.status === status || (status === 'ACTIVE' && rule.status === 'PUBLISHED')) && `${rule.name} ${rule.ruleId} ${rule.description || ''}`.toLowerCase().includes(search.toLowerCase())), [query.data, search, status])
  const counts = useMemo(() => (query.data?.data || []).reduce<Record<string, number>>((acc, rule) => { acc[rule.status] = (acc[rule.status] || 0) + 1; return acc }, {}), [query.data])

  return <>
    <header className="page-head"><div><p className="eyebrow accent">Rule Studio</p><h1>Règles métier</h1><p className="subtitle">Concevez, testez, simulez et publiez les règles d’opportunité sans code. Chaque version est auditée ; le moteur n’exécute que les règles publiées.</p></div><div className="page-actions"><Link to="/back-office/regles/nouvelle" className="btn primary"><FilePlus2 size={16} /> Nouvelle règle</Link></div></header>
    <section className="grid cols-4">
      {(['DRAFT', 'SIMULATED', 'SUBMITTED', 'ACTIVE'] as const).map((key) => <button type="button" key={key} className="kpi clickable tone-blue" onClick={() => setStatus(key)} aria-pressed={status === key}><span className="kpi-label">{LIFECYCLE_LABELS[key]}</span><strong className="kpi-value num">{(counts[key] || 0) + (key === 'ACTIVE' ? counts.PUBLISHED || 0 : 0)}</strong><span className="kpi-note">{key === 'DRAFT' ? 'à valider' : key === 'SIMULATED' ? 'prêtes à soumettre' : key === 'SUBMITTED' ? 'en attente d’approbation' : 'exécutées par le moteur'}</span></button>)}
    </section>
    <Panel flush id="rules">
      <header className="panel-head list-head"><div><p className="eyebrow">Catalogue</p><h2>{rules.length} règle(s)</h2></div><div className="panel-tools"><div className="search"><Search size={14} /><input className="input sm" placeholder="Nom, identifiant…" aria-label="Rechercher une règle" value={search} onChange={(event) => setSearch(event.target.value)} /></div></div></header>
      <div className="list-filters"><Segmented value={status} onChange={setStatus} options={STATUS_FILTERS.map((value) => ({ value, label: value === 'ALL' ? 'Toutes' : LIFECYCLE_LABELS[value] || value }))} /></div>
      {query.isPending ? <div className="panel-body"><SkeletonStack rows={3} /></div> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !query.data.data.length ? <EmptyState title="Aucune règle" message="Créez la première règle métier : elle restera un brouillon jusqu’à sa publication." action={<Link to="/back-office/regles/nouvelle" className="btn primary sm">Créer une règle</Link>} /> : !rules.length ? <NoResults /> : <div className="table-wrap"><table className="table hover clickable"><thead><tr><th>Règle</th><th>Opportunité</th><th>Conditions</th><th>Version</th><th>Statut</th><th>Mise à jour</th><th /></tr></thead><tbody>
        {rules.map((rule) => <tr key={rule.ruleId} onClick={() => navigate(`/back-office/regles/${rule.ruleId}`)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') navigate(`/back-office/regles/${rule.ruleId}`) }}>
          <td><strong>{rule.name}</strong><small className="mono">{rule.ruleId}</small></td>
          <td>{label(rule.recommendation?.opportunityType)}</td>
          <td className="num">{countConditions(rule.conditions || [])}</td>
          <td className="num">v{rule.version}</td>
          <td><Badge value={rule.status}>{LIFECYCLE_LABELS[rule.status] || rule.status}</Badge></td>
          <td className="muted">{formatDate(rule.updatedAt)}{rule.updatedBy ? ` · ${rule.updatedBy}` : ''}</td>
          <td><div className="row" style={{ gap: 4, justifyContent: 'flex-end' }} onClick={(event) => event.stopPropagation()}><Link to={`/back-office/regles/${rule.ruleId}/modifier`} className="btn ghost sm" title="Modifier"><SlidersHorizontal size={14} /></Link><Button size="sm" variant="ghost" icon={<Copy size={14} />} onClick={() => setDuplicate(rule)} title="Dupliquer" /></div></td>
        </tr>)}
      </tbody></table></div>}
    </Panel>
    {duplicate && <DuplicateDialog rule={duplicate} onClose={() => setDuplicate(undefined)} />}
  </>
}

function DuplicateDialog({ rule, onClose }: { rule: RuleDefinition; onClose: () => void }) {
  const navigate = useNavigate()
  const mutation = useDuplicateStudioRule(rule.ruleId)
  const [name, setName] = useState(`${rule.name} (variante)`)
  const [reason, setReason] = useState('Nouvelle variante métier')
  const submit = (event: FormEvent) => { event.preventDefault(); mutation.mutate({ name, reason }, { onSuccess: (created) => navigate(`/back-office/regles/${created.ruleId}/modifier`) }) }
  return <Modal title="Dupliquer la règle" onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button variant="primary" type="submit" form="duplicate-form" loading={mutation.isPending} icon={<Copy size={15} />}>Dupliquer</Button></>}>
    <form id="duplicate-form" className="stack" onSubmit={submit}>
      <p className="muted">La copie est créée en brouillon avec sa propre identité et son propre historique d’audit.</p>
      <label className="field">Nom<input className="input" required minLength={3} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label className="field">Motif<textarea className="textarea" required minLength={3} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      {mutation.isError && <p className="form-error">{mutation.error.message}</p>}
    </form>
  </Modal>
}
