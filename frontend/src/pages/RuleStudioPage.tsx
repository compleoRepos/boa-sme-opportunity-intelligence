import { Copy, FilePlus2, GitBranch, History, Search, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { formatDate } from '../api/format'
import { useDuplicateStudioRule, useStudioRules } from '../api/ruleStudioHooks'
import type { RuleDefinition } from '../api/types'
import { Badge, EmptyState, ErrorState, LoadingState, Modal, PageHeader } from '../components/UI'

const statuses = ['ALL', 'DRAFT', 'VALIDATED', 'SIMULATED', 'SUBMITTED', 'APPROVED', 'PUBLISHED', 'ACTIVE', 'DISABLED', 'RETIRED'] as const

function DuplicateDialog({ rule, onClose }: { rule: RuleDefinition; onClose: () => void }) {
  const navigate = useNavigate()
  const duplicate = useDuplicateStudioRule(rule.ruleId)
  const [name, setName] = useState(`${rule.name} — copie`)
  const [reason, setReason] = useState('Nouvelle variante métier')
  return <Modal title="Dupliquer la règle" onClose={onClose}><form className="form-stack" onSubmit={(event) => { event.preventDefault(); duplicate.mutate({ name, reason }, { onSuccess: (created) => navigate(`/rule-studio/${created.ruleId}/modifier`) }) }}>
    <p className="muted">La copie sera créée en brouillon via l’API, avec sa propre identité et son propre historique.</p>
    <label>Nom de la nouvelle règle<input required minLength={3} value={name} onChange={(event) => setName(event.target.value)} /></label>
    <label>Motif de duplication<textarea required minLength={3} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
    {duplicate.isError && <p className="form-error" role="alert">{duplicate.error.message}</p>}
    <footer className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Annuler</button><button className="button primary" type="submit" disabled={duplicate.isPending}><Copy size={16} /> {duplicate.isPending ? 'Duplication…' : 'Dupliquer via API'}</button></footer>
  </form></Modal>
}

export function RuleStudioPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<(typeof statuses)[number]>('ALL')
  const [duplicateRule, setDuplicateRule] = useState<RuleDefinition>()
  const query = useStudioRules({ pageSize: 100, sort: '-updatedAt' })
  const rules = useMemo(() => (query.data?.data || []).filter((rule) => {
    const matchesSearch = `${rule.name} ${rule.ruleId} ${rule.description || ''}`.toLocaleLowerCase('fr-FR').includes(search.toLocaleLowerCase('fr-FR'))
    return matchesSearch && (status === 'ALL' || rule.status === status)
  }), [query.data, search, status])

  return <div className="page rule-studio-page"><PageHeader eyebrow="GOUVERNANCE MÉTIER" title="Rule Studio" description="Concevez, testez et gouvernez les règles d’opportunité sans code ni SQL. Chaque action est exécutée par les APIs et auditée." actions={<Link className="button primary" to="/rule-studio/nouvelle"><FilePlus2 size={17} /> Créer une règle</Link>} />
    <section className="studio-intro"><span><SlidersHorizontal /></span><div><strong>Atelier no-code</strong><p>Métriques, opérateurs, seuils, groupes imbriqués, recommandations et confiance : le métier pilote la configuration, jamais le code source.</p></div><div className="studio-guardrail"><GitBranch /><span>Cycle contrôlé</span><strong>Brouillon → Approbation → Actif</strong></div></section>
    <section className="filter-panel studio-filters"><div className="search-control"><Search size={17} /><input aria-label="Rechercher une règle" placeholder="Nom, identifiant ou description…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><label>Statut<select aria-label="Filtrer par statut" value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>{statuses.map((value) => <option key={value} value={value}>{value === 'ALL' ? 'Tous les statuts' : value}</option>)}</select></label></section>
    {query.isPending ? <LoadingState label="Chargement des règles et versions…" /> : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : !rules.length ? <EmptyState title="Aucune règle" message={query.data.data.length ? 'Aucune règle ne correspond aux filtres.' : 'Le service Rule Management n’a retourné aucune règle. Créez le premier brouillon.'} /> : <section className="studio-rule-list" aria-label="Règles métier">{rules.map((rule) => <article className="studio-rule-card" key={`${rule.ruleId}-${rule.version}`}>
      <header><div><small>{rule.ruleId}</small><h2>{rule.name}</h2></div><Badge value={rule.status} /></header>
      <p>{rule.description || 'Description non fournie par le service.'}</p>
      <div className="rule-summary"><span>Version<strong>v{rule.version}</strong></span><span>Conditions<strong>{rule.conditions?.length ?? 0}</strong></span><span>Opportunité<strong>{rule.recommendation?.opportunityType || '—'}</strong></span><span>Mise à jour<strong>{formatDate(rule.updatedAt)}</strong></span></div>
      <footer><Link className="button secondary" to={`/rule-studio/${rule.ruleId}`}><History size={16} /> Examiner</Link><Link className="button primary" to={`/rule-studio/${rule.ruleId}/modifier`}><SlidersHorizontal size={16} /> Modifier</Link><button className="button ghost" type="button" onClick={() => setDuplicateRule(rule)}><Copy size={16} /> Dupliquer</button></footer>
    </article>)}</section>}
    {duplicateRule && <DuplicateDialog rule={duplicateRule} onClose={() => setDuplicateRule(undefined)} />}
  </div>
}
