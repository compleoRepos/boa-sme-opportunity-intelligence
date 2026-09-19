import type { ReactNode } from 'react'
import { label } from '../api/format'

export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'violet' | 'teal' | 'outline' | 'navy'

const toneFor = (value?: string | null): Tone => {
  switch (value) {
    case 'HIGH': case 'ACTIVE': case 'PUBLISHED': case 'APPROVED': case 'CONVERTED': case 'OFFER_CREATED': case 'MATCH': case 'COMPLETED': case 'DONE':
      return 'success'
    case 'MEDIUM': case 'SUBMITTED': case 'SIMULATED': case 'VALIDATED': case 'MEETING_SCHEDULED': case 'CONTACTED': case 'OPEN':
      return 'warning'
    case 'LOW': case 'DISABLED': case 'RETIRED': case 'REJECTED': case 'NOT_RELEVANT': case 'NO_MATCH': case 'CANCELLED': case 'INACTIVE':
      return 'danger'
    case 'DRAFT': case 'CANDIDATE':
      return 'neutral'
    default:
      return 'info'
  }
}

export function Badge({ value, tone, children, className = '' }: { value?: string | null; tone?: Tone; children?: ReactNode; className?: string }) {
  const resolved = tone || toneFor(value)
  return <span className={`badge ${resolved} ${className}`}>{children ?? label(value)}</span>
}

export function PriorityBadge({ level }: { level?: string | null }) {
  if (!level) return <span className="badge neutral">—</span>
  return <span className="badge priority" data-level={level}>{level}</span>
}
