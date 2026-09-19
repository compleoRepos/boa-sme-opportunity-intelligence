import type { ReactNode } from 'react'

export interface TabItem { id: string; label: ReactNode; count?: number | null; icon?: ReactNode }

export function Tabs({ items, value, onChange, pill, ariaLabel }: { items: TabItem[]; value: string; onChange: (id: string) => void; pill?: boolean; ariaLabel?: string }) {
  return <div className={`tabs ${pill ? 'pill' : ''}`} role="tablist" aria-label={ariaLabel}>
    {items.map((item) => <button key={item.id} role="tab" type="button" className="tab" aria-selected={value === item.id} onClick={() => onChange(item.id)}>
      {item.icon}{item.label}{item.count != null && <span className="count">{item.count}</span>}
    </button>)}
  </div>
}

export function Segmented<T extends string>({ options, value, onChange, ariaLabel }: { options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void; ariaLabel?: string }) {
  return <div className="segmented" role="group" aria-label={ariaLabel}>
    {options.map((option) => <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>
}
