import type { ReactNode } from 'react'

export interface TooltipRow { name: string; value: ReactNode; color?: string }

export function ChartTooltip({ title, rows }: { title?: ReactNode; rows: TooltipRow[] }) {
  return <div className="chart-tooltip">
    {title && <strong>{title}</strong>}
    {rows.map((row) => <div className="row" key={row.name}><span>{row.color && <i className="swatch" style={{ background: row.color }} />}{row.name}</span><b className="num">{row.value}</b></div>)}
  </div>
}
