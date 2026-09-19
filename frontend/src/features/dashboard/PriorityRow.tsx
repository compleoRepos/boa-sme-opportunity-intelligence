import { ArrowRight, Building2, CalendarClock, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatRelative, initials, label, opportunityTone } from '../../api/format'
import type { PortfolioCustomerSummary } from '../../api/types'
import { Badge, PriorityBadge, Ring, Tooltip } from '../../ui'
import { primaryOpportunity, productNames, topSignals } from '../customer/signals'

/**
 * Ligne « carte d'information » du dashboard CC : tout ce qu'il faut pour décider
 * si la PME mérite un regard aujourd'hui, sans ouvrir la fiche.
 */
export function PriorityRow({ customer, index, compact, linkSuffix = '' }: { customer: PortfolioCustomerSummary; index: number; compact?: boolean; linkSuffix?: string }) {
  const opportunity = primaryOpportunity(customer)
  const signals = topSignals(opportunity?.why, 3)
  const products = productNames(opportunity)
  const nextAction = customer.nextActions[0]
  const to = `/clients/${customer.customerId}${linkSuffix}`
  return <article className={`priority-row rise`} style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }} data-priority={customer.priorityLevel} data-demo={index === 0 ? 'first-row' : undefined}>
    <Link to={to} className="priority-main" aria-label={`Ouvrir la fiche de ${customer.customerName}`}>
      <span className="avatar company" aria-hidden="true">{initials(customer.customerName)}</span>
      <div className="priority-copy">
        <div className="row" style={{ gap: 8 }}>
          <h3>{customer.customerName}</h3>
          <PriorityBadge level={customer.priorityLevel} />
        </div>
        <p className="muted"><Building2 size={12} /> {label(customer.industry)} · {customer.branchName || label(customer.segment)} · <span className="mono">{customer.customerId}</span></p>
        {opportunity ? <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
          <Badge tone={opportunityTone(opportunity.opportunityType)}>{label(opportunity.opportunityType)}</Badge>
          {opportunity.generatedAt && <span className="muted" style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4 }}><Clock3 size={12} /> Détecté {formatRelative(opportunity.generatedAt)}</span>}
        </div> : <p className="faint" style={{ marginTop: 6, fontSize: 12 }}>Aucune opportunité ouverte · suivi standard</p>}
      </div>
    </Link>
    {!compact && <div className="priority-signals" aria-label="Signaux déterminants">
      {signals.length ? signals.map((signal) => <Tooltip key={signal.raw} content={<><strong>{signal.label}</strong>{signal.text}</>}><span className="signal-chip"><span>{signal.label}</span><b className={`num ${(signal.observed ?? 0) >= 0 ? 'up' : 'down'}`}>{signal.delta}</b></span></Tooltip>) : <span className="faint" style={{ fontSize: 12 }}>{customer.priorityReason || 'Aucun signal chiffré'}</span>}
      {products.length > 0 && <span className="chip product" title={products.join(' · ')}>{products[0]}{products.length > 1 ? ` +${products.length - 1}` : ''}</span>}
    </div>}
    <div className="priority-side">
      <Tooltip content={<><strong>Propension commerciale</strong>Intérêt commercial estimé (ML + règles). Ce n’est pas un score de risque.</>}>
        <Ring value={customer.propensityScore} label={`Propension ${Math.round(customer.propensityScore * 100)} %`} />
      </Tooltip>
      {nextAction ? <span className="muted next-action"><CalendarClock size={12} /> {label(nextAction.actionType)}{nextAction.dueAt ? ` · ${formatRelative(nextAction.dueAt)}` : ''}</span> : <span className="faint next-action">Aucune action planifiée</span>}
      <Link to={to} className="btn secondary sm" data-demo-link="sheet">Voir le client <ArrowRight size={14} /></Link>
    </div>
  </article>
}
