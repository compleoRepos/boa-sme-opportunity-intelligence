import { Beaker, Check, CheckCircle2, CircleX, Edit3, Power, Rocket, RotateCcw, Send, ShieldCheck } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatDate, formatPercent, label, safeJson } from '../../api/format'
import { useCustomers, useEngine, useProducts } from '../../api/hooks'
import { useRuleAudit, useRuleLifecycle, useRuleSimulations, useRuleVersions, useSimulateRule, useStudioRule, useTestRule, useValidateRule } from '../../api/ruleStudioHooks'
import type { RuleLifecycleInput, RuleSimulationResult, RuleStatus, RuleTestResult } from '../../api/types'
import { useAuth } from '../../auth/AuthProvider'
import { Badge, Button, EmptyState, ErrorState, Modal, Panel, SkeletonStack, Stepper, Tabs, useToast } from '../../ui'
import { ReadableRule } from './RuleBlocks'
import { LIFECYCLE, LIFECYCLE_LABELS, countConditions } from './ruleModel'
import { SimulationForm, SimulationProgress, SimulationResults } from './SimulationPanel'

type Lifecycle = 'submit' | 'approve' | 'publish' | 'disable' | 'rollback'
const COPY: Record<Lifecycle, [string, string, string]> = {
  submit: ['Soumettre à approbation', 'La version simulée est verrouillée pour revue par un approbateur distinct (séparation des tâches).', 'Soumettre'],
  approve: ['Approuver la règle', 'Vous confirmez la revue indépendante de cette version.', 'Approuver'],
  publish: ['Publier la règle', 'La version approuvée est publiée : le moteur l’exécutera au prochain recalcul.', 'Publier'],
  disable: ['Désactiver la règle', 'La règle active ne sera plus chargée par le moteur.', 'Désactiver'],
  rollback: ['Restaurer une version', 'Le service crée une restauration auditée de la version sélectionnée.', 'Restaurer'],
}

export function RuleDetailPage() {
  const { ruleId = '' } = useParams()
  const auth = useAuth()
  const toast = useToast()
  const rule = useStudioRule(ruleId)
  const versions = useRuleVersions(ruleId)
  const audit = useRuleAudit(ruleId)
  const simulations = useRuleSimulations(ruleId)
  const products = useProducts({ pageSize: 100, active: true })
  const customers = useCustomers({ pageSize: 100, segment: 'SME', sort: 'legalName' })
  const engine = useEngine()
  const validate = useValidateRule(ruleId)
  const simulate = useSimulateRule(ruleId)
  const test = useTestRule(ruleId)
  const lifecycle = { submit: useRuleLifecycle(ruleId, 'submit'), approve: useRuleLifecycle(ruleId, 'approve'), publish: useRuleLifecycle(ruleId, 'publish'), disable: useRuleLifecycle(ruleId, 'disable'), rollback: useRuleLifecycle(ruleId, 'rollback') }
  const [dialog, setDialog] = useState<{ action: Lifecycle; version?: number | string }>()
  const [tab, setTab] = useState<'simulation' | 'test' | 'history'>('simulation')
  const [customerId, setCustomerId] = useState('')
  const productNames = useMemo(() => Object.fromEntries((products.data?.data || []).map((product) => [product.productId, product.name])), [products.data])
  const lastSimulation: RuleSimulationResult | undefined = simulate.data || simulations.data?.simulations?.[0]

  if (rule.isPending) return <SkeletonStack rows={4} kind="block" />
  if (rule.isError || !rule.data) return <ErrorState error={rule.error} onRetry={() => void rule.refetch()} />
  const item = rule.data
  const isAnalyst = auth.hasRole('BUSINESS_ANALYST') || auth.hasRole('ADMIN')
  const isApprover = auth.hasRole('RULE_APPROVER') || auth.hasRole('ADMIN')
  const status = item.status as RuleStatus
  const activeVersion = versions.data?.data.find((version) => ['ACTIVE', 'PUBLISHED'].includes(version.status))
  // Séparation des tâches : l'auteur ou le soumetteur ne peut pas approuver sa propre version.
  const ownRule = [item.createdBy, item.updatedBy, item.submittedBy].filter(Boolean).includes(auth.username)
  const run = (action: Lifecycle, input: RuleLifecycleInput) => lifecycle[action].mutate(input, { onSuccess: () => { setDialog(undefined); toast.push('success', `${COPY[action][2]} : effectué`, `Règle ${item.ruleId} · version ${item.version}`) }, onError: (error) => toast.push('error', 'Transition refusée', error.message) })
  const stepperCurrent = status === 'PUBLISHED' ? 'PUBLISHED' : status

  return <>
    <header className="page-head"><div><p className="eyebrow accent">Rule Studio · {item.ruleId}</p><h1>{item.name}</h1><p className="subtitle">{item.description || 'Description non renseignée.'}</p></div><div className="page-actions"><Badge value={status}>{LIFECYCLE_LABELS[status] || status}</Badge><Badge tone="outline">v{item.version}</Badge>{isAnalyst && ['DRAFT', 'VALIDATED', 'SIMULATED'].includes(status) && <Link to={`/back-office/regles/${ruleId}/modifier`} className="btn secondary"><Edit3 size={15} /> Modifier</Link>}</div></header>

    <Panel flush id="lifecycle"><div className="panel-body lifecycle-body">
      <Stepper steps={[...LIFECYCLE]} current={stepperCurrent} labels={LIFECYCLE_LABELS} />
      <div className="row wrap" style={{ gap: 8 }}>
        {isAnalyst && status === 'DRAFT' && <Button variant="primary" size="sm" loading={validate.isPending} icon={<CheckCircle2 size={14} />} onClick={() => validate.mutate(undefined, { onSuccess: (result) => toast.push(result.valid ? 'success' : 'error', result.valid ? 'Configuration valide' : 'Configuration invalide', result.errors?.map((error) => error.message).join(' ')), onError: (error) => toast.push('error', 'Validation refusée', error.message) })}>Valider</Button>}
        {isAnalyst && ['VALIDATED', 'SIMULATED'].includes(status) && <Button variant="primary" size="sm" icon={<Beaker size={14} />} onClick={() => setTab('simulation')}>Simuler</Button>}
        {isAnalyst && status === 'SIMULATED' && <Button variant="primary" size="sm" icon={<Send size={14} />} onClick={() => setDialog({ action: 'submit' })}>Soumettre à approbation</Button>}
        {isApprover && status === 'SUBMITTED' && <Button variant="primary" size="sm" icon={<ShieldCheck size={14} />} disabled={ownRule} title={ownRule ? 'Séparation des tâches : un autre approbateur doit relire cette version.' : undefined} onClick={() => setDialog({ action: 'approve' })}>Approuver</Button>}{isApprover && status === 'SUBMITTED' && ownRule && <span className="muted" style={{ fontSize: 12 }}>En attente d’un approbateur distinct</span>}
        {isApprover && status === 'APPROVED' && <Button variant="primary" size="sm" icon={<Rocket size={14} />} onClick={() => setDialog({ action: 'publish' })}>Publier</Button>}
        {isApprover && ['PUBLISHED', 'ACTIVE'].includes(status) && <Button variant="danger" size="sm" icon={<Power size={14} />} onClick={() => setDialog({ action: 'disable' })}>Désactiver</Button>}
        {['PUBLISHED', 'ACTIVE'].includes(status) && <span className="badge success"><Check size={12} /> Exécutée par le moteur au prochain recalcul</span>}
      </div>
    </div></Panel>

    <div className="grid cols-3 rule-grid">
      <Panel eyebrow="Lecture métier" title="Cette règle détecte les PME pour lesquelles" id="readable" className="span-2">
        <ReadableRule conditions={item.conditions} logic={item.logic} recommendation={item.recommendation} products={productNames} />
      </Panel>
      <Panel eyebrow="Paramètres" title="Confiance & périmètre" id="params">
        <dl className="kv">
          <dt>Conditions</dt><dd>{countConditions(item.conditions)} · logique {item.logic}</dd>
          <dt>Score de base</dt><dd>{item.confidence.baseScore} points</dd>
          <dt>Confiance élevée</dt><dd>à partir de {item.confidence.highThreshold ?? 80} %</dd>
          <dt>Confiance moyenne</dt><dd>à partir de {item.confidence.mediumThreshold ?? 60} %</dd>
          <dt>Segments</dt><dd>{item.scope.segment.map(label).join(', ')}</dd>
          <dt>Secteurs</dt><dd>{item.scope.sectors.map(label).join(', ')}</dd>
          <dt>Validité</dt><dd>{item.lifecycle.validityDays} jours</dd>
          <dt>Cooldown rejet</dt><dd>{item.lifecycle.dismissedCooldownDays} jours</dd>
          <dt>Cooldown conversion</dt><dd>{item.lifecycle.convertedCooldownDays} jours</dd>
          <dt>Cooldown « à revoir »</dt><dd>{item.lifecycle.deferredCooldownDays} jours</dd>
          <dt>Cooldown expiration</dt><dd>{item.lifecycle.expiredCooldownDays} jours</dd>
          <dt>Auteur</dt><dd>{item.createdBy || '—'} · {formatDate(item.createdAt)}</dd>
          <dt>Dernière modification</dt><dd>{item.updatedBy || '—'} · {formatDate(item.updatedAt, true)}</dd>
        </dl>
      </Panel>
    </div>

    <Tabs value={tab} onChange={(id) => setTab(id as typeof tab)} ariaLabel="Outils de la règle" items={[{ id: 'simulation', label: 'Simulation & impact', icon: <Beaker size={14} />, count: simulations.data?.simulations?.length }, { id: 'test', label: 'Tester sur une PME', icon: <ShieldCheck size={14} /> }, { id: 'history', label: 'Versions & audit', icon: <RotateCcw size={14} />, count: versions.data?.data.length }]} />

    {tab === 'simulation' && <Panel eyebrow="Simulation historique" title="Impact estimé sur le portefeuille" id="simulation" tools={isAnalyst && ['VALIDATED', 'SIMULATED'].includes(status) ? <SimulationForm rule={item} asOf={engine.data?.lastRunAt} pending={simulate.isPending} onSubmit={(input) => simulate.mutate(input, { onError: (error) => toast.push('error', 'Simulation refusée', error.message) })} /> : <span className="muted" style={{ fontSize: 12 }}>{status === 'DRAFT' ? 'Validez la règle avant de simuler.' : 'Dernière simulation enregistrée'}</span>}>
      {simulate.isPending ? <SimulationProgress /> : simulate.isError ? <ErrorState error={simulate.error} compact /> : <SimulationResults result={lastSimulation} />}
    </Panel>}

    {tab === 'test' && <Panel eyebrow="Rule tester" title="Preuve condition par condition" id="tester" tools={<form className="row" style={{ gap: 8 }} onSubmit={(event: FormEvent) => { event.preventDefault(); if (customerId) test.mutate(customerId, { onError: (error) => toast.push('error', 'Test refusé', error.message) }) }}><select className="select sm" aria-label="PME à évaluer" value={customerId} onChange={(event) => setCustomerId(event.target.value)} style={{ minWidth: 260 }}><option value="">Choisir une PME</option>{customers.data?.data.map((customer) => <option key={customer.customerId} value={customer.customerId}>{customer.legalName} · {customer.customerId}</option>)}</select><Button type="submit" size="sm" variant="primary" disabled={!customerId} loading={test.isPending} icon={<Beaker size={14} />}>Tester</Button></form>}>
      {test.isError ? <ErrorState error={test.error} compact /> : <TestProof result={test.data} />}
    </Panel>}

    {tab === 'history' && <div className="grid cols-2">
      <Panel eyebrow="Versions" title="Historique des versions" id="versions">{versions.isPending ? <SkeletonStack rows={2} kind="text" /> : !versions.data?.data.length ? <EmptyState compact title="Aucune version" /> : <div className="timeline">{versions.data.data.map((version) => <article key={String(version.version)} className={['ACTIVE', 'PUBLISHED'].includes(version.status) ? 'done' : ''}><strong>Version {version.version} <Badge value={version.status}>{LIFECYCLE_LABELS[version.status] || version.status}</Badge></strong><small>{formatDate(version.createdAt, true)} · {version.createdBy || '—'}</small>{version.reason && <p>{version.reason}</p>}{isApprover && String(version.version) !== String(item.version) && <Button size="sm" variant="ghost" icon={<RotateCcw size={13} />} onClick={() => setDialog({ action: 'rollback', version: version.version })}>Restaurer cette version</Button>}</article>)}</div>}</Panel>
      <Panel eyebrow="Audit" title="Journal des changements" id="audit">{audit.isPending ? <SkeletonStack rows={2} kind="text" /> : !audit.data?.data.length ? <EmptyState compact title="Aucune trace d’audit" /> : <div className="timeline">{audit.data.data.map((entry) => <article key={entry.id}><strong><Badge value={entry.action} /> version {entry.ruleVersion}</strong><small>{formatDate(entry.timestamp, true)} par {entry.userId}</small>{entry.reason && <p>{entry.reason}</p>}{(entry.oldValue !== undefined || entry.newValue !== undefined) && <details><summary className="muted" style={{ fontSize: 12, cursor: 'pointer' }}>Valeurs auditées</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{safeJson({ avant: entry.oldValue, après: entry.newValue })}</pre></details>}</article>)}</div>}</Panel>
    </div>}

    {dialog && <LifecycleDialog action={dialog.action} version={dialog.version} currentVersion={activeVersion?.version} newVersion={item.version} impact={lastSimulation} pending={lifecycle[dialog.action].isPending} error={lifecycle[dialog.action].error} onClose={() => { lifecycle[dialog.action].reset(); setDialog(undefined) }} onConfirm={(input) => run(dialog.action, input)} />}
  </>
}

function LifecycleDialog({ action, version, currentVersion, newVersion, impact, pending, error, onClose, onConfirm }: { action: Lifecycle; version?: number | string; currentVersion?: number | string; newVersion: number | string; impact?: RuleSimulationResult; pending: boolean; error?: Error | null; onClose: () => void; onConfirm: (input: RuleLifecycleInput) => void }) {
  const [reason, setReason] = useState('')
  const [title, description, confirmLabel] = COPY[action]
  return <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button variant="primary" type="submit" form="lifecycle-form" loading={pending}>{confirmLabel}</Button></>}>
    <form id="lifecycle-form" className="stack" onSubmit={(event) => { event.preventDefault(); onConfirm({ reason, version }) }}>
      <p className="muted">{description}</p>
      {['submit', 'publish', 'approve'].includes(action) && <div className="review-grid">
        <div className="stat"><span className="stat-label">Version actuelle</span><span className="stat-value sm">{currentVersion ? `v${currentVersion}` : 'aucune active'}</span></div>
        <div className="stat"><span className="stat-label">Nouvelle version</span><span className="stat-value sm">v{newVersion}</span></div>
        <div className="stat"><span className="stat-label">Impact estimé</span><span className="stat-value sm">{impact ? `${impact.matchedCustomers ?? impact.expectedMatches ?? 0} PME` : 'non simulé'}</span><span className="stat-note">{impact ? `${formatPercent(impact.matchRate ?? (impact.populationAnalyzed ? (impact.matchedCustomers ?? 0) / impact.populationAnalyzed : 0), 1)} de ${impact.populationAnalyzed} analysées` : 'lancez une simulation'}</span></div>
      </div>}
      <label className="field">Motif métier ou de gouvernance<textarea className="textarea" autoFocus required minLength={3} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Conservé dans le journal d’audit." /></label>
      {error && <p className="form-error" role="alert"><CircleX size={14} /> {error.message}</p>}
    </form>
  </Modal>
}

function TestProof({ result }: { result?: RuleTestResult }) {
  if (!result) return <EmptyState compact icon={<Beaker />} title="Aucun test" message="Sélectionnez une PME : le service évalue chaque condition et renvoie la preuve." />
  return <div className="stack">
    <div className="row between"><div><h3 style={{ fontSize: 15 }}>{result.customerName || result.customerId}</h3><span className="muted" style={{ fontSize: 12 }}>{result.customerId} · règle {result.ruleId} v{result.ruleVersion}{result.engineVersion ? ` · moteur ${result.engineVersion}` : ''}</span></div><Badge tone={result.matched ? 'success' : 'danger'}>{result.matched ? 'CORRESPONDANCE' : 'AUCUNE CORRESPONDANCE'} · {formatPercent(result.confidence, 0)}</Badge></div>
    {!result.evidence?.length ? <p className="faint">Le service a répondu sans détail conditionnel.</p> : <ul className="proof-list">{result.evidence.map((evidence, index) => <li key={evidence.conditionId || index} className={evidence.result ? 'ok' : 'ko'}><span className="proof-icon">{evidence.result ? <Check size={14} /> : <CircleX size={14} />}</span><div><strong>{label(evidence.metric)}</strong><span className="muted">observé <b className="num">{String(evidence.actual ?? 'n/a')} {label(evidence.unit)}</b> · attendu {label(evidence.operator).toLowerCase()} {Array.isArray(evidence.threshold) ? evidence.threshold.join(' et ') : String(evidence.threshold)} {label(evidence.unit)}{evidence.period ? ` sur ${label(evidence.period)}` : ''}</span>{evidence.message && <small className="muted">{evidence.message}</small>}</div></li>)}</ul>}
  </div>
}
