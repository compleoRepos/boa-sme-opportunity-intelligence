import { ArrowRight, Building2, CalendarClock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate, getCustomerName, label } from '../api/format'
import type { Opportunity } from '../api/types'
import { Badge, Confidence } from './UI'

export function OpportunityCard({ opportunity, compact = false }: { opportunity: Opportunity; compact?: boolean }) {
  return <article className={`opportunity-card ${compact ? 'compact' : ''}`} data-testid="opportunity-card">
    <div className="opportunity-accent" data-level={opportunity.priorityLevel} />
    <div className="opportunity-main">
      <div className="opportunity-title-row">
        <div>
          <span className="customer-line"><Building2 size={15} /> {getCustomerName(opportunity)}</span>
          <h3>{label(opportunity.opportunityType)}</h3>
        </div>
        <Badge value={opportunity.priorityLevel} />
      </div>
      <div className="opportunity-meta">
        <span><CalendarClock size={15} /> {label(opportunity.horizon)}</span>
        <span>Détectée le {formatDate(opportunity.generatedAt)}</span>
      </div>
      {!compact && opportunity.why?.length > 0 && <ul className="why-preview">{opportunity.why.slice(0, 2).map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </div>
    <div className="opportunity-side">
      <Confidence value={opportunity.confidence} level={opportunity.confidenceLevel} />
      <Link className="button primary" to={`/opportunites/${opportunity.opportunityId}`}>Examiner <ArrowRight size={16} /></Link>
    </div>
  </article>
}
