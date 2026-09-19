import { formatNumber, formatPercent, label } from '../api/format'
import type { BreakdownItem } from '../api/types'

/** Barres horizontales HTML (pas de dépendance), ≤ 24px, libellé direct, part en %. */
export function BreakdownBars({ items, nameKey, colorFor, onSelect, max = 8, labelFor }: { items?: BreakdownItem[]; nameKey: keyof BreakdownItem; colorFor?: (name: string) => string; onSelect?: (name: string) => void; max?: number; labelFor?: (item: BreakdownItem) => string }) {
  if (!items?.length) return <div className="chart-empty">Aucune donnée agrégée pour ce périmètre.</div>
  const top = items.slice(0, max)
  const peak = Math.max(...top.map((item) => item.count), 1)
  return <ul className="breakdown" aria-label="Répartition">
    {top.map((item) => {
      const name = String(item[nameKey] ?? '—')
      const text = labelFor ? labelFor(item) : label(name)
      const color = colorFor?.(name) || 'var(--chart-1)'
      const Tag = onSelect ? 'button' : 'div'
      return <li key={name}>
        <Tag className="breakdown-row" onClick={onSelect ? () => onSelect(name) : undefined} type={onSelect ? 'button' : undefined}>
          <span className="breakdown-label" title={text}>{text}</span>
          <span className="breakdown-track"><i style={{ width: `${Math.max(2, (item.count / peak) * 100)}%`, background: color }} /></span>
          <span className="breakdown-value num">{formatNumber(item.count)}<small>{item.share != null ? formatPercent(item.share) : ''}</small></span>
        </Tag>
      </li>
    })}
  </ul>
}
