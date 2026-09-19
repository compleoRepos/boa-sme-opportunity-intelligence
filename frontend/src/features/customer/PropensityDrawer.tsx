import { Cpu, GitBranch, ShieldAlert } from 'lucide-react'
import { formatDate, formatPercent, label } from '../../api/format'
import { useCustomerPropensity } from '../../api/hooks'
import type { Opportunity } from '../../api/types'
import { FactorChart } from '../../charts/FactorChart'
import { Badge, Drawer, ErrorState, PriorityBadge, Ring, SkeletonStack } from '../../ui'

/** Exploration du score : facteurs, modèle, combinaison règles + ML. Aucun LLM. */
export function PropensityDrawer({ customerId, customerName, opportunity, onClose }: { customerId: string; customerName?: string; opportunity?: Opportunity; onClose: () => void }) {
  const propensity = useCustomerPropensity(customerId)
  const data = propensity.data
  return <Drawer eyebrow="Propension commerciale" title={customerName || customerId} onClose={onClose} size="narrow" data-demo="propensity">
    {propensity.isPending ? <SkeletonStack rows={4} kind="block" /> : propensity.isError || !data ? <ErrorState error={propensity.error} onRetry={() => void propensity.refetch()} /> : <>
      <section className="propensity-hero">
        <Ring value={data.score} size="xl" label={`Propension ${Math.round(data.score * 100)} %`} />
        <div className="stack" style={{ gap: 6 }}>
          <p className="eyebrow">Propension</p>
          <strong style={{ fontSize: 28, letterSpacing: '-0.02em' }} className="num">{formatPercent(data.score, 0)}</strong>
          <span className="muted">{opportunity ? label(opportunity.opportunityType) : data.scoreMeaning || 'Intérêt commercial estimé'}</span>
          <div className="row" style={{ gap: 6 }}><PriorityBadge level={data.priorityLevel} /><Badge tone="violet">POC assistif</Badge></div>
        </div>
      </section>

      <section className="stack">
        <div><p className="eyebrow">Principaux facteurs</p><p className="muted" style={{ fontSize: 12 }}>Contribution de chaque variable au score (régression logistique explicable).</p></div>
        {data.factors.length ? <FactorChart factors={data.factors} /> : <p className="faint">Aucun facteur retourné par le service.</p>}
      </section>

      <section className="stack">
        <p className="eyebrow">Combinaison gouvernée</p>
        <div className="combo">
          <div className="combo-part"><Cpu size={16} /><div><strong>ML</strong><span className="num">{formatPercent(data.combination.mlScore, 0)} × {formatPercent(data.combination.mlWeight)}</span></div></div>
          <span className="combo-op">+</span>
          <div className="combo-part"><GitBranch size={16} /><div><strong>Règles métier</strong><span className="num">{formatPercent(data.combination.rulesScore, 0)} × {formatPercent(data.combination.rulesWeight)}</span></div></div>
          <span className="combo-op">=</span>
          <div className="combo-part result"><div><strong>Priorité combinée</strong><span className="num">{formatPercent((data as { combination: { combinedPriorityScore?: number } }).combination.combinedPriorityScore ?? data.score, 0)}</span></div></div>
        </div>
      </section>

      <dl className="kv">
        <dt>Règle métier</dt><dd>{opportunity ? `${opportunity.opportunityType} v${opportunity.ruleVersion || '1'}` : '—'}</dd>
        <dt>Modèle</dt><dd>{data.model.modelId || 'Propension'} · {data.model.modelVersion}</dd>
        <dt>Features</dt><dd>{data.model.featureSetVersion}</dd>
        <dt>Dernière mise à jour</dt><dd>{formatDate(data.model.scoredAt, true)}</dd>
      </dl>

      <div className="notice"><ShieldAlert size={16} /><div><strong>Aucune décision de crédit</strong>{(data.warnings || []).join(' ')}</div></div>
    </>}
  </Drawer>
}
