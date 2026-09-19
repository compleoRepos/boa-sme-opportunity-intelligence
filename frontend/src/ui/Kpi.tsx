import type { ReactNode } from 'react'
import { AnimatedNumber } from './AnimatedNumber'

export function Kpi({ label, value, note, icon, tone = 'blue', hero, onClick, active, format, 'data-demo': demo }: { label: string; value: number | string | undefined | null; note?: ReactNode; icon?: ReactNode; tone?: 'navy' | 'blue' | 'red' | 'amber' | 'green' | 'violet'; hero?: boolean; onClick?: () => void; active?: boolean; format?: (value: number) => string; 'data-demo'?: string }) {
  const Tag = onClick ? 'button' : 'article'
  return <Tag className={`kpi tone-${tone} ${hero ? 'hero' : ''} ${onClick ? 'clickable' : ''} ${active ? 'active' : ''}`} onClick={onClick} type={onClick ? 'button' : undefined} data-demo={demo} aria-pressed={onClick ? active : undefined}>
    <span className="kpi-label">{label}</span>
    {icon && <span className="kpi-icon" aria-hidden="true">{icon}</span>}
    <strong className="kpi-value">{typeof value === 'number' ? <AnimatedNumber value={value} format={format} /> : value ?? '—'}</strong>
    {note && <span className="kpi-note">{note}</span>}
  </Tag>
}
