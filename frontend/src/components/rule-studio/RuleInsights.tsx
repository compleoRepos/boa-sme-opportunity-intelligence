import { AlertTriangle, Check, CircleX, History, ShieldCheck, Users } from 'lucide-react'
import { formatDate, formatNumber, formatPercent, label, safeJson } from '../../api/format'
import type { ImpactBucket, RuleAuditEntry, RuleSimulationResult, RuleTestResult, RuleVersionSummary } from '../../api/types'
import { Badge, EmptyState, ErrorState, LoadingState } from '../UI'

function count(result: RuleSimulationResult, key: 'matches' | 'opportunities' | 'average') {
  if (key === 'matches') return result.matchedCustomers ?? result.expectedMatches ?? 0
  if (key === 'opportunities') return result.impact?.opportunitiesGenerated ?? result.potentialOpportunities ?? result.matchedCustomers
  return result.impact?.averageOpportunitiesPerRm ?? result.averageOpportunitiesPerRm
}

function rate(result: RuleSimulationResult) {
  return result.matchRate ?? (result.populationAnalyzed ? result.matchedCustomers / result.populationAnalyzed : 0)
}

function ImpactList({ title, buckets }: { title: string; buckets?: ImpactBucket[] }) {
  return <article className="impact-card"><h3>{title}</h3>{!buckets?.length ? <span className="muted">Aucune distribution renvoyée par l’API.</span> : <ol>{buckets.map((bucket, index) => { const name = bucket.name || bucket.sector || bucket.region || bucket.segment || 'Non renseigné'; return <li key={`${name}-${index}`}><div><strong>{label(name)}</strong><span>{formatNumber(bucket.count)} PME</span></div><div className="impact-bar"><i style={{ width: `${Math.max(3, Math.min(100, (bucket.rate ?? 0) * 100))}%` }} /></div></li> })}</ol>}</article>
}

export function SimulationPreview({ result }: { result?: RuleSimulationResult }) {
  if (!result) return <EmptyState title="Aucune simulation" message="Lancez la simulation : la population, les correspondances et l’impact proviendront exclusivement de l’API." />
  const customers = (result.topCustomers || result.customers || []).slice(0, 20)
  const broadWarnings = result.warnings || []
  return <div className="simulation-results" aria-live="polite">
    {broadWarnings.map((warning, index) => <div className="wide-rule-warning" role="alert" key={index}><AlertTriangle /><div><strong>Attention : règle potentiellement trop large</strong><p>{typeof warning === 'string' ? warning : warning.message}{typeof warning !== 'string' && warning.affectedRate != null ? ` (${formatPercent(warning.affectedRate, 1)} de la population)` : ''}</p><span>Le warning informe la décision mais ne bloque pas automatiquement la publication.</span></div></div>)}
    <div className="preview-kpis">
      <article><Users /><span>Population analysée</span><strong>{formatNumber(result.populationAnalyzed)}</strong><small>PME issues de l’historique</small></article>
      <article><Check /><span>Correspondances</span><strong>{formatNumber(count(result, 'matches'))}</strong><small>{formatPercent(rate(result), 1)} de la population</small></article>
      <article><ShieldCheck /><span>Confiance élevée</span><strong>{formatNumber(result.highConfidence)}</strong><small>Opportunités prioritaires</small></article>
      <article><History /><span>Opportunités / RM</span><strong>{formatNumber(count(result, 'average'), 1)}</strong><small>Impact commercial moyen</small></article>
    </div>
    <section className="panel preview-table"><header className="panel-header"><div><p className="eyebrow">RULE PREVIEW</p><h2>Top 20 clients correspondants</h2></div><span>{formatNumber(count(result, 'opportunities'))} opportunités potentielles</span></header>
      {!customers.length ? <EmptyState title="Aucun client correspondant" message="L’API n’a retourné aucun exemple pour cette simulation." /> : <div className="table-wrap"><table><thead><tr><th>Client</th><th>Entreprise</th><th>Signaux et valeurs</th><th>Confiance</th><th>Opportunité</th></tr></thead><tbody>{customers.map((customer) => <tr key={customer.customerId}><td><strong>{customer.customerId}</strong></td><td>{customer.company || customer.legalName || '—'}</td><td><div className="client-signals">{customer.signals?.map((signal) => <span key={signal}>{label(signal)}</span>)}{customer.values && <small>{Object.entries(customer.values).map(([metric, value]) => `${label(metric)} : ${String(value)}`).join(' · ')}</small>}</div></td><td><strong>{formatPercent(customer.confidence, 0)}</strong></td><td>{label(customer.opportunityType)}</td></tr>)}</tbody></table></div>}
    </section>
    <section className="impact-grid" aria-label="Analyse d’impact"><ImpactList title="Par secteur" buckets={result.impact?.bySector} /><ImpactList title="Par région" buckets={result.impact?.byRegion} /><ImpactList title="Par segment" buckets={result.impact?.bySegment} /></section>
    <p className="conversion-note">Conversion historique : <strong>{result.conversionRate === 'NOT_AVAILABLE' || result.conversionRate == null ? 'Non disponible — aucune donnée commerciale inventée' : formatPercent(result.conversionRate, 1)}</strong></p>
  </div>
}

export function RuleTestProof({ result }: { result?: RuleTestResult }) {
  if (!result) return <EmptyState title="Aucun test client" message="Sélectionnez une PME puis lancez le test pour obtenir la preuve condition par condition." />
  return <section className="rule-proof" aria-live="polite">
    <header><div><p className="eyebrow">RULE RESULT</p><h2>{result.customerName || result.customerId}</h2><span>{result.customerId} · Règle {result.ruleId} v{result.ruleVersion}{result.engineVersion ? ` · Moteur ${result.engineVersion}` : ''}</span></div><Badge value={result.matched ? 'MATCH' : 'NO_MATCH'} tone={result.matched ? 'success' : 'danger'} /></header>
    {!result.evidence?.length ? <EmptyState title="Preuves absentes" message="Le service a répondu sans détail conditionnel : le résultat ne peut pas être expliqué." /> : <div className="proof-list">{result.evidence.map((evidence, index) => <article key={evidence.conditionId || `${evidence.metric}-${index}`} className={evidence.result ? 'passed' : 'failed'}><span className="proof-icon">{evidence.result ? <Check /> : <CircleX />}</span><div><small>Condition {index + 1}</small><h3>{label(evidence.metric)}</h3><p>Valeur observée : <strong>{String(evidence.actual ?? 'Non disponible')} {label(evidence.unit)}</strong></p><span>{evidence.message || `Seuil requis : ${label(evidence.operator)} ${Array.isArray(evidence.threshold) ? evidence.threshold.join(' et ') : String(evidence.threshold)} ${label(evidence.unit)}`}</span></div></article>)}</div>}
    <footer><div><span>Résultat</span><strong>{result.matched ? 'CORRESPONDANCE' : 'AUCUNE CORRESPONDANCE'}</strong></div><div><span>Opportunité</span><strong>{label(result.opportunityType)}</strong></div><div><span>Confiance</span><strong>{formatPercent(result.confidence, 0)}</strong></div></footer>
  </section>
}

export function RuleHistory({ versions, audit, loading, error, onRetry, onRollback }: { versions?: RuleVersionSummary[]; audit?: RuleAuditEntry[]; loading: boolean; error?: unknown; onRetry: () => void; onRollback: (version: number | string) => void }) {
  if (loading) return <LoadingState label="Chargement de l’historique et de l’audit…" />
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (!versions?.length && !audit?.length) return <EmptyState title="Historique indisponible" message="Aucune version ni trace d’audit n’a été renvoyée par les APIs." />
  return <div className="history-grid">
    <section><h2>Versions</h2>{!versions?.length ? <p className="muted">Aucune version renvoyée.</p> : <div className="version-list">{versions.map((version, index) => <article key={`${version.ruleId}-${version.version}`}><div><strong>Version {version.version}</strong><Badge value={version.status} /><span>{formatDate(version.createdAt, true)} · {version.createdBy || 'Utilisateur non renseigné'}</span>{version.reason && <p>{version.reason}</p>} {version.changes && <details><summary>Voir les changements</summary><pre>{safeJson(version.changes)}</pre></details>}</div>{index > 0 && <button className="button secondary" type="button" onClick={() => onRollback(version.version)}>Restaurer cette version</button>}</article>)}</div>}</section>
    <section><h2>Journal d’audit</h2>{!audit?.length ? <p className="muted">Aucune trace d’audit renvoyée.</p> : <div className="audit-timeline">{audit.map((entry) => <article key={entry.id}><i /><div><Badge value={entry.action} /><strong>Version {entry.ruleVersion}</strong><span>{formatDate(entry.timestamp, true)} par {entry.userId}</span>{entry.reason && <p>{entry.reason}</p>}{(entry.oldValue !== undefined || entry.newValue !== undefined) && <details><summary>Valeurs auditées</summary><pre>{safeJson({ avant: entry.oldValue, après: entry.newValue })}</pre></details>}</div></article>)}</div>}</section>
  </div>
}
