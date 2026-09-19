import { LoaderCircle } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'ghost' | 'soft' | 'success' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
  wide?: boolean
}

export function Button({ variant = 'secondary', size = 'md', loading, icon, wide, className = '', children, disabled, type = 'button', ...rest }: ButtonProps) {
  return <button type={type} className={`btn ${variant} ${size === 'md' ? '' : size} ${wide ? 'wide' : ''} ${className}`} disabled={disabled || loading} {...rest}>
    {loading ? <LoaderCircle size={16} className="btn-spinner" /> : icon}
    {children}
  </button>
}

export function IconButton({ label, className = '', size = 'md', children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; size?: 'sm' | 'md' }) {
  return <button type="button" className={`btn icon ${size === 'sm' ? 'sm' : ''} ${className}`} aria-label={label} title={label} {...rest}>{children}</button>
}

export function LinkButton({ to, variant = 'secondary', size = 'md', icon, className = '', children, ...rest }: { to: string; variant?: Variant; size?: Size; icon?: ReactNode; className?: string; children: ReactNode; state?: unknown; 'data-demo'?: string }) {
  return <Link to={to} className={`btn ${variant} ${size === 'md' ? '' : size} ${className}`} {...rest}>{icon}{children}</Link>
}
