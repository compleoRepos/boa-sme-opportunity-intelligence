import { ChevronLeft, ChevronRight, Play, Sparkles, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, IconButton } from '../../ui'

/**
 * Parcours de démonstration guidé (5 minutes). Chaque étape navigue réellement dans le produit
 * et met en évidence une zone (attribut data-demo). Aucune donnée n'est simulée : les écrans
 * affichent ce que le Gateway retourne pour la persona active.
 */
export interface DemoStep {
  id: string
  route?: string
  persona?: 'cc' | 'agence' | 'backoffice' | 'approbateur'
  target?: string
  title: string
  say: string
  value: string
  action?: string
}

export const DEMO_STEPS: DemoStep[] = [
  { id: 'dashboard', route: '/', persona: 'cc', target: 'kpis', title: 'Dashboard CC', say: '« Ahmed ouvre son cockpit : combien de PME je gère, combien présentent un signal, lesquelles regarder aujourd’hui. »', value: 'Lecture en 5 secondes, portefeuille limité au périmètre du CC (RBAC).', action: 'Observer les 4 KPI et la file « À regarder aujourd’hui ».' },
  { id: 'priorities', route: '/', persona: 'cc', target: 'priorities', title: 'Priorités du jour', say: '« Chaque ligne est une carte d’information : signaux chiffrés, propension, produit potentiel, date de détection. »', value: 'Le CC n’a rien à chercher : le produit lui présente le pourquoi.', action: 'Cliquer sur la première PME de la liste.' },
  { id: 'sheet', target: 'health', title: 'Fiche PME', say: '« Voici ce qui change dans son activité : encaissements, fournisseurs, transactions, international. »', value: 'Transition fluide, contexte conservé dans le rail de gauche : un cockpit unique.', action: 'Changer la période (30 j / 90 j / 6 mois / 12 mois) sur le graphique.' },
  { id: 'why', target: 'why', title: 'Pourquoi cette opportunité ?', say: '« Signaux détectés → règle métier déclenchée → propension ML → opportunité. Rien n’est une boîte noire. »', value: 'Explicabilité complète, versions du moteur et de la règle visibles.', action: 'Cliquer sur « Voir l’opportunité » puis sur le score de propension.' },
  { id: 'action', target: 'action', title: 'Action commerciale', say: '« Ahmed décide : à contacter. L’action est enregistrée, auditée, et le dashboard se met à jour. »', value: 'Boucle de feedback recommandation → action → outcome.', action: 'Enregistrer « À contacter », puis revenir au dashboard.' },
  { id: 'branch', route: '/', persona: 'agence', target: 'branch', title: 'Dashboard agence', say: '« Salma voit son agence : opportunités par CC, par secteur, par produit, actions et résultats. »', value: 'Pilotage commercial consolidé, drill-down jusqu’à l’opportunité.', action: 'Cliquer sur un chargé de clientèle puis sur une PME.' },
  { id: 'studio', route: '/back-office/regles/SME_INVESTMENT_001', persona: 'backoffice', target: 'rule', title: 'Rule Studio', say: '« Le métier lit la règle en clair : SI encaissements +25 % ET fournisseurs +20 % ALORS financement d’investissement. »', value: 'Règles versionnées, sans code, avec cycle d’approbation.', action: 'Ouvrir « Modifier », changer un seuil, puis lancer la simulation.' },
  { id: 'simulation', target: 'simulation', title: 'Simulation & soumission', say: '« 500 PME analysées, impact estimé par secteur et par région, puis soumission à approbation. »', value: 'Les résultats viennent de l’API de simulation, jamais inventés.', action: 'Lancer la simulation, lire l’impact, puis « Soumettre à approbation ».' },
  { id: 'approval', route: '/back-office/regles/SME_INVESTMENT_001', persona: 'approbateur', target: 'rule', title: 'Approbation & publication', say: '« Nadia, approbatrice distincte, relit la règle et la publie : le moteur l’exécutera au prochain recalcul. »', value: 'Séparation des tâches imposée par le service : un auteur ne peut pas approuver sa propre règle.', action: 'Approuver → Publier, puis consulter Versions & audit.' },
  { id: 'ml', route: '/back-office/modeles', persona: 'backoffice', target: 'models', title: 'ML Governance', say: '« Le modèle de propension est enregistré, versionné, avec ses métriques et son mode POC assistif. »', value: 'Le ML complète les règles, il ne décide pas du crédit.', action: 'Ouvrir la version active et son historique.' },
]

interface DemoContextValue {
  active: boolean
  index: number
  step?: DemoStep
  start: () => void
  stop: () => void
  next: () => void
  previous: () => void
}

const DemoContext = createContext<DemoContextValue | null>(null)

export function DemoProvider({ children, onPersona }: { children: ReactNode; onPersona?: (persona: DemoStep['persona']) => void }) {
  const [active, setActive] = useState(false)
  const [index, setIndex] = useState(0)
  const navigate = useNavigate()
  const step = active ? DEMO_STEPS[index] : undefined

  const goTo = useCallback((nextIndex: number) => {
    const target = DEMO_STEPS[nextIndex]
    if (!target) return
    setIndex(nextIndex)
    if (target.persona) onPersona?.(target.persona)
    if (target.route) navigate(target.route)
  }, [navigate, onPersona])

  const value = useMemo<DemoContextValue>(() => ({
    active,
    index,
    step,
    start: () => { setActive(true); goTo(0) },
    stop: () => { setActive(false); setIndex(0) },
    next: () => goTo(Math.min(DEMO_STEPS.length - 1, index + 1)),
    previous: () => goTo(Math.max(0, index - 1)),
  }), [active, index, step, goTo])

  useEffect(() => {
    document.body.dataset.demoTarget = step?.target || ''
    return () => { delete document.body.dataset.demoTarget }
  }, [step])

  return <DemoContext.Provider value={value}>{children}{active && <DemoPanel />}</DemoContext.Provider>
}

export function useDemo() {
  const context = useContext(DemoContext)
  if (!context) throw new Error('useDemo doit être utilisé dans DemoProvider')
  return context
}

function DemoPanel() {
  const demo = useDemo()
  const location = useLocation()
  const step = demo.step
  if (!step) return null
  const last = demo.index === DEMO_STEPS.length - 1
  return <aside className="demo-panel" role="complementary" aria-label="Parcours de démonstration">
    <header>
      <span className="demo-kicker"><Sparkles size={14} /> Démo guidée · étape {demo.index + 1}/{DEMO_STEPS.length}</span>
      <IconButton label="Quitter la démo" size="sm" onClick={demo.stop}><X size={16} /></IconButton>
    </header>
    <h3>{step.title}</h3>
    <p className="demo-say">{step.say}</p>
    <dl>
      <div><dt>Valeur démontrée</dt><dd>{step.value}</dd></div>
      {step.action && <div><dt>Action</dt><dd>{step.action}</dd></div>}
    </dl>
    <div className="demo-progress" aria-hidden="true">{DEMO_STEPS.map((item, position) => <i key={item.id} className={position <= demo.index ? 'on' : ''} />)}</div>
    <footer>
      <Button size="sm" variant="ghost" onClick={demo.previous} disabled={demo.index === 0} icon={<ChevronLeft size={14} />}>Précédent</Button>
      <span className="muted mono">{location.pathname}</span>
      {last ? <Button size="sm" variant="primary" onClick={demo.stop}>Terminer</Button> : <Button size="sm" variant="primary" onClick={demo.next} icon={<ChevronRight size={14} />}>Suivant</Button>}
    </footer>
  </aside>
}

export function DemoLauncher() {
  const demo = useDemo()
  if (demo.active) return null
  return <Button size="sm" variant="soft" onClick={demo.start} icon={<Play size={14} />} title="Parcours de démonstration guidé (5 minutes)">Démo 5 min</Button>
}
