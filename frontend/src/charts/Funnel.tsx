import { formatNumber, formatPercent, label } from '../api/format'
import type { ConversionFunnelItem } from '../api/types'
import { OUTCOME_COLORS } from './theme'

export function Funnel({ stages }: { stages: ConversionFunnelItem[] }) {
  if (!stages.length) return <div className="chart-empty">Aucune conversion enregistrée.</div>
  const peak = Math.max(...stages.map((stage) => stage.count), 1)
  return <ul className="funnel" aria-label="Entonnoir de conversion">
    {stages.map((stage) => <li key={stage.stage}>
      <div className="row between"><strong>{label(stage.stage)}</strong><span className="num"><b>{formatNumber(stage.count)}</b>{stage.rate != null && <small className="muted"> · {formatPercent(stage.rate)}</small>}</span></div>
      <span className="bar thick"><i style={{ width: `${Math.max(2, (stage.count / peak) * 100)}%`, background: OUTCOME_COLORS[stage.stage] || 'var(--chart-1)' }} /></span>
    </li>)}
  </ul>
}
