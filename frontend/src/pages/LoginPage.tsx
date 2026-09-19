import { ArrowRight, LockKeyhole, ShieldCheck, Sparkles, TrendingUp, UserRound } from 'lucide-react'
import { Navigate, useLocation } from 'react-router-dom'
import { initials } from '../api/format'
import { useAuth } from '../auth/AuthProvider'
import { Button } from '../ui'

export function LoginPage() {
  const auth = useAuth()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/'
  if (!auth.initialized) return <div className="center-screen"><p className="muted">Initialisation de la session sécurisée…</p></div>
  if (auth.authenticated) return <Navigate to={from} replace />
  return <main className="login">
    <section className="login-brand">
      <div className="brand" style={{ padding: 0, border: 0 }}><span className="brand-mark">BOA</span><div><strong>BANK OF AFRICA</strong><small>SME Opportunity Intelligence</small></div></div>
      <div>
        <p className="eyebrow" style={{ color: '#8fb4ff' }}>Intelligence commerciale PME</p>
        <h1>Transformez les signaux bancaires en conversations utiles.</h1>
        <p>Une lecture claire, explicable et priorisée des opportunités commerciales de chaque portefeuille PME : signaux, règles métier, propension ML et actions, dans un seul cockpit.</p>
        <div className="login-features">
          <div><TrendingUp size={18} /><strong>Signaux chiffrés</strong><span>Détectés sur les flux réels, comparés à l’historique.</span></div>
          <div><ShieldCheck size={18} /><strong>Décisions explicables</strong><span>Règle déclenchée, versions du moteur, propension.</span></div>
          <div><Sparkles size={18} /><strong>Action immédiate</strong><span>Contact, offre, conversion : audités via l’API.</span></div>
          <div><UserRound size={18} /><strong>Périmètre maîtrisé</strong><span>RBAC OIDC : portefeuille, agence, back office.</span></div>
        </div>
      </div>
      <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>Environnement de démonstration · données synthétiques · aucune décision de crédit.</p>
    </section>
    <section className="login-form">
      <div className="login-card">
        <span className="kpi-icon" style={{ background: 'var(--blue-50)', color: 'var(--accent)' }}><LockKeyhole size={20} /></span>
        <div><p className="eyebrow">Accès sécurisé</p><h2>Bienvenue</h2><p className="muted">{auth.devMode ? 'Mode démonstration sans Keycloak : choisissez une persona pour rejouer un périmètre réel via le Gateway.' : 'Connectez-vous avec votre identité BOA pour accéder à votre périmètre autorisé.'}</p></div>
        {auth.devMode ? <div className="persona-grid">{auth.personas.map((persona) => <button type="button" key={persona.id} className="persona" onClick={() => auth.selectPersona(persona.id)}><span className="avatar">{initials(persona.displayName)}</span><span><strong>{persona.label}</strong><span>{persona.description}</span></span><ArrowRight size={16} style={{ marginLeft: 'auto', color: 'var(--ink-400)' }} /></button>)}</div>
          : <Button variant="primary" size="lg" wide onClick={() => void auth.login(from)} icon={<ArrowRight size={18} />}>Se connecter avec Keycloak</Button>}
        <p className="muted" style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}><ShieldCheck size={14} /> OAuth 2.0 / OpenID Connect · PKCE · RBAC par périmètre</p>
      </div>
    </section>
  </main>
}
