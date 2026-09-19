import { Area, AreaChart, ResponsiveContainer } from 'recharts'

export function Sparkline({ values, color = '#1f5fd0', height = 36 }: { values: number[]; color?: string; height?: number }) {
  if (values.length < 2) return <div style={{ height }} aria-hidden="true" />
  const data = values.map((value, index) => ({ index, value }))
  const id = `spark-${color.replace('#', '')}`
  return <div style={{ width: '100%', height }} aria-hidden="true">
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.25} /><stop offset="100%" stopColor={color} stopOpacity={0} /></linearGradient></defs>
        <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.75} fill={`url(#${id})`} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  </div>
}
