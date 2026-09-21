import { Ban, CheckCircle2, Clock3, LoaderCircle, XCircle } from 'lucide-react'
import { formatDate, formatNumber } from '../../api/format'
import type { MlTrainingJob } from '../../api/types'
import { Badge, Button } from '../../ui'

const elapsed = (job: MlTrainingJob) => {
  const start = job.startedAt || job.createdAt
  if (!start) return '—'
  const end = job.completedAt ? new Date(job.completedAt).getTime() : Date.now()
  const milliseconds = Math.max(0, end - new Date(start).getTime())
  if (!Number.isFinite(milliseconds)) return '—'
  const seconds = Math.round(milliseconds / 1_000)
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}

const terminalTone = (status: MlTrainingJob['status']) => {
  if (status === 'SUCCEEDED') return 'success' as const
  if (status === 'FAILED' || status === 'INSUFFICIENT_DATA') return 'danger' as const
  if (status === 'CANCELLED') return 'neutral' as const
  return 'info' as const
}

export function TrainingProgress({ job, onCancel, cancelling = false }: { job: MlTrainingJob; onCancel?: () => void; cancelling?: boolean }) {
  const percentage = Math.max(0, Math.min(100, job.percentage))
  return <article className="training-progress" aria-label={`Entraînement ${job.id}`}>
    <header className="row between wrap">
      <div>
        <p className="eyebrow">Entraînement en produit · CPU</p>
        <h3>{job.currentStep || 'En attente'}</h3>
        <small className="muted mono">{job.id}</small>
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        <Badge value={job.status} tone={terminalTone(job.status)} />
        {!job.terminal && onCancel && <Button size="sm" variant="danger" icon={<Ban size={14} />} onClick={onCancel} loading={cancelling} disabled={job.cancellationRequested}>Annuler</Button>}
      </div>
    </header>
    <div className="training-meter-row">
      <div className="bar thick" role="progressbar" aria-label="Progression de l’entraînement" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage} aria-valuetext={`${percentage} % · ${job.currentStep || job.status}`}>
        <i style={{ width: `${percentage}%` }} />
      </div>
      <strong className="num">{percentage} %</strong>
    </div>
    {!job.steps.length && <p className="muted">Le job est en file d’attente ; aucune étape n’a encore commencé.</p>}
    <ol className="training-steps">
      {job.steps.map((step, index) => <li key={`${step.name}-${index}`} className={step.status.toLowerCase()}>
        <span className="training-step-icon" aria-hidden="true">
          {step.status === 'COMPLETED' ? <CheckCircle2 size={17} /> : step.status === 'RUNNING' ? <LoaderCircle size={17} className="btn-spinner" /> : <Clock3 size={17} />}
        </span>
        <span><strong>{step.name}</strong>{step.detail && <small>{step.detail}</small>}</span>
        <span className="mono muted">{step.durationMs == null ? '—' : `${formatNumber(step.durationMs)} ms`}</span>
      </li>)}
    </ol>
    {job.error && <div className="notice danger" role="alert"><XCircle size={16} /><div><strong>{job.error.code || 'Échec de l’entraînement'}</strong>{job.error.message}</div></div>}
    <footer className="row between wrap muted ml-job-meta">
      <span>Auteur {job.author}</span>
      <span>Durée {elapsed(job)} · démarré {formatDate(job.startedAt || job.createdAt, true)} · terminé {formatDate(job.completedAt, true)}</span>
    </footer>
  </article>
}
