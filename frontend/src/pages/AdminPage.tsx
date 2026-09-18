import { Edit3, Save, Settings2, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { formatDate, label, safeJson } from '../api/format'
import { useEngine, useRules, useUpdateRule } from '../api/hooks'
import type { RuleConfig, RuleParameter } from '../api/types'
import { Badge, EmptyState, ErrorState, LoadingState, Modal, PageHeader } from '../components/UI'

function RuleEditor({ rule, onClose }: { rule: RuleConfig; onClose: () => void }) {
  const initial = Array.isArray(rule.parameters) ? rule.parameters : Object.entries(rule.parameters || {}).map(([key, value]) => ({ key, value }))
  const [enabled, setEnabled] = useState(rule.enabled)
  const [parameters, setParameters] = useState<RuleParameter[]>(initial)
  const [justification, setJustification] = useState('')
  const mutation = useUpdateRule(rule.ruleId)
  const submit = (event: FormEvent) => { event.preventDefault(); mutation.mutate({ enabled, parameters, justification }, { onSuccess: onClose }) }
  const update = (index: number, value: string) => setParameters((items) => items.map((item, i) => i === index ? { ...item, value: typeof item.value === 'number' ? Number(value) : typeof item.value === 'boolean' ? value === 'true' : value } : item))
  return <Modal title={`Modifier ${rule.name || label(rule.opportunityType)}`} onClose={onClose}><form className="form-stack" onSubmit={submit}><label className="switch-row">Règle active<input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /></label><div className="parameter-list">{parameters.map((parameter, index) => <label key={parameter.key}>{parameter.label || label(parameter.key)}{typeof parameter.value === 'boolean' ? <select value={String(parameter.value)} onChange={(e) => update(index, e.target.value)}><option value="true">Oui</option><option value="false">Non</option></select> : <input type={typeof parameter.value === 'number' ? 'number' : 'text'} step="any" value={String(parameter.value)} onChange={(e) => update(index, e.target.value)} />}<small>{parameter.key}{parameter.unit ? ` · ${parameter.unit}` : ''}</small></label>)}</div><label>Justification de la modification<textarea required rows={3} value={justification} onChange={(e) => setJustification(e.target.value)} placeholder="Motif métier ou gouvernance" /></label>{mutation.isError && <p className="form-error">{mutation.error.message}</p>}<footer className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Annuler</button><button type="submit" className="button primary" disabled={mutation.isPending}><Save size={16} /> {mutation.isPending ? 'Versionnement…' : 'Créer une nouvelle version'}</button></footer></form></Modal>
}

export function AdminPage() {
  const rules = useRules()
  const engine = useEngine()
  const [editing, setEditing] = useState<RuleConfig>()
  return <div className="page"><PageHeader eyebrow="GOUVERNANCE" title="Administration du moteur" description="Lecture et modification versionnée des règles, réservées aux administrateurs." actions={<Badge value="ADMIN" tone="danger" />} />
    <section className="admin-engine"><span><Settings2 /></span><div><p className="eyebrow">MOTEUR ACTIF</p><h2>{engine.data?.engineVersion || 'Version non renseignée'}</h2><p>Règles : {engine.data?.activeRuleVersion || engine.data?.ruleVersion || '—'} · Statut : {label(engine.data?.status)}</p></div><div><ShieldCheck /><span>Dernière exécution</span><strong>{formatDate(engine.data?.lastRunAt || engine.data?.generatedAt, true)}</strong></div></section>
    {engine.isError && <ErrorState error={engine.error} onRetry={() => void engine.refetch()} />}
    <section className="panel"><header className="panel-header"><div><p className="eyebrow">CONFIGURATION</p><h2>Règles et seuils</h2></div><span>Toute modification crée une nouvelle version</span></header>{rules.isPending ? <LoadingState label="Chargement des règles…" /> : rules.isError ? <ErrorState error={rules.error} onRetry={() => void rules.refetch()} /> : !rules.data.data.length ? <EmptyState title="Aucune règle" /> : <div className="rule-list">{rules.data.data.map((rule) => <article className="rule-card" key={rule.ruleId}><div className="rule-head"><div><small>{rule.ruleId}</small><h3>{rule.name || label(rule.opportunityType)}</h3><p>{rule.description || 'Description non fournie par le service.'}</p></div><Badge value={rule.enabled ? 'ACTIVE' : 'INACTIVE'} /></div><div className="rule-meta"><span>Version <strong>{rule.version || rule.ruleVersion || '—'}</strong></span><span>Modifiée <strong>{formatDate(rule.updatedAt)}</strong></span></div><details><summary>Paramètres actifs</summary><pre>{safeJson(rule.parameters)}</pre></details><button type="button" className="button secondary" onClick={() => setEditing(rule)}><Edit3 size={16} /> Modifier la règle</button></article>)}</div>}</section>
    {editing && <RuleEditor rule={editing} onClose={() => setEditing(undefined)} />}
  </div>
}
