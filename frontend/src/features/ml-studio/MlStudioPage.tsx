import {
  Activity, AlertTriangle, BarChart3, Check, CheckCircle2, ClipboardList, Cpu, Database,
  FlaskConical, Gauge, GitCompareArrows, LockKeyhole, Play, Plus, Save, Send, ShieldCheck,
  SlidersHorizontal, UploadCloud, XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { formatDate, formatNumber, formatPercent, label, safeJson } from '../../api/format'
import {
  useActiveScoringPolicy, useCancelMlTraining, useCreateMlManifest, useCreateScoringPolicy,
  useCreateScoringPolicyVersion, useMaterializeMlOutcomes, useMlGovernanceAudits,
  useMlGovernanceRuns, useMlManifests, useMlModelComparison, useMlStudioSummary,
  useMlTraining, useMlTrainingHistory, useRegisterMlRun, useStartMlTraining,
  useScoringPolicies, useTransitionMlRun, useTransitionScoringPolicy,
} from '../../api/mlStudioHooks'
import type {
  MlDatasetManifest, MlDatasetManifestInput, MlGovernanceRun, MlOutcomeMaterializationInput,
  MlOutcomeMaterializationResult, MlTrainingJob, ScoringPolicyVersionView,
} from '../../api/types'
import { useAuth } from '../../auth/AuthProvider'
import { Badge, Button, EmptyState, ErrorState, Modal, Panel, SkeletonStack, Tabs, tabId, useToast } from '../../ui'
import { MlWeightSlider } from './MlWeightSlider'
import { TrainingProgress } from './TrainingProgress'

const PANEL_ID = 'ml-studio-panel'
const TAB_ITEMS = [
  { id: 'overview', label: 'Vue d’ensemble', icon: <Gauge size={15} /> },
  { id: 'data', label: 'Données et étiquettes', icon: <Database size={15} /> },
  { id: 'training', label: 'Entraînement', icon: <Cpu size={15} /> },
  { id: 'comparison', label: 'Évaluation', icon: <GitCompareArrows size={15} /> },
  { id: 'policy', label: 'Fusion règles / ML', icon: <SlidersHorizontal size={15} /> },
  { id: 'approval', label: 'Approbation et journal', icon: <ClipboardList size={15} /> },
]

type TabId = typeof TAB_ITEMS[number]['id']
type DialogAction =
  | { kind: 'model'; run: MlGovernanceRun; transition: 'submit' | 'approve' | 'promote' }
  | { kind: 'policy'; policy: ScoringPolicyVersionView; transition: 'simulate' | 'submit' | 'approve' | 'publish' | 'activate' }

const isDemoRun = (run: MlGovernanceRun) => run.status === 'DEMO_ONLY' || run.sourceKind === 'DEMO_SYNTHETIC_LABELS'
const metricNumber = (metrics: Record<string, unknown> | undefined, key: string) => {
  const value = metrics?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}
const objectValue = (value: unknown): Record<string, unknown> | undefined => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined
const listValue = (value: unknown): Array<Record<string, unknown>> => Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object')) : []

export function MlStudioPage() {
  const [tab, setTab] = useState<TabId>(() => {
    const requested = new URLSearchParams(window.location.search).get('tab')
    return TAB_ITEMS.some((item) => item.id === requested) ? requested as TabId : 'overview'
  })
  const selectTab = (next: string) => {
    const value = next as TabId
    setTab(value)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', value)
    window.history.replaceState(null, '', `${url.pathname}${url.search}`)
  }
  return <>
    <header className="page-head ml-studio-head">
      <div><p className="eyebrow accent">Studio ML · gouvernance commerciale</p><h1>Analyser, entraîner, comparer, gouverner</h1><p className="subtitle">Un modèle entraîné ne modifie ni le champion, ni la politique active, ni les opportunités. Toute influence ML reste soumise aux portes G1 à G3.</p></div>
      <div className="ml-mode-lock"><LockKeyhole size={18} /><span><strong>POC_SHADOW</strong><small>Aucune activation automatique</small></span></div>
    </header>
    <div className="notice warning ml-guardrail"><AlertTriangle size={17} /><div><strong>Usage commercial uniquement.</strong> Les données de démonstration portent le statut <code>DEMO_ONLY</code> et ne sont jamais promouvables. Aucun LLM, aucun GPU, aucune décision de crédit.</div></div>
    <Tabs items={TAB_ITEMS} value={tab} onChange={selectTab} ariaLabel="Sections du Studio ML" panelId={PANEL_ID} />
    <section id={PANEL_ID} className="ml-tab-panel" role="tabpanel" aria-labelledby={tabId(PANEL_ID, tab)}>
      {tab === 'overview' && <OverviewTab />}
      {tab === 'data' && <DataTab />}
      {tab === 'training' && <TrainingTab />}
      {tab === 'comparison' && <ComparisonTab />}
      {tab === 'policy' && <PolicyTab />}
      {tab === 'approval' && <ApprovalTab />}
    </section>
  </>
}

function OverviewTab() {
  const query = useMlStudioSummary()
  if (query.isPending) return <SkeletonStack rows={4} kind="block" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  const summary = query.data
  return <div className="stack">
    <section className="grid cols-4 ml-summary-grid">
      <article className="kpi tone-blue"><span className="kpi-label">Mode actif</span><strong className="kpi-value compact">{label(summary.mode)}</strong><span className="kpi-note">Règles {formatPercent(summary.weights.rules)} · ML {formatPercent(summary.weights.ml)}</span></article>
      <article className="kpi tone-violet"><span className="kpi-label">Modèle champion</span><strong className="kpi-value compact">{summary.champion?.modelVersion || 'Aucun'}</strong><span className="kpi-note">{summary.champion ? `${summary.champion.status} · ${formatDate(summary.champion.updatedAt)}` : 'Aucun modèle actif'}</span></article>
      <article className="kpi tone-teal"><span className="kpi-label">Résultats / étiquettes matures</span><strong className="kpi-value num">{formatNumber(summary.labels.available)} / {formatNumber(summary.labels.mature)}</strong><span className="kpi-note">Valeurs calculées par l’API</span></article>
      <article className="kpi tone-orange"><span className="kpi-label">Dernière évaluation</span><strong className="kpi-value compact">{summary.latestEvaluation?.status || 'Aucune'}</strong><span className="kpi-note">Brier {formatNumber(summary.latestEvaluation?.brierScore, 4)} · ECE {formatNumber(summary.latestEvaluation?.expectedCalibrationError, 4)} · {formatDate(summary.latestEvaluation?.createdAt)}</span></article>
    </section>
    <Panel eyebrow="Portes d’acceptation" title="Pourquoi le ML n’influence pas encore les priorités" id="ml-gates">
      {!summary.gates.length ? <EmptyState compact title="Aucune porte exposée" /> : <ol className="ml-gates">
        {summary.gates.map((gate) => <li key={gate.gate} className={gate.status === 'PASSED' ? 'passed' : 'blocked'}>
          <span className="gate-icon" aria-hidden="true">{gate.status === 'PASSED' ? <CheckCircle2 /> : <XCircle />}</span>
          <div><p className="eyebrow">{gate.gate}</p><h3>{gate.label}</h3><Badge value={gate.status} tone={gate.status === 'PASSED' ? 'success' : 'danger'} />{gate.missingCondition && <p>{gate.missingCondition}</p>}<small className="muted">{gate.actor ? `Par ${gate.actor}` : 'Aucun acteur enregistré'} · {formatDate(gate.at, true)}</small></div>
        </li>)}
      </ol>}
    </Panel>
    <div className="notice neutral"><ShieldCheck size={17} /><div><strong>{summary.assumptions.status}</strong> Seuils fournis par l’API : {formatNumber(summary.assumptions.minimumExamples)} exemples, {formatNumber(summary.assumptions.minimumPositives)} positifs et poids ML maximal {formatPercent(summary.assumptions.maximumMlWeight)}.</div></div>
  </div>
}

function DataTab() {
  const auth = useAuth()
  const summary = useMlStudioSummary()
  const manifests = useMlManifests()
  const materialize = useMaterializeMlOutcomes()
  const createManifest = useCreateMlManifest()
  const [materializeOpen, setMaterializeOpen] = useState(false)
  const [manifestOpen, setManifestOpen] = useState(false)
  const [materialized, setMaterialized] = useState<MlOutcomeMaterializationResult>()
  const [created, setCreated] = useState<MlDatasetManifest>()
  const canWrite = auth.hasRole('ML_STEWARD') || auth.hasRole('ADMIN')
  return <div className="stack">
    <Panel eyebrow="Cibles versionnées" title="Définitions de cible" id="target-definitions" tools={canWrite && <div className="row wrap"><Button size="sm" icon={<Activity size={14} />} onClick={() => setMaterializeOpen(true)}>Matérialiser les étiquettes</Button><Button size="sm" variant="primary" icon={<Plus size={14} />} onClick={() => setManifestOpen(true)}>Constituer un jeu de données</Button></div>}>
      {summary.isPending ? <SkeletonStack rows={2} /> : summary.isError ? <ErrorState error={summary.error} compact onRetry={() => void summary.refetch()} /> : !summary.data.targetDefinitions.length ? <EmptyState compact title="Aucune définition de cible" /> : <div className="table-wrap"><table className="table"><thead><tr><th>Version</th><th>Nom</th><th>Cible</th><th>Horizon</th><th>Population</th><th>Statut</th></tr></thead><tbody>{summary.data.targetDefinitions.map((item) => <tr key={item.version}><td className="mono">{item.version}</td><td><strong>{item.name}</strong></td><td>{label(item.targetOutcome)}</td><td className="num">{formatNumber(item.horizonDays)} jours</td><td>{safeJson(item.population)}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div>}
    </Panel>
    {materialized && <Panel eyebrow="Dernière matérialisation" title={materialized.snapshotVersion}><div className="grid cols-4"><MiniMetric label="Résultats lus" value={materialized.sourceEventsRead} /><MiniMetric label="Étiquettes écrites" value={materialized.labelsWritten} /><MiniMetric label="Entraînement" value={materialized.trainingReady ? 'Prêt' : 'Bloqué'} /><MiniMetric label="Horizon" value={`${materialized.horizonDays} jours`} /></div><Blockers items={materialized.activationBlockers} /></Panel>}
    {created && <ManifestCard manifest={created} />}
    <Panel eyebrow="Point-in-time" title="Manifestes de jeu de données" id="ml-manifests">
      {manifests.isPending ? <SkeletonStack rows={3} /> : manifests.isError ? <ErrorState error={manifests.error} compact onRetry={() => void manifests.refetch()} /> : !manifests.data.data.length ? <EmptyState title="Aucun manifeste" message="Constituez un manifeste après matérialisation des étiquettes candidates." /> : <div className="manifest-grid">{manifests.data.data.map((manifest) => <ManifestCard key={manifest.manifestVersion} manifest={manifest} />)}</div>}
    </Panel>
    {materializeOpen && summary.data && <MaterializeDialog definition={summary.data.targetDefinitions[0]} pending={materialize.isPending} error={materialize.error} onClose={() => setMaterializeOpen(false)} onSubmit={(input) => materialize.mutate(input, { onSuccess: (result) => { setMaterialized(result); setMaterializeOpen(false) } })} />}
    {manifestOpen && summary.data && <ManifestDialog definition={summary.data.targetDefinitions[0]} pending={createManifest.isPending} error={createManifest.error} onClose={() => setManifestOpen(false)} onSubmit={(input) => createManifest.mutate(input, { onSuccess: (result) => { setCreated(result); setManifestOpen(false) } })} />}
  </div>
}

function ManifestCard({ manifest }: { manifest: MlDatasetManifest }) {
  const demo = manifest.sourceKind === 'DEMO_SYNTHETIC_LABELS'
  const checks = [
    { label: 'Source autorisée', ok: manifest.status !== 'BLOCKED', detail: manifest.sourceKind },
    { label: 'Unicité des observations', ok: manifest.status !== 'BLOCKED', detail: `${formatNumber(manifest.rowCount)} lignes` },
    { label: 'Aucune caractéristique postérieure', ok: manifest.status !== 'BLOCKED', detail: manifest.trainingCutoff },
    { label: 'Étiquette disponible après observation', ok: manifest.status !== 'BLOCKED', detail: `${formatNumber(manifest.horizonDays)} jours` },
  ]
  return <article className="manifest-card">
    <header className="row between wrap"><div><strong>{manifest.manifestVersion}</strong><small>{label(manifest.purpose)} · {label(manifest.targetOutcome)}</small></div><Badge value={demo ? 'DEMO_ONLY' : manifest.status} tone={demo ? 'warning' : undefined} /></header>
    {demo && <p className="demo-only-copy">Jeu de démonstration, étiquettes synthétiques, non promouvable.</p>}
    <ul className="check-list">{checks.map((check) => <li key={check.label} className={check.ok ? 'ok' : 'ko'}>{check.ok ? <Check size={15} /> : <XCircle size={15} />}<span>{check.label}<small>{check.detail}</small></span></li>)}</ul>
    <Blockers items={manifest.activationBlockers} />
  </article>
}

function TrainingTab() {
  const auth = useAuth()
  const toast = useToast()
  const manifests = useMlManifests()
  const history = useMlTrainingHistory()
  const start = useStartMlTraining()
  const cancel = useCancelMlTraining()
  const register = useRegisterMlRun()
  const [selectedId, setSelectedId] = useState<string>()
  const [manifestId, setManifestId] = useState('')
  const [seed, setSeed] = useState(20260921)
  const [justification, setJustification] = useState('Démonstration gouvernée de l’entraînement CPU')
  const current = useMlTraining(selectedId)
  const activeJob = current.data || history.data?.data.find((job) => !job.terminal)
  const trainable = (manifests.data?.data || []).filter((item) => item.status === 'TRAINING_READY' || item.sourceKind === 'DEMO_SYNTHETIC_LABELS')
  const selectedManifest = trainable.find((item) => item.id === manifestId)
  const canTrain = auth.hasRole('ML_STEWARD') || auth.hasRole('ADMIN')
  useEffect(() => { if (!selectedId && activeJob) setSelectedId(activeJob.id) }, [activeJob, selectedId])
  const submit = (event: FormEvent) => {
    event.preventDefault()
    start.mutate({ manifestId, algorithm: 'LOGISTIC_REGRESSION', seed, justification }, { onSuccess: (job) => { setSelectedId(job.id); toast.push('success', 'Entraînement placé dans la file CPU') } })
  }
  return <div className="stack">
    <div className="ml-two-columns">
      <Panel eyebrow="Nouveau job" title="Lancer un entraînement" id="new-training">
        {!canTrain ? <EmptyState compact title="Lecture seule" message="Le rôle ML_STEWARD ou ADMIN est requis pour lancer un entraînement." icon={<LockKeyhole />} /> : manifests.isPending ? <SkeletonStack rows={3} kind="text" /> : manifests.isError ? <ErrorState error={manifests.error} compact onRetry={() => void manifests.refetch()} /> : <form className="stack" onSubmit={submit}>
          <label className="field">Manifeste<select className="select" required value={manifestId} onChange={(event) => setManifestId(event.target.value)}><option value="">Sélectionner un manifeste éligible</option>{trainable.map((item) => <option key={item.manifestVersion} value={item.id}>{item.manifestVersion}{item.sourceKind === 'DEMO_SYNTHETIC_LABELS' ? ' · DÉMO NON PROMOUVABLE' : ''}</option>)}</select></label>
          {!trainable.length && <div className="notice neutral"><AlertTriangle size={16} /><div>Aucun manifeste <code>TRAINING_READY</code> ni jeu de démonstration n’est exposé.</div></div>}
          {selectedManifest?.sourceKind === 'DEMO_SYNTHETIC_LABELS' && <div className="notice warning"><AlertTriangle size={16} /><div>Ce job fonctionnera réellement, mais son artefact portera <code>DEMO_ONLY</code> et ne pourra être ni soumis, ni approuvé, ni promu.</div></div>}
          <label className="field">Algorithme<select className="select" value="LOGISTIC_REGRESSION" disabled><option>Régression logistique · CPU</option></select></label>
          <label className="field">Graine aléatoire<input className="input" type="number" min="0" max="2147483647" required value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
          <label className="field">Justification<textarea className="textarea" required minLength={8} maxLength={2000} rows={3} value={justification} onChange={(event) => setJustification(event.target.value)} /></label>
          {start.isError && <p className="form-error" role="alert">{start.error.message}</p>}
          <Button variant="primary" type="submit" icon={<Play size={15} />} loading={start.isPending} disabled={!manifestId || justification.trim().length < 8}>Lancer l’entraînement</Button>
        </form>}
      </Panel>
      <Panel eyebrow="Exécution persistée" title="Progression" id="training-progress">
        {selectedId && current.isPending ? <SkeletonStack rows={4} /> : current.isError ? <ErrorState error={current.error} compact onRetry={() => void current.refetch()} /> : activeJob ? <TrainingProgress job={activeJob} onCancel={canTrain ? () => cancel.mutate(activeJob.id) : undefined} cancelling={cancel.isPending} /> : <EmptyState title="Aucun entraînement sélectionné" message="Lancez un job ou choisissez-le dans l’historique. Le rafraîchissement s’arrête automatiquement à l’état terminal." icon={<Cpu />} />}
      </Panel>
    </div>
    {activeJob?.status === 'SUCCEEDED' && activeJob.result && <TrainingResultPanel job={activeJob} canRegister={canTrain} onRegister={() => register.mutate(activeJob.result!, { onSuccess: () => toast.push('success', 'Version candidate enregistrée dans le registre') })} registering={register.isPending} error={register.error} />}
    <Panel eyebrow="Historique" title="Entraînements persistés" id="training-history">
      {history.isPending ? <SkeletonStack rows={3} /> : history.isError ? <ErrorState error={history.error} compact onRetry={() => void history.refetch()} /> : !history.data.data.length ? <EmptyState compact title="Aucun entraînement" /> : <div className="table-wrap"><table className="table hover"><thead><tr><th>Date</th><th>Auteur</th><th>Manifeste</th><th>Statut</th><th>Progression</th><th>Version produite</th></tr></thead><tbody>{history.data.data.map((job) => <tr key={job.id} className={job.id === selectedId ? 'selected' : ''} tabIndex={0} onClick={() => setSelectedId(job.id)} onKeyDown={(event) => { if (event.key === 'Enter') setSelectedId(job.id) }}><td>{formatDate(job.createdAt, true)}</td><td>{job.author}</td><td className="mono">{job.manifestId}</td><td><Badge value={job.status} /></td><td className="num">{formatNumber(job.percentage)} %</td><td className="mono">{job.result?.modelVersion || '—'}</td></tr>)}</tbody></table></div>}
    </Panel>
  </div>
}

function TrainingResultPanel({ job, canRegister, onRegister, registering, error }: { job: MlTrainingJob; canRegister: boolean; onRegister: () => void; registering: boolean; error: Error | null }) {
  const result = job.result!
  const metrics = result.metrics
  const matrix = objectValue(metrics.confusionMatrix)
  const calibration = listValue(metrics.calibrationCurve)
  return <Panel eyebrow="Résultat descriptif" title={result.modelVersion} id="training-result" tools={<Button size="sm" variant="primary" icon={<Save size={14} />} onClick={onRegister} loading={registering} disabled={!canRegister}>Enregistrer comme version candidate</Button>}>
    <div className="grid cols-4"><MiniMetric label="Exemples de test" value={metricNumber(metrics, 'sampleCount')} /><MiniMetric label="Brier" value={formatNumber(metricNumber(metrics, 'brierScore'), 4)} /><MiniMetric label="ECE" value={formatNumber(metricNumber(metrics, 'expectedCalibrationError'), 4)} /><MiniMetric label="Statut registre" value={result.registryStatus} /></div>
    {result.registryStatus === 'DEMO_ONLY' && <Blockers items={result.promotionBlockers} />}
    <div className="ml-result-grid"><div><h3>Coefficients</h3><div className="table-wrap"><table className="table"><thead><tr><th>Caractéristique</th><th>Signe</th><th>Contribution</th></tr></thead><tbody>{result.artifact.featureOrder.map((feature) => { const coefficient = result.artifact.coefficients[feature] ?? 0; return <tr key={feature}><td>{label(feature)}</td><td>{coefficient >= 0 ? 'Positive' : 'Négative'}</td><td className="num">{formatNumber(coefficient, 4)}</td></tr> })}</tbody></table></div></div>
      <div><h3>Matrice de confusion · seuil {formatNumber(result.artifact.threshold, 2)}</h3>{matrix ? <div className="confusion-grid"><MiniMetric label="Vrais négatifs" value={String(matrix.tn ?? '—')} /><MiniMetric label="Faux positifs" value={String(matrix.fp ?? '—')} /><MiniMetric label="Faux négatifs" value={String(matrix.fn ?? '—')} /><MiniMetric label="Vrais positifs" value={String(matrix.tp ?? '—')} /></div> : <EmptyState compact title="Matrice indisponible" />}
      <h3>Calibration en déciles</h3>{calibration.length ? <div className="calibration-bars">{calibration.map((bin, index) => { const prediction = typeof bin.meanPrediction === 'number' ? bin.meanPrediction : 0; const observed = typeof bin.observedRate === 'number' ? bin.observedRate : 0; return <div key={String(bin.decile ?? index)}><span>D{String(bin.decile ?? index + 1)}</span><i title={`Prédiction ${formatPercent(prediction)}`} style={{ height: `${prediction * 100}%` }} /><b title={`Observé ${formatPercent(observed)}`} style={{ height: `${observed * 100}%` }} /></div> })}</div> : <EmptyState compact title="Courbe indisponible" />}</div>
    </div>
    {error && <p className="form-error" role="alert">{error.message}</p>}
  </Panel>
}

function ComparisonTab() {
  const runs = useMlGovernanceRuns()
  const [left, setLeft] = useState('')
  const [right, setRight] = useState('')
  useEffect(() => {
    if (!runs.data?.runs.length) return
    const champion = runs.data.runs.find((item) => item.status === 'CHAMPION')
    const candidate = runs.data.runs.find((item) => item.modelVersion !== champion?.modelVersion)
    setLeft((value) => value || champion?.modelVersion || runs.data!.runs[0]!.modelVersion)
    setRight((value) => value || candidate?.modelVersion || '')
  }, [runs.data])
  const comparison = useMlModelComparison(left, right)
  if (runs.isPending) return <SkeletonStack rows={4} kind="block" />
  if (runs.isError) return <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
  if (!runs.data.runs.length) return <EmptyState title="Aucun modèle enregistré" message="Enregistrez le résultat d’un entraînement pour l’évaluer et le comparer." />
  return <div className="stack">
    <Panel eyebrow="Même jeu de test" title="Choisir deux versions"><div className="form-grid two"><label className="field">Modèle A<select className="select" value={left} onChange={(event) => setLeft(event.target.value)}>{runs.data.runs.map((run) => <option key={`a-${run.modelVersion}`} value={run.modelVersion}>{run.modelVersion} · {run.status}</option>)}</select></label><label className="field">Modèle B<select className="select" value={right} onChange={(event) => setRight(event.target.value)}><option value="">Sélectionner une autre version</option>{runs.data.runs.filter((run) => run.modelVersion !== left).map((run) => <option key={`b-${run.modelVersion}`} value={run.modelVersion}>{run.modelVersion} · {run.status}</option>)}</select></label></div></Panel>
    {!right ? <EmptyState title="Deux versions sont nécessaires" message="La comparaison ne calcule rien tant que deux versions distinctes ne sont pas sélectionnées." /> : comparison.isPending ? <SkeletonStack rows={4} kind="block" /> : comparison.isError ? <ErrorState error={comparison.error} onRetry={() => void comparison.refetch()} /> : !comparison.data.comparable ? <div className="notice danger" role="alert"><XCircle size={17} /><div><strong>{comparison.data.reason || 'Comparaison impossible'}</strong>{comparison.data.message}</div></div> : <>
      <section className="grid cols-4"><MiniMetric label="Jeu de test commun" value={comparison.data.testDataset || '—'} /><MiniMetric label="Exemples test" value={comparison.data.testCount} /><MiniMetric label="Priorités modifiées" value={formatPercent(comparison.data.rankingChangeRate, 1)} /><MiniMetric label="Versions comparées" value={comparison.data.models?.length} /></section>
      <div className="grid cols-2">{comparison.data.models?.map((model) => <Panel key={model.modelVersion} eyebrow={model.status} title={model.modelVersion}><MetricList metrics={model.metrics} /></Panel>)}</div>
      <Panel eyebrow="Écart de classement" title="Dix plus grands changements">{!comparison.data.largestChanges?.length ? <EmptyState compact title="Aucun changement de priorité" /> : <div className="table-wrap"><table className="table"><thead><tr><th>PME</th><th>Score A</th><th>Score B</th><th>Priorité</th><th>Écart</th><th>Contributions principales</th></tr></thead><tbody>{comparison.data.largestChanges.map((item) => <tr key={item.entityRef}><td className="mono">{item.entityRef}</td><td className="num">{formatPercent(item.leftScore, 1)}</td><td className="num">{formatPercent(item.rightScore, 1)}</td><td>{item.leftPriority} → {item.rightPriority}</td><td className="num">{formatPercent(item.absoluteDifference, 1)}</td><td>{item.contributions.map((part) => `${label(part.feature)} ${formatNumber(part.left, 3)}→${formatNumber(part.right, 3)}`).join(' · ')}</td></tr>)}</tbody></table></div>}</Panel>
    </>}
  </div>
}

function PolicyTab() {
  const auth = useAuth()
  const toast = useToast()
  const policies = useScoringPolicies()
  const active = useActiveScoringPolicy()
  const createPolicy = useCreateScoringPolicy()
  const [policyId, setPolicyId] = useState('')
  const selectedPolicy = policies.data?.data.find((item) => item.policyId === policyId) || policies.data?.data[0]
  const createVersion = useCreateScoringPolicyVersion(selectedPolicy?.policyId || '')
  const transition = useTransitionScoringPolicy()
  const [mlWeight, setMlWeight] = useState(10)
  const [reason, setReason] = useState('Évaluer une fusion gouvernée sans activation automatique')
  const [created, setCreated] = useState<ScoringPolicyVersionView>()
  const [dialog, setDialog] = useState<DialogAction>()
  const [newPolicyId, setNewPolicyId] = useState('commercial-propensity')
  const canAuthor = auth.hasRole('ML_STEWARD') || auth.hasRole('ADMIN')
  const g3 = useMlStudioSummary()
  useEffect(() => { if (!policyId && policies.data?.data[0]) setPolicyId(policies.data.data[0].policyId) }, [policies.data, policyId])
  const target = created || selectedPolicy?.versions.at(-1)
  const create = (event: FormEvent) => {
    event.preventDefault()
    const weights = { rules: (100 - mlWeight) / 100, ml: mlWeight / 100 }
    if (selectedPolicy) createVersion.mutate({ weights, reason }, { onSuccess: (value) => { setCreated(value); toast.push('success', `Version ${value.version} créée`) } })
    else createPolicy.mutate({ policyId: newPolicyId, weights, reason }, { onSuccess: (value) => { setPolicyId(value.policyId); setCreated(value.versions[0]); toast.push('success', 'Politique créée') } })
  }
  const executeDialog = (dialogValue: DialogAction, dialogReason: string) => {
    if (dialogValue.kind !== 'policy') return
    transition.mutate({ policyId: dialogValue.policy.policyId, version: dialogValue.policy.version, transition: dialogValue.transition, reason: dialogReason, simulationId: dialogValue.transition === 'simulate' ? crypto.randomUUID() : undefined, effectiveFrom: dialogValue.transition === 'activate' ? new Date().toISOString() : undefined }, { onSuccess: (value) => { setCreated(value); setDialog(undefined); toast.push('success', `Politique ${label(value.status).toLowerCase()}`) } })
  }
  const gate3 = g3.data?.gates.find((gate) => gate.gate === 'G3')
  return <div className="stack">
    <Panel eyebrow="Politique active" title={active.data ? `${active.data.policyId} · v${active.data.version}` : 'Aucune politique active'}>{active.isPending ? <SkeletonStack rows={2} kind="text" /> : active.isError ? <EmptyState compact title="Aucune version active" message="L’API ne retourne aucune politique effective ; aucune valeur n’est substituée dans l’interface." /> : <div className="grid cols-4"><MiniMetric label="Mode" value={active.data.operationalMode || '—'} /><MiniMetric label="Règles" value={formatPercent(active.data.weights.rules)} /><MiniMetric label="ML" value={formatPercent(active.data.weights.ml)} /><MiniMetric label="Approbateur" value={active.data.approverId || '—'} /></div>}</Panel>
    <div className="ml-two-columns">
      <Panel eyebrow="Nouvelle version" title="Ratio règles / ML" id="ml-policy-form">
        {policies.isPending ? <SkeletonStack rows={4} kind="text" /> : policies.isError ? <ErrorState error={policies.error} compact onRetry={() => void policies.refetch()} /> : !canAuthor ? <EmptyState compact title="Lecture seule" message="Le rôle ML_STEWARD ou ADMIN est requis pour proposer une version." /> : <form className="stack" onSubmit={create}>
          {selectedPolicy ? <label className="field">Politique<select className="select" value={selectedPolicy.policyId} onChange={(event) => { setPolicyId(event.target.value); setCreated(undefined) }}>{policies.data.data.map((item) => <option key={item.policyId} value={item.policyId}>{item.policyId}</option>)}</select></label> : <label className="field">Identifiant de la première politique<input className="input" required minLength={1} maxLength={80} value={newPolicyId} onChange={(event) => setNewPolicyId(event.target.value)} /></label>}
          <MlWeightSlider value={mlWeight} onChange={setMlWeight} />
          <label className="field">Mode<select className="select" value={mlWeight === 0 ? 'RULES_ONLY' : 'HYBRID_RERANK'} disabled><option>{mlWeight === 0 ? 'RULES_ONLY' : 'HYBRID_RERANK · proposition non activable en POC'}</option></select></label>
          <label className="field">Justification<textarea className="textarea" required minLength={3} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          {(createPolicy.isError || createVersion.isError) && <p className="form-error">{createPolicy.error?.message || createVersion.error?.message}</p>}
          <Button type="submit" variant="primary" icon={<Plus size={15} />} loading={createPolicy.isPending || createVersion.isPending}>{selectedPolicy ? 'Créer la version' : 'Créer la politique'}</Button>
        </form>}
      </Panel>
      <Panel eyebrow="Cycle gouverné" title={target ? `${target.policyId} · v${target.version}` : 'Aucune version sélectionnée'}>
        {!target ? <EmptyState compact title="Aucune version" /> : <div className="stack"><div className="grid cols-2"><MiniMetric label="Statut" value={target.status} /><MiniMetric label="Ratio" value={`${formatPercent(target.weights.rules)} / ${formatPercent(target.weights.ml)}`} /><MiniMetric label="Auteur" value={target.authorId} /><MiniMetric label="Simulation" value={target.simulationId || '—'} /></div><PolicyActions policy={target} onAction={(next) => setDialog({ kind: 'policy', policy: target, transition: next })} gate3Passed={gate3?.status === 'PASSED'} gate3Reason={gate3?.missingCondition} /></div>}
      </Panel>
    </div>
    <Panel eyebrow="Simulation" title="Impact portefeuille fourni par l’API"><EmptyState compact title="Simulation d’impact non implémentée" message="Le backend refuse explicitement cette transition tant qu’un jeu point-in-time réunissant scores règles et scores ML n’est pas disponible. Aucune distribution avant/après, montée, descente ou variation du top 10 n’est inventée." /></Panel>
    {transition.isError && <div className="notice danger" role="alert"><XCircle size={16} /><div><strong>Transition refusée</strong>{transition.error.message}</div></div>}
    {dialog?.kind === 'policy' && <ReasonDialog title={`${label(dialog.transition)} la politique`} pending={transition.isPending} onClose={() => setDialog(undefined)} onConfirm={(dialogReason) => executeDialog(dialog, dialogReason)} />}
  </div>
}

function PolicyActions({ policy, onAction, gate3Passed, gate3Reason }: { policy: ScoringPolicyVersionView; onAction: (action: 'simulate' | 'submit' | 'approve' | 'publish' | 'activate') => void; gate3Passed: boolean; gate3Reason?: string | null }) {
  const auth = useAuth()
  const author = auth.hasRole('ML_STEWARD') || auth.hasRole('ADMIN')
  const approver = auth.hasRole('RULE_APPROVER') || auth.hasRole('ADMIN')
  const selfApproval = policy.authorId === auth.username
  return <div className="stack"><div className="row wrap">
    {author && policy.status === 'DRAFT' && <Button size="sm" icon={<FlaskConical size={14} />} onClick={() => onAction('simulate')} disabled title="Simulation indisponible : dataset point-in-time règles/ML non implémenté côté serveur.">Simuler · indisponible</Button>}
    {author && policy.status === 'SIMULATED' && <Button size="sm" variant="primary" icon={<Send size={14} />} onClick={() => onAction('submit')}>Soumettre</Button>}
    {approver && policy.status === 'SUBMITTED' && <Button size="sm" variant="success" icon={<Check size={14} />} onClick={() => onAction('approve')} disabled={selfApproval} title={selfApproval ? 'L’auteur ne peut pas approuver sa propre politique.' : undefined}>Approuver</Button>}
    {approver && policy.status === 'APPROVED' && <Button size="sm" icon={<UploadCloud size={14} />} onClick={() => onAction('publish')}>Publier</Button>}
    {auth.hasRole('ADMIN') && policy.status === 'PUBLISHED' && <Button size="sm" variant="primary" icon={<Play size={14} />} onClick={() => onAction('activate')} disabled={!gate3Passed || policy.weights.ml > 0} title={!gate3Passed ? gate3Reason || 'La porte G3 n’est pas franchie.' : policy.weights.ml > 0 ? 'POC_SHADOW interdit une activation avec un poids ML non nul.' : undefined}>Activer</Button>}
  </div>{selfApproval && policy.status === 'SUBMITTED' && <p className="muted">Séparation des tâches : l’auteur ne peut pas approuver sa propre politique.</p>}{policy.status === 'PUBLISHED' && !gate3Passed && <div className="notice warning"><LockKeyhole size={16} /><div><strong>Activation bloquée.</strong> {gate3Reason || 'La porte G3 n’est pas franchie.'}</div></div>}{policy.status === 'PUBLISHED' && policy.weights.ml > 0 && <div className="notice warning"><LockKeyhole size={16} /><div><strong>POC_SHADOW.</strong> Une politique avec un poids ML non nul ne peut pas être activée tant que les labels historiques BOA et l’évaluation indépendante ne sont pas validés.</div></div>}</div>
}

function ApprovalTab() {
  const auth = useAuth()
  const toast = useToast()
  const runs = useMlGovernanceRuns()
  const policies = useScoringPolicies()
  const audits = useMlGovernanceAudits()
  const runTransition = useTransitionMlRun()
  const policyTransition = useTransitionScoringPolicy()
  const [filter, setFilter] = useState('ALL')
  const [dialog, setDialog] = useState<DialogAction>()
  const pendingRuns = (runs.data?.runs || []).filter((run) => run.status === 'SUBMITTED' || run.status === 'APPROVED' || run.status === 'VALIDATING' || run.status === 'DEMO_ONLY')
  const pendingPolicies = (policies.data?.data || []).flatMap((policy) => policy.versions).filter((item) => ['SUBMITTED', 'APPROVED', 'PUBLISHED'].includes(item.status))
  const events = (audits.data?.audits || []).filter((entry) => filter === 'ALL' || entry.action === filter)
  const eventTypes = Array.from(new Set((audits.data?.audits || []).map((entry) => entry.action)))
  const confirm = (value: DialogAction, reason: string) => {
    if (value.kind === 'model') runTransition.mutate({ modelId: value.run.modelId, modelVersion: value.run.modelVersion, transition: value.transition, reason }, { onSuccess: () => { setDialog(undefined); toast.push('success', 'Transition du modèle enregistrée') } })
    else policyTransition.mutate({ policyId: value.policy.policyId, version: value.policy.version, transition: value.transition, reason, effectiveFrom: value.transition === 'activate' ? new Date().toISOString() : undefined }, { onSuccess: () => { setDialog(undefined); toast.push('success', 'Transition de politique enregistrée') } })
  }
  return <div className="stack">
    <div className="grid cols-2">
      <Panel eyebrow="File de revue" title="Modèles">{runs.isPending ? <SkeletonStack rows={3} /> : runs.isError ? <ErrorState error={runs.error} compact onRetry={() => void runs.refetch()} /> : !pendingRuns.length ? <EmptyState compact title="Aucun modèle à traiter" /> : <div className="review-list">{pendingRuns.map((run) => <ModelReview key={`${run.modelId}-${run.modelVersion}`} run={run} username={auth.username} onAction={(transition) => setDialog({ kind: 'model', run, transition })} />)}</div>}</Panel>
      <Panel eyebrow="File de revue" title="Politiques de fusion">{policies.isPending ? <SkeletonStack rows={3} /> : policies.isError ? <ErrorState error={policies.error} compact onRetry={() => void policies.refetch()} /> : !pendingPolicies.length ? <EmptyState compact title="Aucune politique à traiter" /> : <div className="review-list">{pendingPolicies.map((policy) => <article key={`${policy.policyId}-${policy.version}`}><header className="row between wrap"><strong>{policy.policyId} · v{policy.version}</strong><Badge value={policy.status} /></header><p>Règles {formatPercent(policy.weights.rules)} · ML {formatPercent(policy.weights.ml)}</p><PolicyActions policy={policy} onAction={(transition) => setDialog({ kind: 'policy', policy, transition })} gate3Passed={false} gate3Reason="La porte G3 n’est pas franchie : labels historiques BOA et évaluation indépendante validée requis." /></article>)}</div>}</Panel>
    </div>
    <Panel eyebrow="Audit ML consolidé" title="Journal append-only" tools={<label className="field inline">Type<select className="select sm" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">Tous</option>{eventTypes.map((value) => <option key={value}>{value}</option>)}</select></label>}>
      {audits.isPending ? <SkeletonStack rows={4} /> : audits.isError ? <ErrorState error={audits.error} compact onRetry={() => void audits.refetch()} /> : !audits.data.audits.length ? <EmptyState compact title="Aucune trace d’audit" /> : !events.length ? <EmptyState compact title="Aucun événement pour ce filtre" /> : <div className="timeline">{events.map((entry, index) => <article key={`${entry.traceId}-${index}`}><strong><Badge value={entry.action} /> {entry.objectType} · {entry.objectId}</strong><small>{formatDate(entry.timestamp, true)} par {entry.userId} · trace <span className="mono">{entry.traceId}</span></small>{entry.reason && <p>{entry.reason}</p>}</article>)}</div>}
    </Panel>
    {(runTransition.isError || policyTransition.isError) && <div className="notice danger" role="alert"><XCircle size={16} /><div><strong>Transition refusée</strong>{runTransition.error?.message || policyTransition.error?.message}</div></div>}
    {dialog && <ReasonDialog title={`${label(dialog.transition)} ${dialog.kind === 'model' ? 'le modèle' : 'la politique'}`} pending={runTransition.isPending || policyTransition.isPending} onClose={() => setDialog(undefined)} onConfirm={(reason) => confirm(dialog, reason)} />}
  </div>
}

function ModelReview({ run, username, onAction }: { run: MlGovernanceRun; username: string; onAction: (transition: 'submit' | 'approve' | 'promote') => void }) {
  const auth = useAuth()
  const demo = isDemoRun(run)
  const selfApproval = run.author === username
  return <article><header className="row between wrap"><div><strong>{run.modelVersion}</strong><small>{run.featureVersion} · {run.datasetVersion}</small></div><Badge value={run.status} tone={demo ? 'warning' : undefined} /></header><p>Brier {formatNumber(metricNumber(run.metrics, 'brierScore'), 4)} · ECE {formatNumber(metricNumber(run.metrics, 'expectedCalibrationError'), 4)}</p><Blockers items={run.activationGateBlockers} /><div className="row wrap">
    {(auth.hasRole('ML_STEWARD') || auth.hasRole('ADMIN')) && ['REGISTERED', 'VALIDATING'].includes(run.status) && <Button size="sm" icon={<Send size={14} />} disabled={demo} title={demo ? 'DEMO_ONLY ne peut pas être soumis.' : undefined} onClick={() => onAction('submit')}>Soumettre</Button>}
    {(auth.hasRole('RULE_APPROVER') || auth.hasRole('ADMIN')) && run.status === 'SUBMITTED' && <Button size="sm" variant="success" icon={<Check size={14} />} disabled={demo || selfApproval} title={demo ? 'DEMO_ONLY ne peut pas être approuvé.' : selfApproval ? 'Auto-approbation interdite.' : undefined} onClick={() => onAction('approve')}>Approuver</Button>}
    {auth.hasRole('ADMIN') && (run.status === 'APPROVED' || demo) && <Button size="sm" variant="primary" icon={<UploadCloud size={14} />} disabled={demo || run.activationGateStatus !== 'PASSED'} title={demo ? 'DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE' : run.activationGateBlockers.join(', ')} onClick={() => onAction('promote')}>Promouvoir</Button>}
  </div>{demo && <p className="demo-only-copy">DEMO_ONLY : soumission, approbation et promotion désactivées.</p>}{selfApproval && run.status === 'SUBMITTED' && <p className="muted">L’auteur ne peut pas approuver son propre modèle.</p>}</article>
}

function MiniMetric({ label: metricLabel, value }: { label: string; value: ReactNode }) {
  return <div className="mini-metric"><span>{metricLabel}</span><strong>{value ?? '—'}</strong></div>
}

function MetricList({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics).filter(([, value]) => typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean')
  return !entries.length ? <EmptyState compact title="Aucune métrique" /> : <dl className="metric-list">{entries.map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{typeof value === 'number' ? formatNumber(value, 4) : String(value)}</dd></div>)}</dl>
}

function Blockers({ items }: { items?: string[] }) {
  return items?.length ? <div className="blocker-list" aria-label="Conditions bloquantes">{items.map((item) => <span key={item}><LockKeyhole size={12} />{label(item)}</span>)}</div> : null
}

function ReasonDialog({ title, pending, onClose, onConfirm }: { title: string; pending: boolean; onClose: () => void; onConfirm: (reason: string) => void }) {
  const [reason, setReason] = useState('Revue indépendante et traçable dans le journal d’audit')
  return <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button type="submit" form="ml-reason-form" variant="primary" loading={pending}>Confirmer</Button></>}><form id="ml-reason-form" className="stack" onSubmit={(event) => { event.preventDefault(); onConfirm(reason) }}><p className="muted">Cette action est gouvernée côté serveur. Le motif et l’identité de l’acteur sont conservés.</p><label className="field">Motif métier ou de gouvernance<textarea className="textarea" autoFocus required minLength={3} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label></form></Modal>
}

function MaterializeDialog({ definition, pending, error, onClose, onSubmit }: { definition?: { version: string; targetOutcome: string; horizonDays: number; population: Record<string, unknown> }; pending: boolean; error: Error | null; onClose: () => void; onSubmit: (input: MlOutcomeMaterializationInput) => void }) {
  const [input, setInput] = useState<MlOutcomeMaterializationInput>({ snapshotVersion: '', labelDefinitionVersion: definition?.version || '', targetOutcome: definition?.targetOutcome || '', horizonDays: definition?.horizonDays || 1, population: definition?.population || {}, observationAsOf: '', labelAvailableFrom: '' })
  return <Modal title="Matérialiser les étiquettes" onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button type="submit" form="materialize-labels" variant="primary" loading={pending}>Matérialiser</Button></>}><form id="materialize-labels" className="stack" onSubmit={(event) => { event.preventDefault(); onSubmit(input) }}><label className="field">Version du snapshot<input className="input" required minLength={3} maxLength={40} value={input.snapshotVersion} onChange={(event) => setInput({ ...input, snapshotVersion: event.target.value })} /></label><div className="form-grid two"><label className="field">Observation au<input className="input" type="date" required value={input.observationAsOf} onChange={(event) => setInput({ ...input, observationAsOf: event.target.value })} /></label><label className="field">Étiquette disponible au<input className="input" type="date" required value={input.labelAvailableFrom} onChange={(event) => setInput({ ...input, labelAvailableFrom: event.target.value })} /></label></div><p className="muted">Cible {label(input.targetOutcome)} · horizon {formatNumber(input.horizonDays)} jours · définition {input.labelDefinitionVersion}</p>{error && <p className="form-error">{error.message}</p>}</form></Modal>
}

function ManifestDialog({ definition, pending, error, onClose, onSubmit }: { definition?: { version: string; targetOutcome: string; horizonDays: number; population: Record<string, unknown> }; pending: boolean; error: Error | null; onClose: () => void; onSubmit: (input: MlDatasetManifestInput) => void }) {
  const [input, setInput] = useState<MlDatasetManifestInput>({ manifestVersion: '', snapshotVersion: '', labelDefinitionVersion: definition?.version || '', purpose: 'FUTURE_GOVERNED_LABEL_DATASET', targetOutcome: definition?.targetOutcome || '', horizonDays: definition?.horizonDays || 1, population: definition?.population || {}, exclusions: [], trainingCutoff: '' })
  return <Modal title="Constituer un jeu de données" onClose={onClose} footer={<><Button onClick={onClose}>Annuler</Button><Button type="submit" form="create-manifest" variant="primary" loading={pending}>Constituer</Button></>}><form id="create-manifest" className="stack" onSubmit={(event) => { event.preventDefault(); onSubmit(input) }}><div className="form-grid two"><label className="field">Version du manifeste<input className="input" required minLength={3} maxLength={80} value={input.manifestVersion} onChange={(event) => setInput({ ...input, manifestVersion: event.target.value })} /></label><label className="field">Version du snapshot<input className="input" required minLength={3} maxLength={40} value={input.snapshotVersion} onChange={(event) => setInput({ ...input, snapshotVersion: event.target.value })} /></label></div><label className="field">Fin de la période d’apprentissage<input className="input" type="date" required value={input.trainingCutoff} onChange={(event) => setInput({ ...input, trainingCutoff: event.target.value })} /></label><p className="muted">La période de test, les sources et les contrôles anti-fuite sont résolus et validés par l’API. Un manifeste bloqué reste visible avec ses motifs.</p>{error && <p className="form-error">{error.message}</p>}</form></Modal>
}
