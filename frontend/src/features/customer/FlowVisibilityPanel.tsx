import { Check, Landmark, PencilLine } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { formatDate, formatPercent, label, safeJson } from '../../api/format'
import { useDeclareBankingRelationship } from '../../api/hooks'
import type { BankingRelationship, Customer, FlowVisibility, FlowVisibilityLevel } from '../../api/types'
import { Badge, Button, Drawer, ErrorState } from '../../ui'

const LEVEL_LABELS: Record<FlowVisibilityLevel, string> = {
  HIGH: 'forte',
  PARTIAL: 'partielle',
  LOW: 'faible',
  UNKNOWN: 'inconnue',
}

const LEVEL_TONES: Record<FlowVisibilityLevel, 'success' | 'warning' | 'danger' | 'neutral'> = {
  HIGH: 'success',
  PARTIAL: 'warning',
  LOW: 'danger',
  UNKNOWN: 'neutral',
}

const METHOD_LABELS: Record<string, string> = {
  DECLARED: 'Déclaration du chargé de clientèle',
  TURNOVER_RATIO: 'Rapport encaissements / chiffre d’affaires',
  TRANSACTION_FINGERPRINTS: 'Empreintes de multibancarisation',
  NONE: 'Données insuffisantes',
}

export function visibilityLabel(level?: FlowVisibilityLevel | null) {
  return LEVEL_LABELS[level || 'UNKNOWN']
}

export function FlowVisibilityBadge({ visibility, onClick }: { visibility?: FlowVisibility | null; onClick: () => void }) {
  const level = visibility?.level || 'UNKNOWN'
  return <button type="button" className="visibility-badge-button" onClick={onClick} aria-label={`Ouvrir la visibilité des flux : ${visibilityLabel(level)}`}>
    <Badge tone={LEVEL_TONES[level]}>Visibilité des flux : {visibilityLabel(level)}</Badge>
  </button>
}

function evidenceText(entry: Record<string, unknown>) {
  const fact = typeof entry.fact === 'string' ? label(entry.fact) : undefined
  const detail = [entry.value, entry.count, entry.share, entry.amount, entry.status]
    .find((value) => value !== undefined && value !== null)
  const observed = entry.observedOn || entry.asOf || entry.date
  const renderedDetail = detail == null
    ? undefined
    : typeof detail === 'object'
      ? safeJson(detail)
      : String(detail)
  return [fact, renderedDetail, observed ? formatDate(String(observed)) : undefined]
    .filter(Boolean)
    .join(' · ') || safeJson(entry)
}

export function FlowVisibilityDrawer({ customer, canDeclare, onClose }: { customer: Customer; canDeclare: boolean; onClose: () => void }) {
  const mutation = useDeclareBankingRelationship(customer.customerId)
  const [editing, setEditing] = useState(false)
  const [relationship, setRelationship] = useState<BankingRelationship>(customer.bankingRelationship === 'UNKNOWN' || !customer.bankingRelationship ? 'PRIMARY' : customer.bankingRelationship)
  const [reason, setReason] = useState('')
  const [declaredTurnover, setDeclaredTurnover] = useState('')
  const current = mutation.data || customer
  const visibility = current.flowVisibility || customer.flowVisibility
  const declaration = current.bankingRelationshipDeclaration || customer.bankingRelationshipDeclaration

  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({
      bankingRelationship: relationship,
      reason: reason.trim(),
      ...(declaredTurnover ? { declaredTurnover: Number(declaredTurnover), declaredTurnoverAsOf: new Date().toISOString().slice(0, 10) } : {}),
    }, {
      onSuccess: () => {
        setEditing(false)
        setReason('')
      },
    })
  }

  return <Drawer eyebrow="Relation bancaire" title={`Visibilité des flux · ${customer.legalName}`} onClose={onClose} size="narrow" tools={<Badge tone={LEVEL_TONES[visibility?.level || 'UNKNOWN']}>{visibilityLabel(visibility?.level)}</Badge>}>
    <section className="visibility-summary">
      <div className="visibility-level" data-level={visibility?.level || 'UNKNOWN'}><Landmark size={20} /><div><span>Niveau estimé</span><strong>{visibilityLabel(visibility?.level)}</strong></div></div>
      <dl className="kv">
        <dt>Méthode</dt><dd>{METHOD_LABELS[visibility?.method || 'NONE'] || label(visibility?.method)}</dd>
        <dt>Part estimée chez BOA</dt><dd>{visibility?.estimatedShare == null ? 'Non estimée' : formatPercent(visibility.estimatedShare, 0)}</dd>
        <dt>Date de référence</dt><dd>{formatDate(visibility?.asOf)}</dd>
        <dt>Relation déclarée</dt><dd>{label(current.bankingRelationship || 'UNKNOWN')}</dd>
      </dl>
      <p className="faint">Indicateur commercial fondé uniquement sur les données BOA et les déclarations autorisées. Toutes les valeurs et tous les seuils sont une <strong>HYPOTHÈSE À VALIDER AVEC BOA</strong>.</p>
    </section>

    <section className="stack">
      <div><p className="eyebrow">Faits datés</p><h3>Éléments d’évidence</h3></div>
      {visibility?.evidence?.length ? <ul className="evidence-list visibility-evidence">{visibility.evidence.map((entry, index) => <li key={`${String(entry.fact || 'fact')}-${index}`}><Check size={12} /><span>{evidenceText(entry)}</span></li>)}</ul> : <p className="faint">Aucun fait suffisant : l’absence de preuve n’est jamais interprétée comme une visibilité forte.</p>}
    </section>

    <section className="declaration-card">
      <div className="row between wrap"><div><p className="eyebrow">Déclaration</p><h3>Relation bancaire</h3></div>{canDeclare && !editing && <Button size="sm" icon={<PencilLine size={14} />} onClick={() => setEditing(true)}>Déclarer la relation bancaire</Button>}</div>
      {declaration?.declaredAt ? <p className="declaration-meta"><strong>{label(declaration.value || current.bankingRelationship)}</strong> · déclaré par {declaration.declaredBy || '—'} le {formatDate(declaration.declaredAt, true)}{declaration.reason ? <> · Motif : {declaration.reason}</> : null}</p> : <p className="faint">Aucune déclaration du chargé de clientèle enregistrée.</p>}
      {!canDeclare && <p className="faint">Déclaration réservée au chargé de clientèle du portefeuille et au responsable de l’agence.</p>}
      {editing && <form className="stack declaration-form" onSubmit={submit}>
        <label className="field">Relation bancaire<select className="select" value={relationship} onChange={(event) => setRelationship(event.target.value as BankingRelationship)}><option value="EXCLUSIVE">Exclusive</option><option value="PRIMARY">Principale</option><option value="SECONDARY">Secondaire</option></select></label>
        <label className="field">Motif<textarea className="input" rows={3} minLength={8} maxLength={1000} required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Élément constaté lors de l’échange client…" /></label>
        <label className="field">Chiffre d’affaires déclaré (MAD, facultatif)<input className="input" type="number" min="1" step="1" value={declaredTurnover} onChange={(event) => setDeclaredTurnover(event.target.value)} /></label>
        {mutation.isError && <ErrorState error={mutation.error} compact />}
        <div className="row"><Button type="submit" variant="primary" loading={mutation.isPending} disabled={reason.trim().length < 8}>Enregistrer la déclaration</Button><Button onClick={() => setEditing(false)}>Annuler</Button></div>
      </form>}
      {mutation.isSuccess && !editing && <div className="notice success"><Check size={16} /><div><strong>Déclaration enregistrée et auditée.</strong>La visibilité calculée sera actualisée au prochain recalcul analytique.</div></div>}
    </section>
  </Drawer>
}
