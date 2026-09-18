import { ArrowLeft, Building2, CalendarClock, Check, CheckCircle2, ClipboardList, Contact, History, PackageSearch, ShieldCheck, Target, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatDate, formatNumber, formatPercent, getCustomerName, label, safeJson } from '../api/format'
import { useExplanation, useOpportunity, useOpportunityActions } from '../api/hooks'
import type { ActionType } from '../api/types'
import { ActionDialog } from '../components/ActionDialog'
import { Badge, Confidence, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UI'

export function OpportunityDetailPage() {
  const { opportunityId } = useParams()
  const opportunity = useOpportunity(opportunityId)
  const explanation = useExplanation(opportunityId)
  const actions = useOpportunityActions(opportunityId)
  const [dialogType, setDialogType] = useState<ActionType>()
  if (opportunity.isPending) return <div className="page"><LoadingState label="Chargement de l’opportunité…" /></div>
  if (opportunity.isError || !opportunity.data) return <div className="page"><ErrorState error={opportunity.error} onRetry={() => void opportunity.refetch()} /></div>
  const item = opportunity.data

  return <div className="page detail-page">
    <Link className="back-link" to="/opportunites"><ArrowLeft size={16} /> Retour aux opportunités</Link>
    <PageHeader eyebrow={`OPPORTUNITÉ ${item.opportunityId}`} title={label(item.opportunityType)} description={`${getCustomerName(item)} · ${item.customerId}`} actions={<><Badge value={item.priorityLevel} /><Badge value={item.status} tone="info" /></>} />
    <section className="detail-hero">
      <div><span className="customer-line"><Building2 size={16} /> Client concerné</span><Link className="customer-detail-link" to={`/clients/${item.customerId}`}>{getCustomerName(item)}</Link><p>{item.what}</p></div>
      <div className="hero-metrics"><div><span>Confiance</span><Confidence value={item.confidence} level={item.confidenceLevel} /></div><div><span>Horizon</span><strong><CalendarClock /> {label(item.horizon)}</strong></div><div><span>Priorité commerciale</span><strong>{formatNumber(item.priorityScore, 1)} / 100</strong></div></div>
    </section>
    <section className="action-bar" aria-label="Actions sur l’opportunité">
      <div><strong>Quelle suite souhaitez-vous donner ?</strong><span>Chaque choix est enregistré et auditable.</span></div>
      <div><button type="button" className="button success" onClick={() => setDialogType('ACCEPT_OPPORTUNITY')}><Check size={16} /> Accepter</button><button type="button" className="button secondary" onClick={() => setDialogType('CONTACT_CUSTOMER')}><Contact size={16} /> Contacter</button><button type="button" className="button danger-soft" onClick={() => setDialogType('DISMISS_OPPORTUNITY')}><XCircle size={16} /> Écarter</button><button type="button" className="button primary" onClick={() => setDialogType('CREATE_FOLLOW_UP')}><ClipboardList size={16} /> Créer un suivi</button></div>
    </section>

    <section className="explain-grid" aria-label="Explication de l’opportunité">
      <article className="explain-card why-card"><span className="explain-index">01</span><Target /><p className="eyebrow">WHY · POURQUOI</p><h2>Signaux déterminants</h2>{item.why?.length ? <ul>{item.why.map((reason) => <li key={reason}><CheckCircle2 /> {reason}</li>)}</ul> : <EmptyState message="Aucune raison résumée par le Gateway." />}</article>
      <article className="explain-card"><span className="explain-index">02</span><PackageSearch /><p className="eyebrow">WHAT · QUOI</p><h2>Besoin potentiel</h2><p>{item.what}</p><h3>Produits recommandés</h3>{item.recommendedProducts?.length ? <div className="chip-list">{item.recommendedProducts.map((product) => <Link key={product.productId} to={`/produits?productId=${product.productId}`}>{product.name}</Link>)}</div> : <span className="muted">Aucun produit retourné.</span>}</article>
      <article className="explain-card"><span className="explain-index">03</span><CalendarClock /><p className="eyebrow">WHEN · QUAND</p><h2>Fenêtre d’action</h2><p>{item.when}</p><div className="callout">Horizon configuré : <strong>{label(item.horizon)}</strong></div></article>
      <article className="explain-card"><span className="explain-index">04</span><ShieldCheck /><p className="eyebrow">CONFIDENCE · CONFIANCE</p><h2>Niveau calculé</h2><Confidence value={item.confidence} level={item.confidenceLevel} /><p className="muted">Il s’agit d’une confiance dans la recommandation commerciale, et non d’un score de risque.</p></article>
    </section>

    <section className="panel evidence-panel" data-testid="evidence-section"><header className="panel-header"><div><p className="eyebrow">EVIDENCE · PREUVES</p><h2>Détail de la décision moteur</h2></div><span>{item.evidenceCount ?? explanation.data?.signals.length ?? '—'} preuve(s)</span></header>
      {explanation.isPending ? <LoadingState label="Chargement de l’explication complète…" /> : explanation.isError ? <ErrorState error={explanation.error} onRetry={() => void explanation.refetch()} /> : explanation.data ? <>
        <div className="evidence-summary"><div><span>Version moteur</span><strong>{explanation.data.engineVersion || item.engineVersion || '—'}</strong></div><div><span>Version règle</span><strong>{explanation.data.ruleVersion || item.ruleVersion || '—'}</strong></div><div><span>Générée le</span><strong>{formatDate(item.generatedAt, true)}</strong></div></div>
        <div className="evidence-columns"><div><h3>Signaux sources</h3>{explanation.data.signals.length ? explanation.data.signals.map((signal) => <div className="evidence-row" key={signal.signalId}><div><strong>{label(signal.type)}</strong><span>{signal.signalId}</span></div><div><span>Valeur {formatPercent(signal.value, 1)}</span><span>Seuil {formatPercent(signal.threshold, 1)}</span></div></div>) : <EmptyState message="Aucun signal retourné." />}</div><div><h3>Composantes de confiance</h3>{explanation.data.confidenceComponents.length ? explanation.data.confidenceComponents.map((component) => <div className="score-row" key={component.name}><span className={component.satisfied ? 'score-check ok' : 'score-check'}>{component.satisfied ? <Check /> : '–'}</span><div><strong>{label(component.name)}</strong><div className="score-track"><i style={{ width: `${component.maxPoints ? Math.min(100, component.points / component.maxPoints * 100) : 0}%` }} /></div></div><span>{component.points}/{component.maxPoints}</span></div>) : <EmptyState message="Aucune composante retournée." />}</div></div>
        <details className="technical-evidence"><summary>Seuils et comparaison historique</summary><div className="technical-grid"><pre>{safeJson(explanation.data.thresholds)}</pre><pre>{safeJson(explanation.data.historicalComparison)}</pre></div></details>
      </> : null}
    </section>

    <section className="panel history-panel"><header className="panel-header"><div><p className="eyebrow">HISTORIQUE</p><h2>Actions enregistrées</h2></div><History /></header>{actions.isPending ? <LoadingState /> : actions.isError ? <ErrorState error={actions.error} onRetry={() => void actions.refetch()} /> : !actions.data?.data.length ? <EmptyState title="Aucune action" message="Aucune suite commerciale n’a encore été enregistrée." /> : <div className="timeline">{actions.data.data.map((action) => <article key={action.actionId}><span className="timeline-dot" /><div><strong>{label(action.actionType)}</strong><p>{action.note || 'Aucune note'}</p><small>{formatDate(action.createdAt, true)}{action.outcome ? ` · ${label(action.outcome)}` : ''}</small></div></article>)}</div>}</section>
    {dialogType && opportunityId && <ActionDialog opportunityId={opportunityId} initialType={dialogType} onClose={() => setDialogType(undefined)} />}
  </div>
}
