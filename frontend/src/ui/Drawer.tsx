import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { IconButton } from './Button'

export function Drawer({ title, eyebrow, onClose, children, footer, size = 'md', tools, 'data-demo': demo }: { title: ReactNode; eyebrow?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; size?: 'narrow' | 'md' | 'wide'; tools?: ReactNode; 'data-demo'?: string }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = previous }
  }, [onClose])
  return createPortal(<>
    <div className="drawer-backdrop" onClick={onClose} role="presentation" />
    <aside className={`drawer ${size === 'md' ? '' : size}`} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined} data-demo={demo}>
      <header className="drawer-head">
        <div className="drawer-title">{eyebrow && <p className="eyebrow accent">{eyebrow}</p>}<h2>{title}</h2></div>
        {tools}
        <IconButton label="Fermer" onClick={onClose}><X size={18} /></IconButton>
      </header>
      <div className="drawer-body">{children}</div>
      {footer && <footer className="drawer-foot">{footer}</footer>}
    </aside>
  </>, document.body)
}
