import { ArrowLeft, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

export function ForbiddenPage() {
  return <div className="status-page"><ShieldAlert /><p className="eyebrow">ACCÈS REFUSÉ</p><h1>Cette page est réservée à un autre rôle.</h1><p>Votre identité est valide, mais votre rôle ou votre périmètre ne permet pas cette opération.</p><Link className="button primary" to="/"><ArrowLeft size={16} /> Revenir au dashboard</Link></div>
}

export function NotFoundPage() {
  return <div className="status-page"><p className="eyebrow">ERREUR 404</p><h1>Page introuvable</h1><p>L’adresse demandée ne correspond à aucun écran de l’application.</p><Link className="button primary" to="/"><ArrowLeft size={16} /> Revenir au dashboard</Link></div>
}
