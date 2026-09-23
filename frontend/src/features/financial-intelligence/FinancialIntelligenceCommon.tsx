import { AlertTriangle, Ban, Database, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { formatMoney, formatNumber, formatPercent, formatShortDate, label } from '../../api/format'
import { sourceStatusFor, type FiMetric, type FiResponseMeta, type FiSourceStatus } from '../../api/financialIntelligence.types'
import { Badge, EmptyState } from '../../ui'

export function FiGovernance({ meta }: { meta?: FiResponseMeta | null }) {
  const rulesWeight = meta?.rulesWeight
  const mlWeight = meta?.mlWeight
  return <section className="fi-governance" aria-label="Gouvernance Financial Intelligence">
    <div className="row wrap">
      <ShieldCheck size={18} aria-hidden="true" />
      <strong>
        {meta?.syntheticData ? 'SYNTHETIC DATA' : 'SYNTHETIC STATUS NOT PROVIDED'} /{' '}
        {meta?.nonProduction ? 'NON-PRODUCTION' : 'NON-PRODUCTION STATUS NOT PROVIDED'}
      </strong>
      <Badge value={meta?.executionMode ?? undefined}>{meta?.executionMode ?? 'EXECUTION MODE NOT PROVIDED'}</Badge>
      <Badge value={meta?.mlGovernanceStatus ?? undefined}>
        ML GOVERNANCE {meta?.mlGovernanceStatus ?? 'NOT PROVIDED'}
      </Badge>
      <Badge value={meta?.mlMode ?? undefined}>{meta?.mlMode ?? 'ML MODE NOT ATTESTED'}</Badge>
      <Badge tone={rulesWeight === 1 ? 'success' : 'danger'}>rulesWeight={rulesWeight ?? 'NOT PROVIDED'}</Badge>
      <Badge tone={mlWeight === 0 ? 'success' : 'danger'}>mlWeight={mlWeight ?? 'NOT PROVIDED'}</Badge>
    </div>
    <p>Aucune décision de crédit. Le frontend restitue les agrégats du backend sans calcul d’indicateur; le backend reste autoritaire pour les scopes, grants et périmètres.</p>
  </section>
}

export function FiMeta({ meta, compact = false }: { meta?: FiResponseMeta | null; compact?: boolean }) {
  if (!meta) return <EmptyState compact title="Métadonnées absentes" message="Le backend n’a pas fourni la provenance attendue." />
  return <dl className={`fi-meta ${compact ? 'compact' : ''}`}>
    <div><dt>asOf</dt><dd>{meta.asOf ? formatShortDate(meta.asOf) : 'NOT PROVIDED'}</dd></div>
    <div><dt>Généré</dt><dd>{meta.generatedAt ? formatShortDate(meta.generatedAt) : 'NOT PROVIDED'}</dd></div>
    <div><dt>Contrat</dt><dd>{meta.contractVersion ?? 'NOT PROVIDED'}</dd></div>
    <div><dt>Trace</dt><dd className="mono">{meta.traceId ?? 'NOT PROVIDED'}</dd></div>
    <div><dt>Sources</dt><dd>{meta.sources?.length ? meta.sources.join(', ') : 'NOT PROVIDED'}</dd></div>
    {meta.calculationVersion && <div><dt>Calcul</dt><dd>{meta.calculationVersion}</dd></div>}
    {meta.featureVersion && <div><dt>Features</dt><dd>{meta.featureVersion}</dd></div>}
    {meta.modelVersion && <div><dt>Modèle shadow</dt><dd>{meta.modelVersion}</dd></div>}
  </dl>
}

function sourceTone(status: string) {
  if (status === 'AVAILABLE') return 'success' as const
  if (status === 'EMPTY') return 'warning' as const
  if (status === 'NOT_IMPLEMENTED' || status === 'UNAVAILABLE') return 'danger' as const
  return 'neutral' as const
}

export function FiSourceStatuses({ sources }: { sources?: FiSourceStatus[] | null }) {
  if (!sources?.length) return <EmptyState compact title="Statut des sources absent" message="Aucun sourceStatus n’a été fourni par le backend." />
  return <ul className="fi-source-list">
    {sources.map((source, index) => <li key={`${source.source}-${index}`}>
      <Database size={15} aria-hidden="true" />
      <span><strong>{source.source}</strong><small>{source.capability}{source.reason ? ` — ${source.reason}` : ''}</small></span>
      <Badge tone={sourceTone(source.status)}>{source.status}</Badge>
    </li>)}
  </ul>
}

export function FiBlockedState({ meta, capabilities }: { meta?: FiResponseMeta; capabilities: string[] }) {
  const blocked = capabilities.flatMap((capability) => sourceStatusFor(meta, capability)).filter((source) => source.status === 'NOT_IMPLEMENTED')
  if (!blocked.length) return null
  return <div className="state error fi-blocked" role="alert">
    <Ban aria-hidden="true" />
    <strong>NOT IMPLEMENTED — BLOCKED</strong>
    <span>Le backend déclare une source indispensable non implémentée. Aucune valeur de remplacement n’est affichée.</span>
    {blocked.map((source) => <small key={`${source.source}-${source.capability}`}>{source.capability}{source.reason ? ` — ${source.reason}` : ''}</small>)}
  </div>
}

export function FiPartialWarning({ meta }: { meta?: FiResponseMeta | null }) {
  if (!meta?.sourceStatus.some((source) => source.status === 'UNAVAILABLE')) return null
  return <div className="fi-warning" role="status"><AlertTriangle size={17} aria-hidden="true" /><span><strong>Réponse partielle.</strong> Consultez la provenance; aucune donnée manquante n’est remplacée.</span></div>
}

export function FiValue({ value, unit, currency }: { value?: number | string | null; unit?: string | null; currency?: string | null }) {
  if (value == null) return <>—</>
  if (typeof value === 'string') return <>{value}</>
  if (currency) return <>{formatMoney(value, currency)}</>
  if (unit?.toUpperCase() === 'PERCENT' || unit === '%') return <>{formatPercent(value, 1)}</>
  return <>{formatNumber(value, 2)}{unit ? ` ${unit}` : ''}</>
}

export function FiMetricGrid({ metrics, emptyTitle = 'Aucun agrégat disponible' }: { metrics?: FiMetric[] | null; emptyTitle?: string }) {
  if (!metrics?.length) return <EmptyState compact title={emptyTitle} message="Le backend n’a renvoyé aucune valeur pour cette section." />
  return <dl className="fi-metric-grid">
    {metrics.map((metric, index) => <div key={`${metric.metric}-${metric.period}-${index}`}>
      <dt>{label(metric.metric)}</dt>
      <dd><FiValue value={metric.value} unit={metric.unit} currency={metric.unit === 'MAD' ? 'MAD' : undefined} /></dd>
      <small>{[metric.period, metric.dataQuality, metric.dataCoverage != null && `couverture ${formatPercent(metric.dataCoverage, 0)}`, metric.sampleSize != null && `n=${formatNumber(metric.sampleSize)}`].filter(Boolean).join(' · ')}</small>
    </div>)}
  </dl>
}

export function FiSectionGate({ meta, capabilities = [], children }: { meta?: FiResponseMeta; capabilities?: string[]; children: ReactNode }) {
  if (capabilities.some((capability) => sourceStatusFor(meta, capability).some((source) => source.status === 'NOT_IMPLEMENTED'))) return <FiBlockedState meta={meta} capabilities={capabilities} />
  return <>{children}</>
}
