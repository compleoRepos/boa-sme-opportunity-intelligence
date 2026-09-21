import { formatPercent } from '../../api/format'

export const MAX_ML_WEIGHT_PERCENT = 50
export const ML_WEIGHT_STEP_PERCENT = 5

export const clampMlWeight = (value: number) => Math.min(MAX_ML_WEIGHT_PERCENT, Math.max(0, Math.round(value / ML_WEIGHT_STEP_PERCENT) * ML_WEIGHT_STEP_PERCENT))

export function MlWeightSlider({ value, onChange, disabled = false }: { value: number; onChange: (value: number) => void; disabled?: boolean }) {
  const bounded = clampMlWeight(value)
  return <div className="ml-weight-control">
    <div className="row between wrap">
      <label htmlFor="ml-weight"><strong>Part ML</strong><small className="muted">Pas de {ML_WEIGHT_STEP_PERCENT} % · plafond MVP {MAX_ML_WEIGHT_PERCENT} %</small></label>
      <strong className="ml-ratio num">Règles {formatPercent((100 - bounded) / 100)} · ML {formatPercent(bounded / 100)}</strong>
    </div>
    <input
      id="ml-weight"
      type="range"
      min="0"
      max={MAX_ML_WEIGHT_PERCENT}
      step={ML_WEIGHT_STEP_PERCENT}
      value={bounded}
      disabled={disabled}
      aria-label="Part ML"
      aria-valuetext={`${bounded} % de ML, ${100 - bounded} % de règles`}
      onChange={(event) => onChange(clampMlWeight(Number(event.target.value)))}
    />
    <div className="row between muted ml-weight-scale" aria-hidden="true"><span>ML 0 %</span><span>ML {MAX_ML_WEIGHT_PERCENT} %</span></div>
  </div>
}
