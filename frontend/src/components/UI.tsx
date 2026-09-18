import { AlertCircle, ChevronLeft, ChevronRight, LoaderCircle, RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'
import { label } from '../api/format'

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-header">
    <div>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {description && <p className="page-description">{description}</p>}
    </div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>
}

export function LoadingState({ label: text = 'Chargement des données…' }: { label?: string }) {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" /><strong>{text}</strong><span>Interrogation sécurisée du Gateway.</span></div>
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : undefined
  return <div className="state-panel error-state" role="alert">
    <AlertCircle />
    <strong>{apiError?.status === 403 ? 'Accès non autorisé' : 'Impossible de charger les données'}</strong>
    <span>{error instanceof Error ? error.message : 'Une erreur inattendue est survenue.'}</span>
    {apiError?.correlationId && <small>Référence : {apiError.correlationId}</small>}
    {onRetry && <button className="button secondary" type="button" onClick={onRetry}><RotateCcw size={16} /> Réessayer</button>}
  </div>
}

export function EmptyState({ title = 'Aucune donnée', message = 'Aucun élément ne correspond aux critères actuels.' }: { title?: string; message?: string }) {
  return <div className="state-panel empty-state"><strong>{title}</strong><span>{message}</span></div>
}

export function Badge({ value, tone }: { value?: string | null; tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }) {
  const inferred = tone || (value === 'HIGH' || value === 'P1' || value === 'ACTIVE' ? 'success' : value === 'MEDIUM' || value === 'P2' ? 'warning' : value === 'LOW' || value === 'P3' ? 'neutral' : 'info')
  return <span className={`badge ${inferred}`}>{label(value)}</span>
}

export function Confidence({ value, level }: { value: number; level?: string }) {
  const percent = Math.round(value * 100)
  return <div className="confidence" aria-label={`Confiance ${percent} pour cent`}>
    <div className="confidence-head"><strong>{percent}%</strong>{level && <span>{label(level)}</span>}</div>
    <div className="confidence-track"><i style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} /></div>
  </div>
}

export interface CursorState {
  cursors: Array<string | undefined>
  index: number
}

export function CursorPagination({ state, hasMore, onChange }: { state: CursorState; hasMore: boolean; onChange: (next: CursorState) => void }) {
  return <nav className="pagination" aria-label="Pagination">
    <button type="button" className="button secondary" disabled={state.index === 0} onClick={() => onChange({ ...state, index: state.index - 1 })}><ChevronLeft size={16} /> Précédent</button>
    <span>Page {state.index + 1}</span>
    <button type="button" className="button secondary" disabled={!hasMore} onClick={() => onChange({ ...state, index: state.index + 1 })}>Suivant <ChevronRight size={16} /></button>
  </nav>
}

export function SkeletonRows({ count = 5 }: { count?: number }) {
  return <div className="skeleton-list" role="status" aria-label="Chargement">{Array.from({ length: count }, (_, index) => <div className="skeleton" key={index} />)}</div>
}

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header><h2 id="modal-title">{title}</h2><button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">×</button></header>
      {children}
    </section>
  </div>
}
