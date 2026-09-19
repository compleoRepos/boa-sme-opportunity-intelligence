import { ArrowLeft, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

export function ForbiddenPage() {
  return <div className="status-page"><ShieldAlert size={32} style={{ margin: '0 auto', color: 'var(--red-600)' }} /><p className="eyebrow">Accès refusé</p><h1>Cette page est réservée à un autre rôle.</h1><p className="muted">Votre identité est valide, mais votre rôle ou votre périmètre ne permet pas cette opération.</p><Link className="btn primary" to="/" style={{ justifySelf: 'center' }}><ArrowLeft size={16} /> Revenir au cockpit</Link></div>
}

export function NotFoundPage() {
  return <div className="status-page"><p className="eyebrow">Erreur 404</p><h1>Page introuvable</h1><p className="muted">L’adresse demandée ne correspond à aucun écran de l’application.</p><Link className="btn primary" to="/" style={{ justifySelf: 'center' }}><ArrowLeft size={16} /> Revenir au cockpit</Link></div>
}
