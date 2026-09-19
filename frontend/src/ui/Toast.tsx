import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type ToastKind = 'success' | 'error' | 'info'
interface ToastItem { id: number; kind: ToastKind; title: string; detail?: string }
interface ToastApi { push: (kind: ToastKind, title: string, detail?: string) => void }

const ToastContext = createContext<ToastApi | null>(null)
const icons = { success: CheckCircle2, error: AlertCircle, info: Info }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const dismiss = useCallback((id: number) => setItems((list) => list.filter((item) => item.id !== id)), [])
  const push = useCallback((kind: ToastKind, title: string, detail?: string) => {
    const id = Date.now() + Math.random()
    setItems((list) => [...list.slice(-3), { id, kind, title, detail }])
    window.setTimeout(() => dismiss(id), kind === 'error' ? 7000 : 3800)
  }, [dismiss])
  const api = useMemo(() => ({ push }), [push])
  return <ToastContext.Provider value={api}>
    {children}
    {createPortal(<div className="toast-stack" aria-live="polite" aria-atomic="false">
      {items.map((item) => { const Icon = icons[item.kind]; return <div className={`toast ${item.kind}`} key={item.id} role="status"><Icon size={18} /><div><strong>{item.title}</strong>{item.detail && <span>{item.detail}</span>}</div><button type="button" onClick={() => dismiss(item.id)} aria-label="Fermer la notification" tabIndex={document.body.classList.contains('dialog-open') ? -1 : 0}><X size={14} /></button></div> })}
    </div>, document.body)}
  </ToastContext.Provider>
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast doit être utilisé dans ToastProvider')
  return context
}
