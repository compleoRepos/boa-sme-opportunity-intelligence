import { Activity, BriefcaseBusiness, Cpu, Database, FlaskConical, GitBranch, History, Languages, Mail, PackageSearch, RotateCcw, Send, Settings2, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { formatDate, formatNumber, formatPercent, label, safeJson } from '../../api/format'
import { useActions, useActiveModel, useDashboard, useEngine, useGenerateDigests, useLabelCatalog, useMlModels, useNotifications, useNotificationSubscriptions, useProducts, useRules, useUpdateDigestSubscription, useUpdateLabel, useUpdateRule } from '../../api/hooks'
import { useRuleAudit, useRuleSimulations, useStudioRules } from '../../api/ruleStudioHooks'
import type { LabelCatalogEntry, MlModel, NotificationDigestSubscription, RuleConfig, RuleLifecyclePolicy, RuleParameter } from '../../api/types'
import { BreakdownBars } from '../../charts/BreakdownBars'
import { CHART, OPPORTUNITY_COLORS, PRIORITY_COLORS } from '../../charts/theme'
import { Badge, Button, EmptyState, ErrorState, Kpi, Modal, Panel, SkeletonStack, Tabs, useToast } from '../../ui'
import { LIFECYCLE_LABELS } from '../rules/ruleModel'
import { SimulationResults } from '../rules/SimulationPanel'

/* ------------------------------------------------------------------ Accueil */
export function BackOfficeHomePage() {
  const rules = useStudioRules({ pageSize: 100 })
  const engine = useEngine()
  const model = useActiveModel()
  const dashboard = useDashboard()
  const products = useProducts({ pageSize: 100, active: true })
  const byStatus = useMemo(() => (rules.data?.data || []).reduce<Record<string, number>>((acc, rule) => { acc[rule.status] = (acc[rule.status] || 0) + 1; return acc }, {}), [rules.data])
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Back office métier</p><h1>Gouvernance du moteur d’opportunités</h1><p className="subtitle">Règles, seuils, produits, modèles ML, simulations et audit : tout ce qui alimente les dashboards CC et agence, versionné et traçable.</p></div></header>
    <section className="grid cols-4">
      <Kpi label="Règles Rule Studio" value={rules.data?.data.length ?? 0} tone="blue" icon={<GitBranch size={20} />} note={`${(byStatus.ACTIVE || 0) + (byStatus.PUBLISHED || 0)} publiées · ${byStatus.DRAFT || 0} brouillons`} onClick={() => void 0} />
      <Kpi label="Opportunités ouvertes" value={dashboard.data?.totalOpportunities ?? 0} tone="navy" icon={<BriefcaseBusiness size={20} />} note={`${formatNumber(dashboard.data?.highConfidenceOpportunities)} en confiance élevée`} />
      <Kpi label="Moteur de règles" value={engine.data?.engineVersion || '—'} tone="green" icon={<Settings2 size={20} />} note={`Jeu de règles ${engine.data?.activeRuleVersion || engine.data?.ruleVersion || '—'} · ${label(engine.data?.status)}`} />
      <Kpi label="Modèle ML actif" value={model.data ? model.data.modelVersion.replace('sales-propensity-', '') : '—'} tone="violet" icon={<Cpu size={20} />} note={model.data ? `${model.data.deploymentMode} · seuil ${formatPercent(model.data.threshold, 0)}` : 'Aucun modèle actif'} />
    </section>
    <section className="grid cols-3">
      {[
        { to: '/back-office/regles', icon: GitBranch, title: 'Rule Studio', text: 'Créer, simuler, approuver et publier les règles sans code.' },
        { to: '/back-office/opportunites', icon: BriefcaseBusiness, title: 'Opportunités', text: 'Pipeline global filtrable, toutes agences.' },
        { to: '/back-office/produits', icon: PackageSearch, title: 'Produits', text: 'Catalogue de référence et éligibilités.' },
        { to: '/back-office/seuils', icon: SlidersHorizontal, title: 'Seuils moteur', text: 'Configuration versionnée des règles déterministes.' },
        { to: '/back-office/modeles', icon: Cpu, title: 'ML Governance', text: 'Registre des modèles, métriques, versions.' },
        { to: '/back-office/simulations', icon: FlaskConical, title: 'Simulations', text: 'Historique des simulations et impacts estimés.' },
        { to: '/back-office/audit', icon: ShieldCheck, title: 'Audit', text: 'Journal des règles et des actions commerciales.' },
        { to: '/back-office/libelles', icon: Languages, title: 'Libellés', text: 'Terminologie française versionnée sans modifier les codes métier.' },
        { to: '/back-office/notifications', icon: Mail, title: 'Notifications', text: 'Synthèses quotidiennes, SMTP, retries et suivi de livraison.' },
      ].map((card) => <Link key={card.to} to={card.to} className="panel interactive bo-card"><span className="kpi-icon"><card.icon size={20} /></span><div><strong>{card.title}</strong><span className="muted">{card.text}</span></div></Link>)}
    </section>
    <section className="grid cols-2">
      <Panel eyebrow="Pipeline" title="Opportunités par type (toutes agences)" id="bo-type"><BreakdownBars items={(dashboard.data?.opportunitiesByType || []).map((item) => ({ count: item.count, opportunityType: item.opportunityType || item.type }))} nameKey="opportunityType" colorFor={(name) => OPPORTUNITY_COLORS[name] || CHART.blue} /></Panel>
      <Panel eyebrow="Pipeline" title="Opportunités par priorité" id="bo-priority"><BreakdownBars items={(dashboard.data?.opportunitiesByPriority || []).map((item) => ({ count: item.count, priorityLevel: item.priorityLevel || item.priority }))} nameKey="priorityLevel" colorFor={(name) => PRIORITY_COLORS[name] || CHART.blue} /><p className="faint" style={{ fontSize: 11, marginTop: 8 }}>{formatNumber(products.data?.data.length)} produits actifs au catalogue · contact {formatPercent(dashboard.data?.contactRate, 1)} · conversion {formatPercent(dashboard.data?.conversionRate, 1)}</p></Panel>
    </section>
  </>
}

/* ------------------------------------------------------------------ Seuils moteur (admin rules) */
export function EngineThresholdsPage() {
  const rules = useRules()
  const engine = useEngine()
  const [editing, setEditing] = useState<RuleConfig>()
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Seuils moteur</p><h1>Configuration déterministe</h1><p className="subtitle">Jeu de règles {engine.data?.activeRuleVersion || '—'} · moteur {engine.data?.engineVersion || '—'} · dernière exécution {formatDate(engine.data?.lastRunAt, true)}. Toute modification crée une nouvelle version justifiée.</p></div></header>
    {rules.isPending ? <SkeletonStack rows={3} /> : rules.isError ? <ErrorState error={rules.error} onRetry={() => void rules.refetch()} /> : <div className="grid cols-2">{rules.data.data.map((rule) => { const params = rule.parameters as Record<string, unknown>; const conditions = (params?.all_conditions as Array<{ key: string; operator: string; value: unknown; label?: string }> | undefined) || []; return <Panel key={rule.ruleId} eyebrow={label(rule.opportunityType)} title={rule.name || label(rule.opportunityType)} id={`rule-${rule.ruleId}`} tools={<div className="row" style={{ gap: 6 }}><Badge value={rule.enabled ? 'ACTIVE' : 'INACTIVE'} /><Badge tone="outline">v{rule.version || rule.ruleVersion}</Badge></div>}>
      <div className="stack">
        {conditions.length ? <ul className="threshold-list">{conditions.map((condition) => <li key={condition.key}><span>{condition.label || label(condition.key)}</span><b className="num">{condition.operator} {typeof condition.value === 'number' && Math.abs(condition.value) <= 1 && !condition.key.includes('period') ? formatPercent(condition.value, 0) : String(condition.value)}</b></li>)}</ul> : <details><summary className="muted" style={{ cursor: 'pointer', fontSize: 12 }}>Paramètres</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{safeJson(rule.parameters)}</pre></details>}
        <LifecyclePolicySummary policy={rule.lifecyclePolicy} />
        <div className="row between"><span className="muted" style={{ fontSize: 12 }}>Horizon {label(String(params?.horizon || '—'))} · modifiée {formatDate(rule.updatedAt)}</span><Button size="sm" onClick={() => setEditing(rule)} icon={<SlidersHorizontal size={14} />}>Modifier</Button></div>
      </div>
    </Panel> })}</div>}
    {editing && <ThresholdEditor rule={editing} onClose={() => setEditing(undefined)} />}
  </>
}

function LifecyclePolicySummary({ policy }: { policy?: RuleLifecyclePolicy }) {
  if (!policy) return null
  return <div className="notice neutral"><History size={15} /><div><strong>Cycle de vie</strong>Validité {policy.validityDays} j · rejet {policy.dismissedCooldownDays} j · conversion {policy.convertedCooldownDays} j · à revoir {policy.deferredCooldownDays} j · expiration {policy.expiredCooldownDays} j.</div></div>
}

function ThresholdEditor({ rule, onClose }: { rule: RuleConfig; onClose: () => void }) {
  const toast = useToast()
  const mutation = useUpdateRule(rule.ruleId)
  const initial = Array.isArray(rule.parameters) ? rule.parameters : Object.entries(rule.parameters || {}).filter(([, value]) => ['number', 'boolean', 'string'].includes(typeof value)).map(([key, value]) => ({ key, value: value as string | number | boolean }))
  const [enabled, setEnabled] = useState(rule.enabled)
  const [parameters, setParameters] = useState<RuleParameter[]>(initial)
  const [justification, setJustification] = useState('')
  const submit = (event: FormEvent) => { event.preventDefault(); mutation.mutate({ enabled, parameters: Object.fromEntries(parameters.map((parameter) => [parameter.key, parameter.value])), justification }, { onSuccess: () => { toast.push('success', 'Nouvelle version créée', rule.name || rule.ruleId); onClose() }, onError: (error) => toast.push('error', 'Modification refusée', error.message) }) }
  return <Modal title={`Modifier ${rule.name || label(rule.opportunityType)}`} onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button variant="primary" type="submit" form="threshold-form" loading={mutation.isPending}>Créer une nouvelle version</Button></>}>
    <form id="threshold-form" className="stack" onSubmit={submit}>
      <label className="checkbox"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Règle active</label>
      <div className="grid cols-2">{parameters.map((parameter, index) => <label className="field" key={parameter.key}>{parameter.label || label(parameter.key)}{typeof parameter.value === 'boolean' ? <select className="select sm" value={String(parameter.value)} onChange={(event) => setParameters((items) => items.map((item, i) => (i === index ? { ...item, value: event.target.value === 'true' } : item)))}><option value="true">Oui</option><option value="false">Non</option></select> : <input className="input sm" type={typeof parameter.value === 'number' ? 'number' : 'text'} step="any" value={String(parameter.value)} onChange={(event) => setParameters((items) => items.map((item, i) => (i === index ? { ...item, value: typeof item.value === 'number' ? Number(event.target.value) : event.target.value } : item)))} />}<span className="hint mono">{parameter.key}</span></label>)}</div>
      <label className="field">Justification<textarea className="textarea" required rows={2} value={justification} onChange={(event) => setJustification(event.target.value)} placeholder="Motif métier ou de gouvernance (audité)" /></label>
    </form>
  </Modal>
}

/* ------------------------------------------------------------------ ML Governance */
export function ModelsPage() {
  const models = useMlModels()
  const [selected, setSelected] = useState<string>()
  const toast = useToast()
  const list = models.data?.data || []
  const active = list.find((model) => model.status === 'ACTIVE')
  const current: MlModel | undefined = list.find((model) => model.modelVersion === selected) || active
  const metrics = current ? Object.entries(current.validationMetrics || {}) : []
  return <>
    <header className="page-head" data-demo="models"><div><p className="eyebrow accent">ML Governance</p><h1>Model Registry</h1><p className="subtitle">Modèle de propension commerciale (régression logistique CPU, POC assistif). Aucune décision de crédit, aucun entraînement automatique.</p></div></header>
    {models.isPending ? <SkeletonStack rows={3} /> : models.isError ? <ErrorState error={models.error} onRetry={() => void models.refetch()} /> : !list.length ? <EmptyState title="Aucun modèle enregistré" /> : <div className="grid cols-3 rule-grid">
      <Panel eyebrow="Registre" title={`${list.length} version(s)`} id="registry" flush>
        <ul className="model-list">{list.map((model) => <li key={model.modelVersion}><button type="button" className={current?.modelVersion === model.modelVersion ? 'active' : ''} onClick={() => setSelected(model.modelVersion)}><strong>{model.modelVersion}</strong><span className="row" style={{ gap: 6 }}><Badge value={model.status} /><small className="muted">{model.featureSetVersion}</small></span></button></li>)}</ul>
      </Panel>
      {current && <div className="stack span-2" style={{ gap: 20 }}>
        <Panel eyebrow={current.scoreType} title={<span className="row" style={{ gap: 8 }}>{current.modelVersion} <Badge value={current.status} /></span>} id="model" tools={<div className="row" style={{ gap: 6 }}><Button size="sm" icon={<History size={14} />} onClick={() => setSelected(undefined)}>Historique</Button><Button size="sm" variant="danger" icon={<RotateCcw size={14} />} onClick={() => toast.push('info', 'Rollback non exposé', 'Le ML engine ne publie pas d’endpoint de bascule de version dans ce MVP : l’opération se fait par le registre (statut ACTIVE unique).')}>Rollback</Button></div>}>
          <div className="grid cols-4">
            <div className="stat"><span className="stat-label">Algorithme</span><span className="stat-value sm">{label(current.algorithm)}</span></div>
            <div className="stat"><span className="stat-label">Seuil de décision</span><span className="stat-value sm num">{formatPercent(current.threshold, 0)}</span></div>
            <div className="stat"><span className="stat-label">Mode</span><span className="stat-value sm">{current.deploymentMode}</span></div>
            <div className="stat"><span className="stat-label">Features</span><span className="stat-value sm">{current.featureSetVersion}</span><span className="stat-note">{current.featureOrder.length} variables</span></div>
          </div>
          <div className="divider" style={{ margin: '16px 0' }} />
          <div className="grid cols-2">
            <div className="stack"><p className="eyebrow">Métriques de validation</p>{metrics.length ? <ul className="metric-list">{metrics.map(([key, value]) => <li key={key}><span>{label(key)}</span><strong>{typeof value === 'number' ? (value <= 1 ? formatPercent(value, 1) : formatNumber(value, 3)) : typeof value === 'boolean' ? (value ? 'oui' : 'non') : typeof value === 'object' ? safeJson(value) : label(String(value))}</strong></li>)}</ul> : <p className="faint">Aucune métrique publiée.</p>}<div className="notice"><ShieldCheck size={16} /><div><strong>Aucune performance de production revendiquée</strong>Dataset {current.trainingDatasetVersion} · code {current.trainingCodeVersion}. Les métriques @K (precision, recall, PR-AUC) seront publiées après une évaluation sur labels d’outcome réels.</div></div></div>
            <div className="stack"><p className="eyebrow">Coefficients (contribution par feature)</p><ul className="coef-list">{Object.entries(current.coefficients).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([feature, coefficient]) => { const peak = Math.max(...Object.values(current.coefficients).map(Math.abs), 0.01); return <li key={feature}><span className="breakdown-label" title={label(feature)}>{label(feature)}</span><span className="breakdown-track"><i style={{ width: `${Math.max(3, (Math.abs(coefficient) / peak) * 100)}%`, background: coefficient >= 0 ? CHART.violet : CHART.red }} /></span><b className="num">{coefficient >= 0 ? '+' : ''}{formatNumber(coefficient, 2)}</b></li> })}</ul><p className="faint" style={{ fontSize: 11 }}>Intercept {formatNumber(current.intercept, 2)} · ordre des features imposé par le registre (checksum vérifié au scoring).</p></div>
          </div>
        </Panel>
        <Panel eyebrow="Traçabilité" title="Cycle de vie" id="model-lifecycle"><dl className="kv"><dt>Enregistré</dt><dd>{formatDate(current.createdAt, true)}</dd><dt>Mis à jour</dt><dd>{formatDate(current.updatedAt, true)}</dd><dt>Entraînement auto</dt><dd>{current.automaticTraining ? 'oui' : 'non'}</dd><dt>Score</dt><dd>{current.scoreType} · combiné aux règles publiées (35 % / 65 %)</dd></dl></Panel>
      </div>}
    </div>}
  </>
}

/* ------------------------------------------------------------------ Simulations */
export function SimulationsPage() {
  const rules = useStudioRules({ pageSize: 100 })
  const [ruleId, setRuleId] = useState<string>()
  const navigate = useNavigate()
  const current = ruleId || rules.data?.data[0]?.ruleId
  const simulations = useRuleSimulations(current)
  const [index, setIndex] = useState(0)
  const entries = simulations.data?.simulations || []
  const selected = entries[index]
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Simulations</p><h1>Historique des simulations</h1><p className="subtitle">Chaque simulation est persistée avec sa période, sa population et son résultat. Rien n’est recalculé côté navigateur.</p></div><div className="page-actions"><select className="select" aria-label="Règle" value={current || ''} onChange={(event) => { setRuleId(event.target.value); setIndex(0) }}>{rules.data?.data.map((rule) => <option key={rule.ruleId} value={rule.ruleId}>{rule.name} · v{rule.version}</option>)}</select>{current && <Button onClick={() => navigate(`/back-office/regles/${current}`)} icon={<GitBranch size={14} />}>Ouvrir la règle</Button>}</div></header>
    {simulations.isPending ? <SkeletonStack rows={3} /> : simulations.isError ? <ErrorState error={simulations.error} compact /> : !entries.length ? <EmptyState icon={<FlaskConical />} title="Aucune simulation enregistrée" message="Lancez une simulation depuis la règle (statut validée) pour mesurer son impact." action={current ? <Link className="btn primary sm" to={`/back-office/regles/${current}`}>Aller à la règle</Link> : undefined} /> : <>
      <Tabs pill value={String(index)} onChange={(id) => setIndex(Number(id))} items={entries.map((entry, position) => ({ id: String(position), label: `${formatDate(entry.createdAt, true)} · v${entry.ruleVersion ?? '—'}` }))} />
      {selected && <SimulationResults result={selected} />}
    </>}
  </>
}

/* ------------------------------------------------------------------ Audit */
export function AuditPage() {
  const rules = useStudioRules({ pageSize: 100 })
  const [ruleId, setRuleId] = useState<string>()
  const current = ruleId || rules.data?.data[0]?.ruleId
  const audit = useRuleAudit(current)
  const actions = useActions({ pageSize: 50, sort: '-createdAt' })
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Audit</p><h1>Traçabilité</h1><p className="subtitle">Journal des règles (qui, quand, quoi, pourquoi) et des actions commerciales enregistrées par les CC.</p></div></header>
    <div className="grid cols-2">
      <Panel eyebrow="Règles" title="Journal d’audit Rule Studio" id="audit-rules" tools={<select className="select sm" aria-label="Règle" value={current || ''} onChange={(event) => setRuleId(event.target.value)}>{rules.data?.data.map((rule) => <option key={rule.ruleId} value={rule.ruleId}>{rule.name}</option>)}</select>}>
        {audit.isPending ? <SkeletonStack rows={3} kind="text" /> : audit.isError ? <ErrorState error={audit.error} compact /> : !audit.data?.data.length ? <EmptyState compact title="Aucune entrée" /> : <div className="timeline">{audit.data.data.map((entry) => <article key={entry.id}><strong><Badge value={entry.action} /> version {entry.ruleVersion}</strong><small>{formatDate(entry.timestamp, true)} · {entry.userId}</small>{entry.reason && <p>{entry.reason}</p>}</article>)}</div>}
      </Panel>
      <Panel eyebrow="Actions commerciales" title="Dernières actions enregistrées" id="audit-actions" tools={<Link to="/actions" className="btn ghost sm"><Activity size={14} /> Tout voir</Link>}>
        {actions.isPending ? <SkeletonStack rows={3} kind="text" /> : actions.isError ? <ErrorState error={actions.error} compact /> : !actions.data?.data.length ? <EmptyState compact title="Aucune action" message="Les actions des CC apparaîtront ici avec leur auteur et leur résultat." /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Action</th><th>Client</th><th>Auteur</th><th>Résultat</th><th>Date</th></tr></thead><tbody>{actions.data.data.map((action) => <tr key={action.actionId}><td><strong>{label(action.actionType)}</strong><small className="mono">{action.actionId.slice(0, 8)}</small></td><td><Link to={`/clients/${action.customerId}`}>{action.customerId}</Link></td><td className="muted">{action.assignedTo || action.createdBy || '—'}</td><td>{action.outcome ? <Badge value={action.outcome} /> : <Badge value={action.status} />}</td><td className="muted">{formatDate(action.createdAt, true)}</td></tr>)}</tbody></table></div>}
      </Panel>
    </div>
    <div className="notice neutral"><Database size={16} /><div><strong>Persisté côté services</strong>Audit des règles : rule-management-service · actions et outcomes : action-service · décisions moteur : opportunity-service (versions moteur et règle sur chaque opportunité). {rules.data ? `${rules.data.data.length} règle(s) · statuts ${rules.data.data.map((rule) => LIFECYCLE_LABELS[rule.status] || rule.status).join(', ')}` : ''}</div></div>
  </>
}

/* ------------------------------------------------------------------ Libellés */
export function LabelsPage() {
  const catalog = useLabelCatalog(true)
  const [editing, setEditing] = useState<LabelCatalogEntry>()
  const entries = catalog.data?.data || []
  const namespaces = useMemo(() => [...new Set(entries.map((entry) => entry.namespace))], [entries])
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Terminologie</p><h1>Libellés fonctionnels</h1><p className="subtitle">Le code technique reste stable. Chaque changement de texte français crée une version justifiée et immuable.</p></div></header>
    {catalog.isPending ? <SkeletonStack rows={5} /> : catalog.isError ? <ErrorState error={catalog.error} onRetry={() => void catalog.refetch()} /> : <div className="stack">{namespaces.map((namespace) => <Panel key={namespace} eyebrow="Catalogue français" title={namespace} id={`labels-${namespace.toLowerCase()}`} flush><div className="table-wrap"><table className="table hover"><thead><tr><th>Code stable</th><th>Libellé affiché</th><th>Version</th><th>État</th><th>Action</th></tr></thead><tbody>{entries.filter((entry) => entry.namespace === namespace).map((entry) => <tr key={`${entry.namespace}-${entry.code}`}><td className="mono">{entry.code}</td><td><strong>{entry.label}</strong><small>{entry.justification}</small></td><td className="num">v{entry.version}</td><td><Badge value={entry.active ? 'ACTIVE' : 'INACTIVE'} /></td><td><Button size="sm" onClick={() => setEditing(entry)}>Modifier</Button></td></tr>)}</tbody></table></div></Panel>)}</div>}
    {editing && <LabelEditor entry={editing} onClose={() => setEditing(undefined)} />}
  </>
}

function LabelEditor({ entry, onClose }: { entry: LabelCatalogEntry; onClose: () => void }) {
  const mutation = useUpdateLabel(entry.namespace, entry.code)
  const toast = useToast()
  const [value, setValue] = useState(entry.label)
  const [active, setActive] = useState(entry.active)
  const [justification, setJustification] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({ label: value, active, expectedVersion: entry.version, justification }, {
      onSuccess: (updated) => { toast.push('success', 'Libellé versionné', `${updated.code} · v${updated.version}`); onClose() },
      onError: (error) => toast.push('error', 'Modification refusée', error.message),
    })
  }
  return <Modal title={`Modifier ${entry.code}`} onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button variant="primary" type="submit" form="label-form" loading={mutation.isPending}>Créer la version</Button></>}>
    <form id="label-form" className="stack" onSubmit={submit}>
      <div className="notice neutral"><Languages size={16} /><div><strong>Code immuable</strong><span className="mono">{entry.namespace}.{entry.code}</span></div></div>
      <label className="field">Libellé français<input className="input" required maxLength={180} value={value} onChange={(event) => setValue(event.target.value)} /></label>
      <label className="checkbox"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Libellé actif</label>
      <label className="field">Justification<textarea className="textarea" required minLength={8} maxLength={1000} rows={3} value={justification} onChange={(event) => setJustification(event.target.value)} placeholder="Motif métier auditable" /></label>
    </form>
  </Modal>
}


/* ------------------------------------------------------------------ Notifications */
export function NotificationsPage() {
  const subscriptions = useNotificationSubscriptions()
  const deliveries = useNotifications()
  const generate = useGenerateDigests()
  const toast = useToast()
  const [editing, setEditing] = useState<NotificationDigestSubscription>()
  const run = () => generate.mutate(undefined, {
    onSuccess: (result) => toast.push('success', 'Synthèses traitées', `${result.created} créée(s) · ${result.sent} envoyée(s) · ${result.skipped} ignorée(s)`),
    onError: (error) => toast.push('error', 'Génération refusée', error.message),
  })
  return <>
    <header className="page-head"><div><p className="eyebrow accent">Communication commerciale</p><h1>Notifications email</h1><p className="subtitle">Une synthèse quotidienne agrégée par CC, livrée via un relais SMTP configurable. Aucun détail financier ni décision de crédit n’est envoyé par email.</p></div><Button variant="primary" icon={<Send size={15} />} loading={generate.isPending} onClick={run}>Générer maintenant</Button></header>
    <div className="grid cols-2">
      <Panel eyebrow="Planification" title="Synthèses quotidiennes" id="digest-subscriptions" flush>
        {subscriptions.isPending ? <SkeletonStack rows={3} /> : subscriptions.isError ? <ErrorState error={subscriptions.error} onRetry={() => void subscriptions.refetch()} /> : !subscriptions.data?.data.length ? <EmptyState compact title="Aucun abonnement" message="Créez un abonnement par CC pour activer la synthèse quotidienne." /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>CC</th><th>Destinataire</th><th>Heure</th><th>État</th><th /></tr></thead><tbody>{subscriptions.data.data.map((item) => <tr key={item.relationshipManagerId}><td className="mono">{item.relationshipManagerId}</td><td>{item.recipientEmail}<small>{item.timezone}</small></td><td className="num">{String(item.deliveryHour).padStart(2, '0')}:00</td><td><Badge value={item.enabled ? 'ACTIVE' : 'INACTIVE'} /></td><td><Button size="sm" onClick={() => setEditing(item)}>Modifier</Button></td></tr>)}</tbody></table></div>}
        <div style={{ padding: 16 }}><Button onClick={() => setEditing({ relationshipManagerId: '', recipientEmail: '', timezone: 'Africa/Abidjan', deliveryHour: 7, enabled: true, updatedAt: '' })}>Ajouter un CC</Button></div>
      </Panel>
      <Panel eyebrow="Traçabilité" title="Dernières livraisons" id="notification-deliveries" flush>
        {deliveries.isPending ? <SkeletonStack rows={4} /> : deliveries.isError ? <ErrorState error={deliveries.error} onRetry={() => void deliveries.refetch()} /> : !deliveries.data?.data.length ? <EmptyState compact title="Aucun email" message="Les livraisons et retries apparaîtront ici." /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Type</th><th>Destinataire</th><th>État</th><th>Tentatives</th><th>Date</th></tr></thead><tbody>{deliveries.data.data.map((item) => <tr key={item.notificationId}><td>{item.type === 'PORTFOLIO_DAILY_DIGEST' ? 'Synthèse quotidienne' : 'Rappel d’action'}</td><td>{item.recipient}</td><td><Badge value={item.status} /></td><td className="num">{item.attemptCount}/{item.maxAttempts}</td><td className="muted">{formatDate(item.sentAt || item.createdAt, true)}</td></tr>)}</tbody></table></div>}
      </Panel>
    </div>
    <div className="notice neutral"><ShieldCheck size={16} /><div><strong>Garde-fous</strong>Déduplication par CC et date, Message-ID stable, retry exponentiel, dead-letter après cinq échecs et historique de livraison append-only.</div></div>
    {editing && <DigestSubscriptionEditor entry={editing} onClose={() => setEditing(undefined)} />}
  </>
}

function DigestSubscriptionEditor({ entry, onClose }: { entry: NotificationDigestSubscription; onClose: () => void }) {
  const toast = useToast()
  const [relationshipManagerId, setRelationshipManagerId] = useState(entry.relationshipManagerId)
  const [recipientEmail, setRecipientEmail] = useState(entry.recipientEmail)
  const [timezone, setTimezone] = useState(entry.timezone)
  const [deliveryHour, setDeliveryHour] = useState(entry.deliveryHour)
  const [enabled, setEnabled] = useState(entry.enabled)
  const mutation = useUpdateDigestSubscription(relationshipManagerId)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({ recipientEmail, timezone, deliveryHour, enabled }, {
      onSuccess: () => { toast.push('success', 'Abonnement enregistré', relationshipManagerId); onClose() },
      onError: (error) => toast.push('error', 'Abonnement refusé', error.message),
    })
  }
  return <Modal title="Synthèse quotidienne d’un CC" onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button variant="primary" type="submit" form="digest-subscription-form" loading={mutation.isPending}>Enregistrer</Button></>}>
    <form id="digest-subscription-form" className="stack" onSubmit={submit}>
      <label className="field">Identifiant CC<input className="input" required pattern="[A-Za-z0-9._-]+" value={relationshipManagerId} disabled={Boolean(entry.relationshipManagerId)} onChange={(event) => setRelationshipManagerId(event.target.value)} placeholder="rm-01" /></label>
      <label className="field">Adresse email<input className="input" type="email" required value={recipientEmail} onChange={(event) => setRecipientEmail(event.target.value)} placeholder="cc@banque.example" /></label>
      <div className="grid cols-2"><label className="field">Fuseau IANA<input className="input" required value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label><label className="field">Heure locale<input className="input" type="number" min={0} max={23} required value={deliveryHour} onChange={(event) => setDeliveryHour(Number(event.target.value))} /></label></div>
      <label className="checkbox"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Envoi quotidien actif</label>
    </form>
  </Modal>
}
