import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber, formatShortDate } from '../api/format'
import type { TimelinePoint } from '../api/types'
import { ChartTooltip } from './ChartTooltip'
import { CHART, axisProps } from './theme'

export function TimelineChart({ points, color = CHART.blue, name, height = 180 }: { points?: TimelinePoint[]; color?: string; name: string; height?: number }) {
  if (!points?.length) return <div className="chart-empty">Aucune donnée datée sur ce périmètre.</div>
  const data = points.map((point) => ({ ...point, label: formatShortDate(point.date) }))
  return <ResponsiveContainer width="100%" height={height}>
    <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="35%">
      <CartesianGrid vertical={false} stroke={CHART.grid} />
      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={20} />
      <YAxis {...axisProps} width={36} allowDecimals={false} />
      <Tooltip cursor={{ fill: 'rgba(31,95,208,0.06)' }} content={({ payload }) => { const point = payload?.[0]?.payload as (TimelinePoint & { label: string }) | undefined; return point ? <ChartTooltip title={point.label} rows={[{ name, value: formatNumber(point.count), color }]} /> : null }} />
      <Bar dataKey="count" fill={color} radius={[4, 4, 0, 0]} maxBarSize={24} />
    </BarChart>
  </ResponsiveContainer>
}
