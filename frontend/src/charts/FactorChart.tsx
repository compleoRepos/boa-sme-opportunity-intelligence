import { formatNumber } from '../api/format'
import type { PropensityFactor } from '../api/types'
import { CHART } from './theme'

/** Contribution des facteurs au score ML : barres divergentes autour de zéro (HTML/CSS). */
export function FactorChart({ factors }: { factors: PropensityFactor[] }) {
  const values = factors.map((factor) => Math.abs(factor.contribution ?? 0))
  const peak = Math.max(...values, 0.0001)
  return <ul className="factors" aria-label="Contribution des facteurs">
    {factors.map((factor) => {
      const contribution = factor.contribution ?? 0
      const positive = contribution >= 0
      const width = Math.max(2, (Math.abs(contribution) / peak) * 100)
      return <li key={factor.feature} className="factor">
        <div className="factor-copy"><strong>{factor.label}</strong><small>{factor.value == null ? '' : typeof factor.value === 'number' ? `valeur ${formatNumber(factor.value, 2)}` : String(factor.value)}</small></div>
        <div className="factor-axis" aria-hidden="true">
          <span className="factor-neg">{!positive && <i style={{ width: `${width}%`, background: CHART.red }} />}</span>
          <span className="factor-zero" />
          <span className="factor-pos">{positive && <i style={{ width: `${width}%`, background: CHART.green }} />}</span>
        </div>
        <span className={`factor-value num ${positive ? 'up' : 'down'}`}>{positive ? '+' : ''}{formatNumber(contribution, 3)}</span>
      </li>
    })}
  </ul>
}
