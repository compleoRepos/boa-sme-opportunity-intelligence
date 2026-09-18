import { ArrowLeft, Beaker, CheckCircle2, Play, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useCustomers, useProducts } from '../api/hooks'
import { useCreateStudioRule, useSimulateRule, useStudioRule, useTestRule, useUpdateStudioRule, useValidateRule } from '../api/ruleStudioHooks'
import type { RuleConditionGroup, RuleDefinition, RuleExpression, SaveRuleInput } from '../api/types'
import { ConditionBuilder, isGroup, newCondition } from '../components/rule-studio/ConditionBuilder'
import { RuleTestProof, SimulationPreview } from '../components/rule-studio/RuleInsights'
import { Badge, ErrorState, LoadingState, PageHeader } from '../components/UI'

const opportunities = [['INVESTMENT_FINANCING', 'Financement d’investissement'], ['WORKING_CAPITAL', 'Financement BFR'], ['TRADE_FINANCE', 'Trade finance'], ['CASH_INVESTMENT', 'Placement de trésorerie'], ['FINANCIAL_STRESS_SIGNAL', 'Signal de tension financière']]
const horizons = [['0-1_MONTH', '0–1 mois'], ['1-3_MONTHS', '1–3 mois'], ['3-6_MONTHS', '3–6 mois'], ['6-12_MONTHS', '6–12 mois']]
const sectors = ['ALL', 'AGRICULTURE', 'COMMERCE', 'CONSTRUCTION', 'INDUSTRY', 'SERVICES', 'TRANSPORT']
const regions = ['ALL', 'CASABLANCA_SETTAT', 'RABAT_SALE_KENITRA', 'MARRAKECH_SAFI', 'FES_MEKNES', 'TANGER_TETOUAN_AL_HOCEIMA']

function initialDraft(): SaveRuleInput {
  return {
    name: '', description: '', scope: { segment: ['SME'], sectors: ['ALL'], regions: ['ALL'] },
    logic: 'AND', conditions: [newCondition()],
    recommendation: { opportunityType: 'INVESTMENT_FINANCING', products: [], horizon: '1-3_MONTHS' },
    confidence: { baseScore: 50, weights: { INFLOW_GROWTH: 20 }, highThreshold: 80, mediumThreshold: 60 }, reason: '',
  }
}

function fromRule(rule: RuleDefinition): SaveRuleInput {
  return { name: rule.name, description: rule.description || '', scope: rule.scope, logic: rule.logic, conditions: rule.conditions, recommendation: rule.recommendation, confidence: rule.confidence, reason: '' }
}

function syncWeights(expressions: RuleExpression[], weights: Record<string, number>) {
  const next = { ...weights }
  expressions.forEach((item) => isGroup(item) ? Object.assign(next, syncWeights(item.conditions, next)) : next[item.metric] = item.weight ?? next[item.metric] ?? 0)
  return next
}

function rootGroup(draft: SaveRuleInput): RuleConditionGroup {
  return { id: 'root', type: 'GROUP', logic: draft.logic, conditions: draft.conditions }
}

function toggleItem(items: string[], value: string) {
  if (value === 'ALL') return ['ALL']
  const withoutAll = items.filter((item) => item !== 'ALL')
  return withoutAll.includes(value) ? withoutAll.filter((item) => item !== value) : [...withoutAll, value]
}

function SelectionChips({ legend, options, value, onChange }: { legend: string; options: string[]; value: string[]; onChange: (value: string[]) => void }) {
  return <fieldset className="chip-field"><legend>{legend}</legend><div>{options.map((option) => <label key={option}><input type="checkbox" checked={value.includes(option)} onChange={() => onChange(toggleItem(value, option))} /><span>{option.replaceAll('_', ' ')}</span></label>)}</div></fieldset>
}

function SimulationForm({ onSubmit, pending }: { onSubmit: (from: string, to: string) => void; pending: boolean }) {
  const today = new Date().toISOString().slice(0, 10)
  const previous = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10)
  const [from, setFrom] = useState(previous)
  const [to, setTo] = useState(today)
  return <form className="simulation-form" onSubmit={(event) => { event.preventDefault(); onSubmit(from, to) }}><label>Du<input aria-label="Début de période" required type="date" max={to} value={from} onChange={(event) => setFrom(event.target.value)} /></label><label>Au<input aria-label="Fin de période" required type="date" min={from} value={to} onChange={(event) => setTo(event.target.value)} /></label><button type="submit" className="button primary" disabled={pending}><Play size={16} /> {pending ? 'Simulation en cours…' : 'Lancer la simulation'}</button></form>
}

export function RuleEditorPage() {
  const { ruleId } = useParams()
  const editing = Boolean(ruleId)
  const navigate = useNavigate()
  const ruleQuery = useStudioRule(ruleId)
  const products = useProducts({ pageSize: 100, active: true })
  const customers = useCustomers({ pageSize: 100, segment: 'SME', sort: 'legalName' })
  const [draft, setDraft] = useState<SaveRuleInput>(initialDraft)
  const [savedRule, setSavedRule] = useState<RuleDefinition>()
  const [customerId, setCustomerId] = useState('')
  const create = useCreateStudioRule()
  const update = useUpdateStudioRule(ruleId || '')
  const activeId = savedRule?.ruleId || ruleId || ''
  const validate = useValidateRule(activeId)
  const simulate = useSimulateRule(activeId)
  const testRule = useTestRule(activeId)

  useEffect(() => { if (ruleQuery.data) setDraft(fromRule(ruleQuery.data)) }, [ruleQuery.data])
  useEffect(() => { const first = customers.data?.data[0]?.customerId; if (!customerId && first) setCustomerId(first) }, [customers.data, customerId])

  const selectedProducts = draft.recommendation.products
  const weights = useMemo(() => syncWeights(draft.conditions, draft.confidence.weights), [draft.conditions, draft.confidence.weights])
  const setRecommendation = (value: Partial<SaveRuleInput['recommendation']>) => setDraft((current) => ({ ...current, recommendation: { ...current.recommendation, ...value } }))
  const save = (event: FormEvent) => {
    event.preventDefault()
    const payload = { ...draft, confidence: { ...draft.confidence, weights } }
    if (editing) update.mutate(payload, { onSuccess: (rule) => { setSavedRule(rule); setDraft(fromRule(rule)) } })
    else create.mutate(payload, { onSuccess: (rule) => { setSavedRule(rule); navigate(`/rule-studio/${rule.ruleId}/modifier`, { replace: true }) } })
  }
  const mutationError = create.error || update.error

  if (editing && ruleQuery.isPending) return <div className="page"><LoadingState label="Chargement de la règle…" /></div>
  if (editing && ruleQuery.isError) return <div className="page"><ErrorState error={ruleQuery.error} onRetry={() => void ruleQuery.refetch()} /></div>

  return <div className="page rule-editor-page">
    <Link className="back-link" to={activeId ? `/rule-studio/${activeId}` : '/rule-studio'}><ArrowLeft size={16} /> Retour au Rule Studio</Link>
    <PageHeader eyebrow="RULE BUILDER" title={editing ? `Modifier ${ruleQuery.data?.name || 'la règle'}` : 'Créer une règle'} description="Construisez une logique métier lisible, sans code ni SQL. Une sauvegarde d’édition crée une nouvelle version côté service." actions={ruleQuery.data && <><Badge value={ruleQuery.data.status} /><Badge value={`v${ruleQuery.data.version}`} tone="neutral" /></>} />
    <form className="rule-builder" onSubmit={save}>
      <section className="panel builder-section"><header className="panel-header"><div><p className="eyebrow">01 · IDENTITÉ & PÉRIMÈTRE</p><h2>Définition métier</h2></div></header><div className="builder-grid two"><label>Nom de la règle<input required minLength={3} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="PME — potentiel financement investissement" /></label><label>Motif de versionnement<input required={editing} minLength={editing ? 3 : undefined} value={draft.reason || ''} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} placeholder="Pourquoi cette création ou modification ?" /></label><label className="span-two">Description<textarea rows={3} value={draft.description || ''} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="Intention et usage métier de cette règle" /></label></div><div className="scope-grid"><SelectionChips legend="Segments" options={['SME', 'MICRO_BUSINESS', 'MID_MARKET']} value={draft.scope.segment} onChange={(segment) => setDraft({ ...draft, scope: { ...draft.scope, segment } })} /><SelectionChips legend="Secteurs" options={sectors} value={draft.scope.sectors} onChange={(nextSectors) => setDraft({ ...draft, scope: { ...draft.scope, sectors: nextSectors } })} /><SelectionChips legend="Régions" options={regions} value={draft.scope.regions || []} onChange={(nextRegions) => setDraft({ ...draft, scope: { ...draft.scope, regions: nextRegions } })} /></div></section>
      <section className="panel builder-section"><header className="panel-header"><div><p className="eyebrow">02 · WHEN</p><h2>Conditions et logique</h2></div><span>Groupes ET / OU / NON imbriqués</span></header><ConditionBuilder group={rootGroup(draft)} onChange={(group) => setDraft({ ...draft, logic: group.logic, conditions: group.conditions })} /></section>
      <section className="panel builder-section"><header className="panel-header"><div><p className="eyebrow">03 · THEN</p><h2>Opportunité recommandée</h2></div></header><div className="builder-grid three"><label>Opportunité<select value={draft.recommendation.opportunityType} onChange={(event) => setRecommendation({ opportunityType: event.target.value })}>{opportunities.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label><label>Horizon<select value={draft.recommendation.horizon} onChange={(event) => setRecommendation({ horizon: event.target.value })}>{horizons.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label><label>Score de base<input type="number" min="0" max="100" value={draft.confidence.baseScore} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, baseScore: Number(event.target.value) } })} /></label></div><fieldset className="product-selector"><legend>Produits du catalogue</legend>{products.isPending ? <span className="muted">Chargement du catalogue via API…</span> : products.isError ? <p className="form-error" role="alert">{products.error.message}</p> : !products.data.data.length ? <p className="muted">Aucun produit actif renvoyé par le catalogue.</p> : <div>{products.data.data.map((product) => <label key={product.productId}><input type="checkbox" checked={selectedProducts.includes(product.productId)} onChange={() => setRecommendation({ products: selectedProducts.includes(product.productId) ? selectedProducts.filter((id) => id !== product.productId) : [...selectedProducts, product.productId] })} /><span><strong>{product.name}</strong><small>{product.category}</small></span></label>)}</div>}</fieldset></section>
      <section className="panel builder-section"><header className="panel-header"><div><p className="eyebrow">04 · CONFIANCE</p><h2>Configuration du scoring</h2></div><span>Score final plafonné à 100</span></header><div className="builder-grid three"><label>Score de base<input type="number" min="0" max="100" value={draft.confidence.baseScore} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, baseScore: Number(event.target.value) } })} /></label><label>Seuil confiance élevée<input type="number" min="0" max="100" value={draft.confidence.highThreshold ?? 80} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, highThreshold: Number(event.target.value) } })} /></label><label>Seuil confiance moyenne<input type="number" min="0" max="100" value={draft.confidence.mediumThreshold ?? 60} onChange={(event) => setDraft({ ...draft, confidence: { ...draft.confidence, mediumThreshold: Number(event.target.value) } })} /></label></div></section>
      {mutationError && <p className="form-error builder-error" role="alert">{mutationError.message}</p>}
      <div className="builder-savebar"><div><ShieldCheck /><span>Aucun code ni SQL</span><strong>Configuration structurée et versionnée</strong></div><button className="button primary" type="submit" disabled={create.isPending || update.isPending}><Save size={17} /> {create.isPending || update.isPending ? 'Sauvegarde…' : editing ? 'Sauvegarder une nouvelle version' : 'Enregistrer le brouillon'}</button></div>
    </form>

    {activeId && <><section className="panel validation-panel"><header className="panel-header"><div><p className="eyebrow">05 · CONTRÔLE</p><h2>Validation de la configuration</h2></div><button className="button secondary" type="button" disabled={validate.isPending} onClick={() => validate.mutate()}><CheckCircle2 size={16} /> {validate.isPending ? 'Validation…' : 'Valider via API'}</button></header>{validate.isError && <p className="form-error" role="alert">{validate.error.message}</p>}{validate.data && <div className={validate.data.valid ? 'validation-result valid' : 'validation-result invalid'}><strong>{validate.data.valid ? 'Configuration valide' : 'Configuration invalide'}</strong>{validate.data.errors?.map((error, index) => <p key={index}>{error.path ? `${error.path} : ` : ''}{error.message}</p>)}{validate.data.warnings?.map((warning, index) => <p key={index}>Attention : {warning.message}</p>)}</div>}</section>
      <section className="panel simulation-panel"><header className="panel-header"><div><p className="eyebrow">06 · SIMULATION & PREVIEW</p><h2>Tester sur l’historique</h2></div><Badge value="DONNÉES API" tone="info" /></header><SimulationForm pending={simulate.isPending} onSubmit={(from, to) => simulate.mutate({ period: { from, to }, population: { segment: draft.scope.segment[0] || 'SME', sectors: draft.scope.sectors, regions: draft.scope.regions } })} />{simulate.isError && <ErrorState error={simulate.error} />}</section><SimulationPreview result={simulate.data} />
      <section className="panel rule-tester"><header className="panel-header"><div><p className="eyebrow">07 · RULE TESTER</p><h2>Preuve sur une PME</h2></div><Beaker /></header><div className="tester-control"><label>PME à évaluer<select aria-label="PME à évaluer" value={customerId} onChange={(event) => setCustomerId(event.target.value)} disabled={customers.isPending || customers.isError}>{customers.data?.data.map((customer) => <option key={customer.customerId} value={customer.customerId}>{customer.legalName} · {customer.customerId}</option>)}</select></label><button className="button primary" type="button" disabled={!customerId || testRule.isPending} onClick={() => testRule.mutate(customerId)}><Beaker size={16} /> {testRule.isPending ? 'Évaluation…' : 'Tester la règle'}</button></div>{customers.isError && <p className="form-error" role="alert">{customers.error.message}</p>}{testRule.isError && <ErrorState error={testRule.error} />}</section><RuleTestProof result={testRule.data} /></>}
  </div>
}
