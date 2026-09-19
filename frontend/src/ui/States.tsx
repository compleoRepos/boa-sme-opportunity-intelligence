import { AlertCircle, Inbox, RotateCcw, SearchX } from 'lucide-react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'
import { Button } from './Button'

export function Skeleton({ kind = 'text', style, className = '' }: { kind?: 'text' | 'title' | 'block' | 'row' | 'circle'; style?: React.CSSProperties; className?: string }) {
  return <div className={`skeleton ${kind} ${className}`} style={style} aria-hidden="true" />
}

export function SkeletonStack({ rows = 4, kind = 'row' }: { rows?: number; kind?: 'row' | 'block' | 'text' }) {
  return <div className="skeleton-stack" role="status" aria-label="Chargement">{Array.from({ length: rows }, (_, index) => <Skeleton kind={kind} key={index} />)}</div>
}

export function EmptyState({ title = 'Aucune donnée', message, icon, action, compact }: { title?: string; message?: ReactNode; icon?: ReactNode; action?: ReactNode; compact?: boolean }) {
  return <div className={`state ${compact ? 'compact' : ''}`}>{icon ?? <Inbox />}<strong>{title}</strong>{message && <span>{message}</span>}{action}</div>
}

export function NoResults({ message = 'Modifiez les filtres ou élargissez la période.' }: { message?: string }) {
  return <EmptyState title="Aucun résultat" message={message} icon={<SearchX />} compact />
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const apiError = error instanceof ApiError ? error : undefined
  const title = apiError?.status === 403 ? 'Accès non autorisé' : apiError?.status === 404 ? 'Ressource introuvable' : apiError?.status === 0 ? 'Gateway injoignable' : 'Chargement impossible'
  return <div className={`state error ${compact ? 'compact' : ''}`} role="alert">
    <AlertCircle />
    <strong>{title}</strong>
    <span>{error instanceof Error ? error.message : 'Une erreur inattendue est survenue.'}</span>
    {apiError?.correlationId && <small>Référence {apiError.correlationId}</small>}
    {onRetry && <Button size="sm" onClick={onRetry} icon={<RotateCcw size={14} />}>Réessayer</Button>}
  </div>
}
