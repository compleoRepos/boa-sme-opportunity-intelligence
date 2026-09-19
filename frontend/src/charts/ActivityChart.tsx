import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatCompact, formatMonth, formatNumber, formatShortDate } from '../api/format'
import type { ActivityPoint } from '../api/types'
import { ChartTooltip } from './ChartTooltip'
import { CHART, SERIES, axisProps } from './theme'

type Mode = 'flows' | 'volume' | 'international'

const labelFor = (point: ActivityPoint, granularity: string) => granularity === 'MONTH' ? formatMonth(point.period) : formatShortDate(point.period)

export function ActivityChart({ points, granularity, mode, height = 240 }: { points: ActivityPoint[]; granularity: string; mode: Mode; height?: number }) {
  if (!points.length) return <div className="chart-empty">Aucune transaction sur la période sélectionnée.</div>
  const data = points.map((point) => ({ ...point, label: labelFor(point, granularity) }))
  const money = (value: number) => formatCompact(value).replace(/\s?(M|k)?MAD$/, ' $1').trim()
  if (mode === 'volume') {
    return <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
        <CartesianGrid vertical={false} stroke={CHART.grid} />
        <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...axisProps} width={44} tickFormatter={(value: number) => formatNumber(value)} />
        <Tooltip cursor={{ fill: 'rgba(31,95,208,0.06)' }} content={({ payload }) => { const point = payload?.[0]?.payload as (ActivityPoint & { label: string }) | undefined; return point ? <ChartTooltip title={point.label} rows={[{ name: 'Transactions', value: formatNumber(point.transactionCount), color: SERIES.transactionCount }, { name: 'dont internationales', value: formatNumber(point.internationalCount), color: SERIES.internationalAmount }]} /> : null }} />
        <Bar dataKey="transactionCount" fill={SERIES.transactionCount} radius={[4, 4, 0, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  }
  if (mode === 'international') {
    return <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
        <CartesianGrid vertical={false} stroke={CHART.grid} />
        <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...axisProps} width={48} tickFormatter={money} />
        <Tooltip cursor={{ fill: 'rgba(14,155,176,0.08)' }} content={({ payload }) => { const point = payload?.[0]?.payload as (ActivityPoint & { label: string }) | undefined; return point ? <ChartTooltip title={point.label} rows={[{ name: 'Flux internationaux', value: formatCompact(point.internationalAmount), color: SERIES.internationalAmount }, { name: 'Opérations', value: formatNumber(point.internationalCount) }]} /> : null }} />
        <Bar dataKey="internationalAmount" fill={SERIES.internationalAmount} radius={[4, 4, 0, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  }
  return <ResponsiveContainer width="100%" height={height}>
    <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
      <defs>
        <linearGradient id="inflowFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={SERIES.inflow} stopOpacity={0.16} /><stop offset="100%" stopColor={SERIES.inflow} stopOpacity={0} /></linearGradient>
        <linearGradient id="outflowFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={SERIES.outflow} stopOpacity={0.12} /><stop offset="100%" stopColor={SERIES.outflow} stopOpacity={0} /></linearGradient>
      </defs>
      <CartesianGrid vertical={false} stroke={CHART.grid} />
      <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={24} />
      <YAxis {...axisProps} width={48} tickFormatter={money} />
      <Tooltip cursor={{ stroke: CHART.axis, strokeDasharray: '0' }} content={({ payload }) => { const point = payload?.[0]?.payload as (ActivityPoint & { label: string }) | undefined; return point ? <ChartTooltip title={point.label} rows={[{ name: 'Encaissements', value: formatCompact(point.inflow), color: SERIES.inflow }, { name: 'Décaissements', value: formatCompact(point.outflow), color: SERIES.outflow }, { name: 'dont fournisseurs', value: formatCompact(point.supplierPayments), color: SERIES.supplierPayments }, { name: 'Net', value: formatCompact(point.net) }]} /> : null }} />
      <Area type="monotone" dataKey="inflow" stroke={SERIES.inflow} strokeWidth={2} fill="url(#inflowFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} />
      <Area type="monotone" dataKey="outflow" stroke={SERIES.outflow} strokeWidth={2} fill="url(#outflowFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} />
    </AreaChart>
  </ResponsiveContainer>
}
