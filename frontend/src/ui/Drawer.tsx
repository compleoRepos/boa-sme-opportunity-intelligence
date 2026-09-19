import { X } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { IconButton } from './Button'
import { useDialogA11y } from './useDialogA11y'

export function Drawer({ title, eyebrow, onClose, children, footer, size = 'md', tools, 'data-demo': demo }: { title: ReactNode; eyebrow?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; size?: 'narrow' | 'md' | 'wide'; tools?: ReactNode; 'data-demo'?: string }) {
  const titleId = useId()
  const dialogRef = useDialogA11y<HTMLElement>(onClose)

  return createPortal(<>
    <div className="drawer-backdrop" onClick={onClose} role="presentation" aria-hidden="true" />
    <aside ref={dialogRef} className={`drawer ${size === 'md' ? '' : size}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} data-demo={demo}>
      <header className="drawer-head">
        <div className="drawer-title">{eyebrow && <p className="eyebrow accent">{eyebrow}</p>}<h2 id={titleId}>{title}</h2></div>
        {tools}
        <IconButton label="Fermer" onClick={onClose}><X size={18} /></IconButton>
      </header>
      <div className="drawer-body">{children}</div>
      {footer && <footer className="drawer-foot">{footer}</footer>}
    </aside>
  </>, document.body)
}
