import { ArrowLeft, Beaker, CheckCircle2, Edit3, Power, Rocket, RotateCcw, Send, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCustomers } from '../api/hooks'
import { useRuleAudit, useRuleLifecycle, useRuleVersions, useSimulateRule, useStudioRule, useTestRule, useValidateRule } from '../api/ruleStudioHooks'
import type { RuleLifecycleInput, RuleStatus } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { isGroup, metricOptions, operatorOptions } from '../components/rule-studio/ConditionBuilder'
import { RuleHistory, RuleTestProof, SimulationPreview } from '../components/rule-studio/RuleInsights'
import { Badge, ErrorState, LoadingState, Modal, PageHeader } from '../components/UI'
import { label } from '../api/format'

const editableStatuses: RuleStatus[] = ['DRAFT', 'VALIDATED', 'SIMULATED']
const metricLabel = (metric: string) => metricOptions.find(([value]) => value === metric)?.[1] || label(metric)
const operatorLabel = (operator: string) => operatorOptions.find(([value]) => value === operator)?.[1] || label(operator)

function LifecycleDialog({ title, description, actionLabel, pending, error, version, onClose, onConfirm }: { title: string; description: string; actionLabel: string; pending: boolean; error?: Error | null; version?: number | string; onClose: () => void; onConfirm: (input: RuleLifecycleInput) => void }) {
  const [reason, setReason] = useState('')
  return <Modal title={title} onClose={onClose}><form className="form-stack" onSubmit={(event) => { event.preventDefault(); onConfirm({ reason, version }) }}><p className="muted">{description}</p><label>Motif métier ou de gouvernance<textarea autoFocus required minLength={3} rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Cette justification sera conservée dans l’audit." /></label>{error && <p className="form-error" role="alert">{error.message}</p>}<footer className="modal-actions"><button className="button secondary" type="button" onClick={onClose}>Annuler</button><button className="button primary" type="submit" disabled={pending}>{pending ? 'Traitement via API…' : actionLabel}</button></footer></form></Modal>
}

function ReadableConditions({ conditions, logic, depth = 0 }: { conditions: import('../api/types').RuleExpression[]; logic: import('../api/types').RuleLogic; depth?: number }) {
  return <div className="readable-group" data-depth={depth}><strong className="readable-logic">{logic === 'AND' ? 'Toutes ces conditions' : logic === 'OR' ? 'Au moins une condition' : 'Aucune de ces conditions'}</strong>{conditions.map((item, index) => <div key={item.id || index}>{index > 0 && <span className="readable-connector">{logic === 'AND' ? 'ET' : logic === 'OR' ? 'OU' : 'NON'}</span>}{isGroup(item) ? <ReadableConditions conditions={item.conditions} logic={item.logic} depth={depth + 1} /> : <p><strong>{metricLabel(item.metric)}</strong> {operatorLabel(item.operator).toLocaleLowerCase('fr-FR')} <b>{Array.isArray(item.value) ? item.value.join(' et ') : String(item.value)} {label(item.unit)}</b> sur <b>{label(item.period)}</b>.</p>}</div>)}</div>
}

type DialogState = { action: 'submit' | 'approve' | 'publish' | 'disable' | 'rollback'; version?: number | string }
const dialogCopy = {
  submit: ['Soumettre la règle', 'La règle sera verrouillée pour revue par un approbateur distinct.', 'Soumettre via API'],
  approve: ['Approuver la règle', 'Confirmez la revue indépendante. Un créateur ne peut pas approuver sa propre règle.', 'Approuver via API'],
  publish: ['Publier la règle', 'La version approuvée sera publiée puis activée par le service de gouvernance.', 'Publier via API'],
  disable: ['Désactiver la règle', 'La règle active ne sera plus chargée par le moteur de production.', 'Désactiver via API'],
  rollback: ['Restaurer une version', 'Le service créera la restauration auditée de la version sélectionnée.', 'Restaurer via API'],
} as const

export function RuleDetailPage() {
  const { ruleId = '' } = useParams()
  const auth = useAuth()
  const rule = useStudioRule(ruleId)
  const versions = useRuleVersions(ruleId)
  const audit = useRuleAudit(ruleId)
  const validate = useValidateRule(ruleId)
  const simulate = useSimulateRule(ruleId)
  const testRule = useTestRule(ruleId)
  const submit = useRuleLifecycle(ruleId, 'submit')
  const approve = useRuleLifecycle(ruleId, 'approve')
  const publish = useRuleLifecycle(ruleId, 'publish')
  const disable = useRuleLifecycle(ruleId, 'disable')
  const rollback = useRuleLifecycle(ruleId, 'rollback')
  const customers = useCustomers({ pageSize: 100, segment: 'SME', sort: 'legalName' })
  const [customerId, setCustomerId] = useState('')
  const [dialog, setDialog] = useState<DialogState>()

  if (rule.isPending) return <div className="page"><LoadingState label="Chargement de la règle, de sa version et de son statut…" /></div>
  if (rule.isError || !rule.data) return <div className="page"><ErrorState error={rule.error || new Error('Règle absente de la réponse API.')} onRetry={() => void rule.refetch()} /></div>
  const item = rule.data
  const isAnalyst = auth.hasRole('BUSINESS_ANALYST') || auth.hasRole('ADMIN')
  const isApprover = auth.hasRole('RULE_APPROVER') || auth.hasRole('ADMIN')
  const ownRule = Boolean(item.createdBy && [auth.username, item.submittedBy].includes(item.createdBy))
  const simulationInput = { period: { from: new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10), to: new Date().toISOString().slice(0, 10) }, population: { segment: item.scope.segment[0] || 'SME', sectors: item.scope.sectors, regions: item.scope.regions } }
  const lifecycle = dialog?.action === 'submit' ? submit : dialog?.action === 'approve' ? approve : dialog?.action === 'publish' ? publish : dialog?.action === 'disable' ? disable : rollback
  const runLifecycle = (input: RuleLifecycleInput) => lifecycle.mutate(input, { onSuccess: () => setDialog(undefined) })

  return <div className="page rule-detail-page"><Link className="back-link" to="/rule-studio"><ArrowLeft size={16} /> Toutes les règles</Link><PageHeader eyebrow="RULE GOVERNANCE" title={item.name} description={item.description || 'Description non fournie par le service.'} actions={<><Badge value={item.status} /><Badge value={`v${item.version}`} tone="neutral" /></>} />
    <section className="lifecycle-strip" aria-label="Cycle de vie de la règle">{(['DRAFT', 'VALIDATED', 'SIMULATED', 'SUBMITTED', 'APPROVED', 'PUBLISHED', 'ACTIVE'] as RuleStatus[]).map((status) => <div key={status} className={status === item.status ? 'current' : ''}><i /><span>{status}</span></div>)}</section>
    <section className="governance-actions"><div><strong>Actions autorisées pour vos rôles</strong><span>{auth.roles.join(' · ').replaceAll('_', ' ')}</span></div>{isAnalyst && editableStatuses.includes(item.status) && <Link className="button secondary" to={`/rule-studio/${ruleId}/modifier`}><Edit3 size={16} /> Modifier</Link>}{isAnalyst && item.status === 'DRAFT' && <button className="button secondary" type="button" disabled={validate.isPending} onClick={() => validate.mutate()}><CheckCircle2 size={16} /> Valider</button>}{isAnalyst && ['VALIDATED', 'SIMULATED'].includes(item.status) && <button className="button secondary" type="button" disabled={simulate.isPending} onClick={() => simulate.mutate(simulationInput)}><Beaker size={16} /> Simuler</button>}{isAnalyst && item.status === 'SIMULATED' && <button className="button primary" type="button" onClick={() => setDialog({ action: 'submit' })}><Send size={16} /> Soumettre</button>}{isApprover && item.status === 'SUBMITTED' && <button className="button primary" type="button" disabled={ownRule} title={ownRule ? 'Séparation des tâches : approbation par un autre utilisateur requise.' : undefined} onClick={() => setDialog({ action: 'approve' })}><ShieldCheck size={16} /> Approuver</button>}{isApprover && item.status === 'APPROVED' && <button className="button primary" type="button" onClick={() => setDialog({ action: 'publish' })}><Rocket size={16} /> Publier</button>}{isApprover && ['PUBLISHED', 'ACTIVE'].includes(item.status) && <button className="button danger-soft" type="button" onClick={() => setDialog({ action: 'disable' })}><Power size={16} /> Désactiver</button>}</section>
    {(validate.isError || simulate.isError) && <ErrorState error={validate.error || simulate.error} />}{validate.data && <div className={validate.data.valid ? 'validation-result valid' : 'validation-result invalid'}><strong>{validate.data.valid ? 'Validation réussie par le service' : 'Validation refusée par le service'}</strong>{validate.data.errors?.map((entry, index) => <p key={index}>{entry.message}</p>)}</div>}
    <section className="rule-readable-grid"><article className="panel"><p className="eyebrow">WHEN · EXPLICATION</p><h2>Cette règle détecte les PME présentant :</h2><ReadableConditions conditions={item.conditions} logic={item.logic} /></article><article className="panel recommendation-card"><p className="eyebrow">THEN · RECOMMANDATION</p><h2>{label(item.recommendation.opportunityType)}</h2><dl><div><dt>Produits</dt><dd>{item.recommendation.products.length ? item.recommendation.products.map(label).join(' / ') : 'Aucun produit lié'}</dd></div><div><dt>Horizon</dt><dd>{label(item.recommendation.horizon)}</dd></div><div><dt>Score de base</dt><dd>{item.confidence.baseScore} points</dd></div><div><dt>Confiance élevée</dt><dd>à partir de {item.confidence.highThreshold ?? 80}%</dd></div></dl></article></section>
    <SimulationPreview result={simulate.data} />
    <section className="panel rule-tester"><header className="panel-header"><div><p className="eyebrow">RULE TESTER</p><h2>Tester cette version sur une PME</h2></div></header><div className="tester-control"><label>PME à évaluer<select aria-label="PME à évaluer" value={customerId} onChange={(event) => setCustomerId(event.target.value)}><option value="">Sélectionner une PME</option>{customers.data?.data.map((customer) => <option key={customer.customerId} value={customer.customerId}>{customer.legalName} · {customer.customerId}</option>)}</select></label><button className="button primary" type="button" disabled={!customerId || testRule.isPending} onClick={() => testRule.mutate(customerId)}><Beaker size={16} /> Tester la règle</button></div>{customers.isError && <p className="form-error" role="alert">{customers.error.message}</p>}{testRule.isError && <ErrorState error={testRule.error} />}</section><RuleTestProof result={testRule.data} />
    <section className="panel history-panel"><header className="panel-header"><div><p className="eyebrow">VERSIONS & AUDIT</p><h2>Historique complet</h2></div><RotateCcw /></header><RuleHistory versions={versions.data?.data} audit={audit.data?.data} loading={versions.isPending || audit.isPending} error={versions.error || audit.error} onRetry={() => { void versions.refetch(); void audit.refetch() }} onRollback={(version) => setDialog({ action: 'rollback', version })} /></section>
    {dialog && <LifecycleDialog title={dialogCopy[dialog.action][0]} description={dialogCopy[dialog.action][1]} actionLabel={dialogCopy[dialog.action][2]} pending={lifecycle.isPending} error={lifecycle.error} version={dialog.version} onClose={() => setDialog(undefined)} onConfirm={runLifecycle} />}
  </div>
}
