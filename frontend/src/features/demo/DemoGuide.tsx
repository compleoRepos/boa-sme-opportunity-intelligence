import { CheckCircle2, ChevronLeft, ChevronRight, Circle, Play, RotateCcw, Sparkles, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, IconButton } from '../../ui'

const PROGRESS_KEY = 'boa-sme-demo-progress-v1'

/**
 * Parcours de démonstration guidé. Chaque étape navigue réellement dans le produit et met en
 * évidence une zone (attribut data-demo). Les six actes persistent localement dans le navigateur.
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

export interface DemoAct {
  id: string
  title: string
  stepIds: string[]
}

export const DEMO_STEPS: DemoStep[] = [
  { id: 'dashboard', route: '/', persona: 'cc', target: 'kpis', title: 'Dashboard CC', say: '« Ahmed ouvre son cockpit : combien de PME je gère, combien présentent un signal, lesquelles regarder aujourd’hui. »', value: 'Lecture en 5 secondes, portefeuille limité au périmètre du CC (RBAC).', action: 'Observer les 4 KPI et la file « À regarder aujourd’hui ».' },
  { id: 'priorities', route: '/', persona: 'cc', target: 'priorities', title: 'Priorités du jour', say: '« Chaque ligne est une carte d’information : priorité issue des règles, signaux chiffrés, propension shadow, produit potentiel et date de détection. »', value: 'La propension est affichée séparément et ne modifie pas l’ordre de travail.', action: 'Cliquer sur la première PME de la liste.' },
  { id: 'sheet', target: 'health', title: 'Fiche PME', say: '« Voici ce qui change dans son activité : encaissements, fournisseurs, transactions, international. »', value: 'Transition fluide, contexte conservé dans le rail de gauche : un cockpit unique.', action: 'Changer la période (30 j / 90 j / 6 mois / 12 mois) sur le graphique.' },
  { id: 'why', target: 'why', title: 'Pourquoi cette opportunité ?', say: '« Signaux détectés → règle métier déclenchée → opportunité, avec propension ML observée à part en shadow. Rien n’est une boîte noire. »', value: 'Explicabilité séparée : la règle décide de la priorité, le score reste une observation.', action: 'Cliquer sur « Voir l’opportunité » puis sur le score de propension.' },
  { id: 'action', target: 'action', title: 'Action commerciale', say: '« Ahmed décide : à contacter. L’action est enregistrée, auditée, et le dashboard se met à jour. »', value: 'Boucle de feedback recommandation → action → outcome.', action: 'Enregistrer « À contacter », puis revenir au dashboard.' },
  { id: 'branch', route: '/', persona: 'agence', target: 'branch', title: 'Dashboard agence', say: '« Salma voit son agence : opportunités par CC, par secteur, par produit, actions et résultats. »', value: 'Pilotage commercial consolidé, drill-down jusqu’à l’opportunité.', action: 'Cliquer sur un chargé de clientèle puis sur une PME.' },
  { id: 'studio', route: '/back-office/regles/SME_INVESTMENT_001', persona: 'backoffice', target: 'rule', title: 'Rule Studio', say: '« Le métier lit la règle en clair : SI encaissements +25 % ET fournisseurs +20 % ALORS financement d’investissement. »', value: 'Règles versionnées, sans code, avec cycle d’approbation.', action: 'Ouvrir « Modifier », changer un seuil, puis lancer la simulation.' },
  { id: 'simulation', target: 'simulation', title: 'Simulation & soumission', say: '« La population analysée et les impacts affichés proviennent de l’API, puis la règle est soumise à approbation. »', value: 'Les résultats viennent de l’API de simulation, jamais inventés.', action: 'Lancer la simulation, lire l’impact, puis « Soumettre à approbation ».' },
  { id: 'approval', route: '/back-office/regles/SME_INVESTMENT_001', persona: 'approbateur', target: 'rule', title: 'Approbation & publication', say: '« Nadia, approbatrice distincte, relit la règle et la publie : le moteur l’exécutera au prochain recalcul. »', value: 'Séparation des tâches imposée par le service : un auteur ne peut pas approuver sa propre règle.', action: 'Approuver → Publier, puis consulter Versions & audit.' },
  { id: 'ml', route: '/back-office/studio-ml', persona: 'backoffice', target: 'ml-studio', title: 'Studio ML gouverné', say: '« Le Studio ML expose les données, entraînements, comparaisons, simulations et validations sans activer le ML dans la priorité. »', value: 'Le modèle reste CPU-only, DEMO_ONLY et POC_SHADOW ; G1 à G4 restent bloquées sans preuves BOA.', action: 'Parcourir les six onglets et vérifier la frise de gouvernance.' },
]

export const DEMO_ACTS: DemoAct[] = [
  { id: 'cc-dashboard', title: 'Cockpit CC', stepIds: ['dashboard', 'priorities'] },
  { id: 'pme-explainability', title: 'Fiche PME & explication', stepIds: ['sheet', 'why'] },
  { id: 'commercial-action', title: 'Action & outcome', stepIds: ['action'] },
  { id: 'branch-dashboard', title: 'Pilotage agence', stepIds: ['branch'] },
  { id: 'rule-studio', title: 'Rule Studio gouverné', stepIds: ['studio', 'simulation', 'approval'] },
  { id: 'ml-studio', title: 'Studio ML gouverné', stepIds: ['ml'] },
]

function readProgress(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PROGRESS_KEY) || '[]')
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function actIndexForStep(stepId: string): number {
  return Math.max(0, DEMO_ACTS.findIndex((act) => act.stepIds.includes(stepId)))
}

interface DemoContextValue {
  active: boolean
  index: number
  step?: DemoStep
  completedActIds: string[]
  start: () => void
  stop: () => void
  next: () => void
  previous: () => void
  goToAct: (actIndex: number) => void
  completeCurrentAct: () => void
  resetProgress: () => void
}

const DemoContext = createContext<DemoContextValue | null>(null)

export function DemoProvider({ children, onPersona }: { children: ReactNode; onPersona?: (persona: DemoStep['persona']) => void }) {
  const [active, setActive] = useState(false)
  const [index, setIndex] = useState(0)
  const [completedActIds, setCompletedActIds] = useState<string[]>(readProgress)
  const navigate = useNavigate()
  const step = active ? DEMO_STEPS[index] : undefined

  useEffect(() => {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify(completedActIds))
  }, [completedActIds])

  const completeAct = useCallback((actId: string) => {
    setCompletedActIds((current) => current.includes(actId) ? current : [...current, actId])
  }, [])

  const goTo = useCallback((nextIndex: number) => {
    const target = DEMO_STEPS[nextIndex]
    if (!target) return
    setIndex(nextIndex)
    if (target.persona) onPersona?.(target.persona)
    if (target.route) navigate(target.route)
  }, [navigate, onPersona])

  const goToAct = useCallback((actIndex: number) => {
    const act = DEMO_ACTS[actIndex]
    if (!act) return
    const firstStepIndex = DEMO_STEPS.findIndex((candidate) => candidate.id === act.stepIds[0])
    if (firstStepIndex >= 0) goTo(firstStepIndex)
  }, [goTo])

  const value = useMemo<DemoContextValue>(() => ({
    active,
    index,
    step,
    completedActIds,
    start: () => {
      setActive(true)
      const firstIncomplete = DEMO_ACTS.findIndex((act) => !completedActIds.includes(act.id))
      goToAct(firstIncomplete >= 0 ? firstIncomplete : 0)
    },
    stop: () => setActive(false),
    next: () => {
      const currentActIndex = actIndexForStep(DEMO_STEPS[index]!.id)
      const nextIndex = Math.min(DEMO_STEPS.length - 1, index + 1)
      const nextActIndex = actIndexForStep(DEMO_STEPS[nextIndex]!.id)
      if (nextActIndex !== currentActIndex || nextIndex === index) completeAct(DEMO_ACTS[currentActIndex]!.id)
      goTo(nextIndex)
    },
    previous: () => goTo(Math.max(0, index - 1)),
    goToAct,
    completeCurrentAct: () => completeAct(DEMO_ACTS[actIndexForStep(DEMO_STEPS[index]!.id)]!.id),
    resetProgress: () => {
      if (!window.confirm('Réinitialiser la progression des six actes de démonstration ?')) return
      setCompletedActIds([])
      setIndex(0)
      window.localStorage.removeItem(PROGRESS_KEY)
    },
  }), [active, index, step, completedActIds, completeAct, goTo, goToAct])

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
  const currentActIndex = actIndexForStep(step.id)
  const currentAct = DEMO_ACTS[currentActIndex]!
  const currentActCompleted = demo.completedActIds.includes(currentAct.id)
  return <aside className="demo-panel" role="complementary" aria-label="Parcours de démonstration">
    <header>
      <span className="demo-kicker"><Sparkles size={14} /> Acte {currentActIndex + 1}/{DEMO_ACTS.length} · étape {demo.index + 1}/{DEMO_STEPS.length}</span>
      <IconButton label="Quitter la démo" size="sm" onClick={demo.stop}><X size={16} /></IconButton>
    </header>
    <ol className="demo-acts" aria-label="Progression des six actes">
      {DEMO_ACTS.map((act, position) => {
        const completed = demo.completedActIds.includes(act.id)
        return <li key={act.id} className={position === currentActIndex ? 'current' : completed ? 'completed' : ''}>
          <button type="button" onClick={() => demo.goToAct(position)} aria-current={position === currentActIndex ? 'step' : undefined}>
            {completed ? <CheckCircle2 size={15} /> : <Circle size={15} />}
            <span>{position + 1}. {act.title}</span>
          </button>
        </li>
      })}
    </ol>
    <div className="row between demo-act-tools">
      <Button size="sm" variant="soft" onClick={demo.completeCurrentAct} disabled={currentActCompleted} icon={<CheckCircle2 size={14} />}>{currentActCompleted ? 'Acte terminé' : 'Marquer terminé'}</Button>
      <IconButton label="Réinitialiser la progression" size="sm" onClick={demo.resetProgress}><RotateCcw size={15} /></IconButton>
    </div>
    <h3>{step.title}</h3>
    <p className="demo-say">{step.say}</p>
    <dl>
      <div><dt>Valeur démontrée</dt><dd>{step.value}</dd></div>
      {step.action && <div><dt>Action</dt><dd>{step.action}</dd></div>}
    </dl>
    <div className="demo-progress" aria-label={`${demo.completedActIds.length} acte(s) terminé(s) sur ${DEMO_ACTS.length}`}>{DEMO_ACTS.map((act) => <i key={act.id} className={demo.completedActIds.includes(act.id) ? 'on' : ''} />)}</div>
    <footer>
      <Button size="sm" variant="ghost" onClick={demo.previous} disabled={demo.index === 0} icon={<ChevronLeft size={14} />}>Précédent</Button>
      <span className="muted mono">{location.pathname}</span>
      {last ? <Button size="sm" variant="primary" onClick={() => { demo.completeCurrentAct(); demo.stop() }}>Terminer</Button> : <Button size="sm" variant="primary" onClick={demo.next} icon={<ChevronRight size={14} />}>Suivant</Button>}
    </footer>
  </aside>
}

export function DemoLauncher() {
  const demo = useDemo()
  if (demo.active) return null
  return <Button size="sm" variant="soft" onClick={demo.start} icon={<Play size={14} />} title="Parcours de démonstration guidé en six actes">Démo {demo.completedActIds.length}/{DEMO_ACTS.length}</Button>
}
