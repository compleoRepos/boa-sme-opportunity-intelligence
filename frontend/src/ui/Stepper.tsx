import { Check } from 'lucide-react'
import { Fragment } from 'react'

export function Stepper({ steps, current, labels }: { steps: string[]; current: string; labels?: Record<string, string> }) {
  const index = steps.indexOf(current)
  return <div className="stepper" aria-label="Cycle de vie">
    {steps.map((step, position) => {
      const state = position < index ? 'done' : position === index ? 'current' : ''
      return <Fragment key={step}>
        {position > 0 && <span className={`step-link ${position <= index ? 'done' : ''}`} />}
        <span className={`step ${state}`} aria-current={state === 'current' ? 'step' : undefined}><i>{state === 'done' ? <Check size={11} /> : position + 1}</i>{labels?.[step] ?? step}</span>
      </Fragment>
    })}
  </div>
}
