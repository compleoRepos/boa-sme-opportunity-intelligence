import { ArrowRight, Cpu, GitBranch, Radar, Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatPercent, label } from '../../api/format'
import type { CustomerPropensity, Explanation, Opportunity } from '../../api/types'
import { useAuth } from '../../auth/AuthProvider'
import { Badge, Skeleton } from '../../ui'
import { parseReasons } from './signals'

interface Evidence { key?: string; label?: string; observed?: unknown; expected?: unknown; operator?: string; passed?: boolean }

const ruleStudioIdFor = (type?: string) => type === 'INVESTMENT_FINANCING' ? 'SME_INVESTMENT_001' : type === 'TRADE_FINANCE' ? 'SME_TRADE_001' : undefined

const isGrowthSignal = (type?: string) => Boolean(type && (type.endsWith('_GROWTH') || type.endsWith('_INCREASE') || type.endsWith('_DECLINE')))

/**
 * « Pourquoi cette opportunité ? » : signaux → règle métier → propension ML → opportunité.
 * Chaque nœud vient de l'API (explication, propension) ; les versions sont affichées.
 */
export function WhyChain({ opportunity, explanation, propensity, loading, onSignal, onRule, onMl, onOpportunity }: { opportunity: Opportunity; explanation?: Explanation; propensity?: CustomerPropensity; loading?: boolean; onSignal?: (signalId: string) => void; onRule?: () => void; onMl?: () => void; onOpportunity?: () => void }) {
  const auth = useAuth()
  const canStudio = auth.hasRole('ADMIN') || auth.hasRole('BUSINESS_ANALYST') || auth.hasRole('RULE_APPROVER')
  const signals = (explanation?.signals || []).filter((signal) => signal.type !== undefined)
  const reasons = parseReasons(opportunity.why)
  const evidence = ((explanation as unknown as { evidence?: Evidence[] })?.evidence || []).filter((item) => typeof item === 'object')
  const passedEvidence = evidence.filter((item) => item.passed).length
  const studioId = ruleStudioIdFor(opportunity.opportunityType)
  const rows = signals.length ? signals.map((signal) => ({ id: signal.signalId, title: label(signal.type), value: isGrowthSignal(signal.type) ? formatPercent(signal.value, 0) : formatPercent(signal.value, 0), threshold: signal.threshold, period: signal.period, severity: signal.severity, growth: isGrowthSignal(signal.type) })) : reasons.filter((reason) => !reason.isBoolean).map((reason, index) => ({ id: `reason-${index}`, title: reason.label, value: reason.delta || '—', threshold: reason.threshold, period: '90D', severity: undefined, growth: true }))
  let step = 0
  const index = () => String(++step).padStart(2, '0')

  if (loading) return <div className="skeleton-stack"><Skeleton kind="row" /><Skeleton kind="row" /><Skeleton kind="row" /></div>

  return <div className="chain" data-demo="why">
    {rows.map((row, position) => <div key={row.id}>
      <button type="button" className="chain-node clickable" data-kind="signal" onClick={onSignal ? () => onSignal(row.id) : undefined} style={{ animationDelay: `${position * 60}ms`, width: '100%', textAlign: 'left' }}>
        <span className="chain-index">{index()}</span>
        <div><h4><Radar size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />{row.title}</h4><p>Signal détecté sur {label(row.period)}{row.threshold != null ? ` · seuil ${formatPercent(row.threshold, 0)}` : ''}{row.severity ? ` · sévérité ${label(row.severity).toLowerCase()}` : ''}</p></div>
        <span className="chain-value">{row.growth && !String(row.value).startsWith('-') ? '+' : ''}{row.value}</span>
      </button>
      <span className="chain-link" aria-hidden="true" />
    </div>)}

    <div>
      {studioId && canStudio && !onRule ? <Link to={`/back-office/regles/${studioId}`} className="chain-node clickable" data-kind="rule" style={{ animationDelay: `${rows.length * 60}ms` }}>
        <RuleNode index={index()} opportunity={opportunity} explanation={explanation} passed={passedEvidence} total={evidence.length} studioId={studioId} />
      </Link> : <button type="button" className={`chain-node ${onRule ? 'clickable' : ''}`} data-kind="rule" onClick={onRule} style={{ animationDelay: `${rows.length * 60}ms`, width: '100%', textAlign: 'left' }}>
        <RuleNode index={index()} opportunity={opportunity} explanation={explanation} passed={passedEvidence} total={evidence.length} studioId={studioId} />
      </button>}
      <span className="chain-link" aria-hidden="true" />
    </div>

    <div>
      <button type="button" className={`chain-node ${onMl ? 'clickable' : ''}`} data-kind="ml" onClick={onMl} style={{ animationDelay: `${(rows.length + 1) * 60}ms`, width: '100%', textAlign: 'left' }}>
        <span className="chain-index">{index()}</span>
        <div><h4><Cpu size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />Propension ML</h4><p>{propensity ? `Modèle ${propensity.model.modelVersion} · features ${propensity.model.featureSetVersion} · ${propensity.factors.length} facteurs` : 'Score de propension commerciale (intérêt estimé)'}</p></div>
        <span className="chain-value">{propensity ? formatPercent(propensity.score, 0) : '—'}</span>
      </button>
      <span className="chain-link" aria-hidden="true" />
    </div>

    <button type="button" className={`chain-node ${onOpportunity ? 'clickable' : ''}`} data-kind="result" onClick={onOpportunity} style={{ animationDelay: `${(rows.length + 2) * 60}ms`, width: '100%', textAlign: 'left' }}>
      <span className="chain-index">{index()}</span>
      <div><h4><Target size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />Opportunité — {label(opportunity.opportunityType)}</h4><p className="muted">{opportunity.recommendedProducts?.map((product) => product.name).join(' · ') || opportunity.what} · horizon {label(opportunity.horizon)}</p></div>
      <span className="chain-value" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Badge tone="success">{label(opportunity.confidenceLevel)} {formatPercent(opportunity.confidence, 0)}</Badge>{onOpportunity && <ArrowRight size={16} />}</span>
    </button>
  </div>
}

function RuleNode({ index, opportunity, explanation, passed, total, studioId }: { index: string; opportunity: Opportunity; explanation?: Explanation; passed: number; total: number; studioId?: string }) {
  const thresholds = explanation?.thresholds ? Object.entries(explanation.thresholds).filter(([, value]) => typeof value === 'number').slice(0, 3) : []
  return <>
    <span className="chain-index">{index}</span>
    <div>
      <h4><GitBranch size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />Règle métier {studioId || opportunity.opportunityType} <span className="chip rule" style={{ marginLeft: 6 }}>v{opportunity.ruleVersion || explanation?.ruleVersion || '1'}</span></h4>
      <p>{total ? `${passed}/${total} conditions satisfaites` : 'Conditions déterministes versionnées'}{thresholds.length ? ` · seuils ${thresholds.map(([key, value]) => `${label(key).toLowerCase()} ${formatPercent(Number(value), 0)}`).join(', ')}` : ''} · moteur {opportunity.engineVersion || explanation?.engineVersion || '—'}</p>
    </div>
    <span className="chain-value"><Badge tone="info">Déclenchée</Badge></span>
  </>
}
