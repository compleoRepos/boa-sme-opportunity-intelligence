import { useRef, type KeyboardEvent, type ReactNode } from 'react'

export interface TabItem { id: string; label: ReactNode; count?: number | null; icon?: ReactNode }

export const tabId = (panelId: string, itemId: string) => `${panelId}-tab-${itemId}`

export function Tabs({ items, value, onChange, pill, ariaLabel, panelId }: { items: TabItem[]; value: string; onChange: (id: string) => void; pill?: boolean; ariaLabel?: string; panelId?: string }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  const selectAt = (index: number) => {
    const item = items[index]
    if (!item) return
    onChange(item.id)
    refs.current[index]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | undefined
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % items.length
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = items.length - 1
    if (next === undefined) return
    event.preventDefault()
    selectAt(next)
  }

  return <div className={`tabs ${pill ? 'pill' : ''}`} role="tablist" aria-label={ariaLabel ?? 'Onglets'} aria-orientation="horizontal">
    {items.map((item, index) => <button
      key={item.id}
      ref={(element) => { refs.current[index] = element }}
      id={panelId ? tabId(panelId, item.id) : undefined}
      role="tab"
      type="button"
      className="tab"
      aria-selected={value === item.id}
      aria-controls={panelId}
      tabIndex={value === item.id ? 0 : -1}
      onClick={() => onChange(item.id)}
      onKeyDown={(event) => onKeyDown(event, index)}
    >
      {item.icon}{item.label}{item.count != null && <span className="count">{item.count}</span>}
    </button>)}
  </div>
}

export function Segmented<T extends string>({ options, value, onChange, ariaLabel }: { options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void; ariaLabel?: string }) {
  return <div className="segmented" role="group" aria-label={ariaLabel}>
    {options.map((option) => <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>
}
