import { ArrowLeft, CheckCircle2, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useProducts } from '../../api/hooks'
import { useCreateStudioRule, useStudioRule, useUpdateStudioRule } from '../../api/ruleStudioHooks'
import type { RuleConditionGroup, RuleDefinition, RuleExpression, SaveRuleInput } from '../../api/types'
import { Badge, Button, ErrorState, Panel, SkeletonStack, useToast } from '../../ui'
import { ReadableRule, RecommendationTokens, RuleBuilder } from './RuleBlocks'
import { LIFECYCLE_LABELS, REGIONS, SECTORS, SEGMENTS, isGroup, newCondition } from './ruleModel'

const DEFAULT_LIFECYCLE = {
  validityDays: 90,
  dismissedCooldownDays: 30,
  convertedCooldownDays: 180,
  deferredCooldownDays: 30,
  expiredCooldownDays: 7,
}

const initialDraft = (): SaveRuleInput => ({
  name: '', description: '', scope: { segment: ['SME'], sectors: ['ALL'], regions: ['ALL'] }, logic: 'AND', conditions: [newCondition()],
  recommendation: { opportunityType: 'INVESTMENT_FINANCING', products: [], horizon: '1-3_MONTHS' },
  confidence: { baseScore: 20, weights: {}, highThreshold: 80, mediumThreshold: 60 }, lifecycle: { ...DEFAULT_LIFECYCLE }, reason: '',
})

const fromRule = (rule: RuleDefinition): SaveRuleInput => ({ name: rule.name, description: rule.description || '', scope: rule.scope, logic: rule.logic, conditions: rule.conditions, recommendation: rule.recommendation, confidence: rule.confidence, lifecycle: rule.lifecycle || { ...DEFAULT_LIFECYCLE }, reason: '' })

function weightsFrom(expressions: RuleExpression[], into: Record<string, number> = {}) {
  expressions.forEach((item) => { if (isGroup(item)) weightsFrom(item.conditions, into); else into[item.metric] = item.weight ?? into[item.metric] ?? 0 })
  return into
}

function toggle(items: string[], value: string) {
  if (value === 'ALL') return ['ALL']
  const rest = items.filter((item) => item !== 'ALL')
  return rest.includes(value) ? rest.filter((item) => item !== value) : [...rest, value]
}

export function RuleBuilderPage() {
  const { ruleId } = useParams()
  const editing = Boolean(ruleId)
  const navigate = useNavigate()
  const toast = useToast()
  const existing = useStudioRule(ruleId)
  const products = useProducts({ pageSize: 100, active: true })
  const create = useCreateStudioRule()
  const update = useUpdateStudioRule(ruleId || '')
  const [draft, setDraft] = useState<SaveRuleInput>(initialDraft)
  useEffect(() => { if (existing.data) setDraft(fromRule(existing.data)) }, [existing.data])
  const weights = useMemo(() => weightsFrom(draft.conditions, { ...draft.confidence.weights }), [draft.conditions, draft.confidence.weights])
  const root: RuleConditionGroup = { id: 'root', type: 'GROUP', logic: draft.logic, conditions: draft.conditions }
  const pending = create.isPending || update.isPending

  const save = (event: FormEvent) => {
    event.preventDefault()
    const payload = { ...draft, confidence: { ...draft.confidence, weights } }
    if (editing) update.mutate(payload, { onSuccess: (rule) => { toast.push('success', 'Nouvelle version enregistrée', `${rule.ruleId} · v${rule.version}`); navigate(`/back-office/regles/${rule.ruleId}`) }, onError: (error) => toast.push('error', 'Enregistrement refusé', error.message) })
    else create.mutate(payload, { onSuccess: (rule) => { toast.push('success', 'Brouillon créé', rule.ruleId); navigate(`/back-office/regles/${rule.ruleId}`) }, onError: (error) => toast.push('error', 'Création refusée', error.message) })
  }

  if (editing && existing.isPending) return <SkeletonStack rows={4} kind="block" />
  if (editing && existing.isError) return <ErrorState error={existing.error} onRetry={() => void existing.refetch()} />

  return <form className="stack" style={{ gap: 20 }} onSubmit={save}>
    <Link to={editing ? `/back-office/regles/${ruleId}` : '/back-office/regles'} className="btn ghost sm" style={{ justifySelf: 'start' }}><ArrowLeft size={14} /> Retour</Link>
    <header className="page-head"><div><p className="eyebrow accent">Rule builder</p><h1>{editing ? `Modifier ${existing.data?.name || 'la règle'}` : 'Nouvelle règle métier'}</h1><p className="subtitle">Écrivez la règle comme vous la diriez : SI … ET … ALORS …. Une sauvegarde crée une nouvelle version, sans code ni SQL.</p></div><div className="page-actions">{existing.data && <><Badge value={existing.data.status}>{LIFECYCLE_LABELS[existing.data.status]}</Badge><Badge tone="outline">v{existing.data.version}</Badge></>}<Button type="submit" variant="primary" loading={pending} icon={<Save size={15} />}>{editing ? 'Enregistrer une nouvelle version' : 'Enregistrer le brouillon'}</Button></div></header>

    <div className="grid cols-3 rule-grid">
      <div className="stack span-2" style={{ gap: 20 }}>
        <Panel eyebrow="01 · Identité" title="Définition" id="identity">
          <div className="grid cols-2">
            <label className="field">Nom de la règle<input className="input" required minLength={3} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="PME — potentiel financement d’investissement" /></label>
            <label className="field">Motif de {editing ? 'modification' : 'création'}<input className="input" required={editing} minLength={editing ? 3 : undefined} value={draft.reason || ''} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} placeholder="Pourquoi cette version ? (conservé dans l’audit)" /></label>
            <label className="field" style={{ gridColumn: '1 / -1' }}>Description<textarea className="textarea" rows={2} value={draft.description || ''} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="Intention métier et usage de la règle" /></label>
          </div>
        </Panel>
        <Panel eyebrow="02 · Conditions" title="SI … ET … OU … NON" id="conditions" tools={<span className="muted" style={{ fontSize: 12 }}>Blocs éditables · groupes imbriqués</span>}>
          <RuleBuilder group={root} onChange={(group) => setDraft({ ...draft, logic: group.logic, conditions: group.conditions })} />
        </Panel>
        <Panel eyebrow="03 · Recommandation" title="ALORS" id="then">
          <RecommendationTokens value={draft.recommendation} onChange={(recommendation) => setDraft({ ...draft, recommendation })} products={products.data?.data || []} />
        </Panel>
      </div>
      <div className="stack" style={{ gap: 20 }}>
        <Panel eyebrow="Aperçu" title="Lecture métier" id="preview">
          <ReadableRule conditions={draft.conditions} logic={draft.logic} recommendation={draft.recommendation} products={Object.fromEntries((products.data?.data || []).map((product) => [product.productId, product.name]))} />
        </Panel>
        <Panel eyebrow="04 · Confiance" title="Barème" id="confidence">
          <div className="stack">
            <label className="field">Score de base<input className="input sm" type="number" min={0} max={100} value={draft.confidence.baseScore} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, baseScore: Number(event.target.value) } })} /></label>
            <label className="field">Seuil confiance élevée (%)<input className="input sm" type="number" min={0} max={100} value={draft.confidence.highThreshold ?? 80} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, highThreshold: Number(event.target.value) } })} /></label>
            <label className="field">Seuil confiance moyenne (%)<input className="input sm" type="number" min={0} max={100} value={draft.confidence.mediumThreshold ?? 60} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, mediumThreshold: Number(event.target.value) } })} /></label>
            <p className="muted" style={{ fontSize: 12 }}>Poids des conditions : {Object.entries(weights).map(([metric, weight]) => `${metric.toLowerCase().replaceAll('_', ' ')} ${weight}`).join(' · ') || '—'}. Score final plafonné à 100.</p>
          </div>
        </Panel>
        <Panel eyebrow="05 · Périmètre" title="Population" id="scope">
          <div className="stack">
            <ChipField legend="Segments" options={SEGMENTS} value={draft.scope.segment} onChange={(segment) => setDraft({ ...draft, scope: { ...draft.scope, segment } })} />
            <ChipField legend="Secteurs" options={SECTORS} value={draft.scope.sectors} onChange={(sectors) => setDraft({ ...draft, scope: { ...draft.scope, sectors } })} />
            <ChipField legend="Régions" options={REGIONS} value={draft.scope.regions || ['ALL']} onChange={(regions) => setDraft({ ...draft, scope: { ...draft.scope, regions } })} />
          </div>
        </Panel>
        <Panel eyebrow="06 · Cycle de vie" title="Expiration et refroidissement" id="lifecycle">
          <div className="grid cols-2">
            <LifecycleDays label="Validité" value={draft.lifecycle.validityDays} onChange={(validityDays) => setDraft({ ...draft, lifecycle: { ...draft.lifecycle, validityDays } })} />
            <LifecycleDays label="Après rejet" value={draft.lifecycle.dismissedCooldownDays} onChange={(dismissedCooldownDays) => setDraft({ ...draft, lifecycle: { ...draft.lifecycle, dismissedCooldownDays } })} />
            <LifecycleDays label="Après conversion" value={draft.lifecycle.convertedCooldownDays} onChange={(convertedCooldownDays) => setDraft({ ...draft, lifecycle: { ...draft.lifecycle, convertedCooldownDays } })} max={730} />
            <LifecycleDays label="Après « à revoir »" value={draft.lifecycle.deferredCooldownDays} onChange={(deferredCooldownDays) => setDraft({ ...draft, lifecycle: { ...draft.lifecycle, deferredCooldownDays } })} />
            <LifecycleDays label="Après expiration" value={draft.lifecycle.expiredCooldownDays} onChange={(expiredCooldownDays) => setDraft({ ...draft, lifecycle: { ...draft.lifecycle, expiredCooldownDays } })} max={90} />
          </div>
          <p className="muted" style={{ fontSize: 12 }}>Ces durées sont versionnées avec la règle. Une opportunité terminale n’est pas réémise avant la fin de son délai de refroidissement.</p>
        </Panel>
        <div className="notice info"><ShieldCheck size={16} /><div><strong>Gouvernance</strong>Brouillon → validation → simulation → soumission → approbation (par un autre utilisateur) → publication. Le moteur n’exécute que les versions publiées.</div></div>
        {(create.error || update.error) && <p className="form-error"><CheckCircle2 size={14} /> {(create.error || update.error)?.message}</p>}
      </div>
    </div>
  </form>
}

function LifecycleDays({ label, value, onChange, max = 365 }: { label: string; value: number; onChange: (value: number) => void; max?: number }) {
  return <label className="field">{label}<input className="input sm" type="number" min={1} max={max} required value={value} onChange={(event) => onChange(Number(event.target.value))} /><span className="hint">jours</span></label>
}

function ChipField({ legend, options, value, onChange }: { legend: string; options: string[]; value: string[]; onChange: (value: string[]) => void }) {
  return <fieldset className="chip-field"><legend className="eyebrow">{legend}</legend><div className="row wrap" style={{ gap: 6 }}>{options.map((option) => <label key={option} className={`chip clickable ${value.includes(option) ? 'on' : ''}`}><input type="checkbox" className="sr-only" checked={value.includes(option)} onChange={() => onChange(toggle(value, option))} />{value.includes(option) ? '✓ ' : ''}{option === 'ALL' ? 'Tous' : option.replaceAll('_', ' ')}</label>)}</div></fieldset>
}
