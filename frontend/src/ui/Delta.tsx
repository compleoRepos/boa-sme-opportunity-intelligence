import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { formatPercent } from '../api/format'

export function Delta({ value, plain, digits = 0, invert }: { value?: number | null; plain?: boolean; digits?: number; invert?: boolean }) {
  if (value == null || Number.isNaN(value)) return <span className="delta flat plain">—</span>
  const positive = value > 0.005
  const negative = value < -0.005
  const good = invert ? negative : positive
  const bad = invert ? positive : negative
  const tone = good ? 'up' : bad ? 'down' : 'flat'
  const Icon = positive ? ArrowUpRight : negative ? ArrowDownRight : Minus
  return <span className={`delta ${tone} ${plain ? 'plain' : ''}`}><Icon size={13} />{positive ? '+' : ''}{formatPercent(value, digits)}</span>
}
