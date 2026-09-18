import { ArrowRight, LockKeyhole, ShieldCheck, TrendingUp } from 'lucide-react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { LoadingState } from '../components/UI'

export function LoginPage() {
  const auth = useAuth()
  const location = useLocation()
  if (!auth.initialized) return <div className="center-screen"><LoadingState label="Initialisation de la session sécurisée…" /></div>
  if (auth.authenticated) return <Navigate to={(location.state as { from?: string } | null)?.from || '/'} replace />

  return <main className="login-page">
    <section className="login-brand-panel">
      <div className="login-brand"><span className="brand-mark"><span>BOA</span></span><div><strong>BANK OF AFRICA</strong><small>SME Opportunity Intelligence</small></div></div>
      <div className="login-copy"><p className="eyebrow light">RELATIONSHIP MANAGEMENT</p><h1>Transformez les signaux bancaires en conversations utiles.</h1><p>Une lecture claire, explicable et priorisée des opportunités commerciales de votre portefeuille PME.</p></div>
      <div className="login-feature-grid"><div><TrendingUp /><strong>Signaux actionnables</strong><span>Détectés à partir des flux du Gateway.</span></div><div><ShieldCheck /><strong>Décisions explicables</strong><span>Pourquoi, quoi, quand et avec quelle confiance.</span></div></div>
      <p className="login-disclaimer">Les données du MVP sont synthétiques. Le signal de tension financière est relationnel et ne constitue pas une décision de crédit.</p>
    </section>
    <section className="login-form-panel">
      <div className="login-card"><span className="login-lock"><LockKeyhole /></span><p className="eyebrow">ACCÈS SÉCURISÉ</p><h2>Bienvenue</h2><p>Connectez-vous avec votre identité BOA pour accéder à votre périmètre autorisé.</p><button className="button primary wide" type="button" onClick={() => void auth.login((location.state as { from?: string } | null)?.from || '/')}><span>Se connecter avec Keycloak</span><ArrowRight size={18} /></button><div className="security-line"><ShieldCheck size={16} /> OAuth 2.0 / OpenID Connect · PKCE</div></div>
    </section>
  </main>
}
