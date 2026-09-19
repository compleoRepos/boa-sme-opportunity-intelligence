import type { CSSProperties } from 'react'

export function Ring({ value, size = 'md', color, onClick, label, suffix = '%' }: { value: number; size?: 'md' | 'lg' | 'xl'; color?: string; onClick?: () => void; label?: string; suffix?: string }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100)
  const tone = color || (percent >= 75 ? 'var(--green-600)' : percent >= 50 ? 'var(--amber-600)' : 'var(--ink-400)')
  const style = { '--ring-value': percent, '--ring-color': tone } as CSSProperties
  const Tag = onClick ? 'button' : 'div'
  return <Tag className={`ring ${size === 'md' ? '' : size} ${onClick ? 'clickable' : ''}`} style={style} onClick={onClick} type={onClick ? 'button' : undefined} aria-label={label || `${percent} ${suffix}`} title={label}>
    <span>{percent}{suffix}</span>
  </Tag>
}
