import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MlTrainingJob } from '../../api/types'
import { ML_TRAINING_POLL_INTERVAL_MS, trainingPollInterval } from '../../api/mlStudioHooks'
import { MAX_ML_WEIGHT_PERCENT, MlWeightSlider, clampMlWeight } from './MlWeightSlider'
import { TrainingProgress } from './TrainingProgress'

const job = (values: Partial<MlTrainingJob> = {}): MlTrainingJob => ({
  id: 'job-01',
  manifestId: 'manifest-01',
  algorithm: 'LOGISTIC_REGRESSION',
  seed: 20260921,
  justification: 'Entraînement de démonstration gouverné',
  status: 'RUNNING',
  currentStep: 'Entraînement',
  percentage: 63,
  steps: [
    { name: 'Chargement du manifeste', status: 'COMPLETED', durationMs: 80, detail: 'Manifeste TRAINING_READY chargé' },
    { name: 'Entraînement', status: 'RUNNING', startedAt: '2026-09-21T10:00:00Z' },
  ],
  cancellationRequested: false,
  author: 'karim.bennani',
  correlationId: 'trace-01',
  startedAt: '2026-09-21T10:00:00Z',
  completedAt: null,
  createdAt: '2026-09-21T09:59:59Z',
  updatedAt: '2026-09-21T10:00:01Z',
  terminal: false,
  ...values,
})

describe('TrainingProgress', () => {
  it('expose une barre bornée et permet l’annulation tant que le job n’est pas terminal', async () => {
    const onCancel = vi.fn()
    const user = userEvent.setup()
    render(<TrainingProgress job={job({ percentage: 120 })} onCancel={onCancel} />)

    const progress = screen.getByRole('progressbar', { name: /progression/i })
    expect(progress).toHaveAttribute('aria-valuemin', '0')
    expect(progress).toHaveAttribute('aria-valuemax', '100')
    expect(progress).toHaveAttribute('aria-valuenow', '100')
    expect(screen.getByText('Manifeste TRAINING_READY chargé')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Annuler' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('masque l’annulation et arrête le polling pour chaque état terminal', () => {
    for (const status of ['SUCCEEDED', 'FAILED', 'INSUFFICIENT_DATA', 'CANCELLED'] as const) {
      const terminalJob = job({ status, terminal: true, percentage: status === 'SUCCEEDED' ? 100 : 70 })
      const view = render(<TrainingProgress job={terminalJob} onCancel={vi.fn()} />)
      expect(screen.queryByRole('button', { name: 'Annuler' })).not.toBeInTheDocument()
      expect(trainingPollInterval(terminalJob)).toBe(false)
      view.unmount()
    }
    expect(trainingPollInterval(job())).toBe(ML_TRAINING_POLL_INTERVAL_MS)
    expect(trainingPollInterval(undefined)).toBe(false)
  })
})

describe('MlWeightSlider', () => {
  it('borne et arrondit le ratio ML à 0–50 % par pas de 5', () => {
    expect(clampMlWeight(-4)).toBe(0)
    expect(clampMlWeight(13)).toBe(15)
    expect(clampMlWeight(88)).toBe(MAX_ML_WEIGHT_PERCENT)
  })

  it('expose la borne accessible et émet une valeur conforme', () => {
    const onChange = vi.fn()
    render(<MlWeightSlider value={10} onChange={onChange} />)
    const slider = screen.getByRole('slider', { name: 'Part ML' })
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '50')
    expect(slider).toHaveAttribute('step', '5')
    expect(slider).toHaveAttribute('aria-valuetext', '10 % de ML, 90 % de règles')
    fireEvent.change(slider, { target: { value: '50' } })
    expect(onChange).toHaveBeenCalledWith(50)
  })
})
