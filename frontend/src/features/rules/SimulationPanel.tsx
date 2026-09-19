import { AlertTriangle, FlaskConical, Play, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatDate, formatNumber, formatPercent, label } from '../../api/format'
import type { RuleDefinition, RuleSimulationInput, RuleSimulationResult } from '../../api/types'
import { BreakdownBars } from '../../charts/BreakdownBars'
import { CHART } from '../../charts/theme'
import { AnimatedNumber, Badge, Button, EmptyState, Kpi, Panel } from '../../ui'

const iso = (date: Date) => date.toISOString().slice(0, 10)

/** Période par défaut : 12 mois glissants jusqu'à la dernière exécution du moteur (sinon aujourd'hui). */
export const defaultSimulationInput = (rule: RuleDefinition, asOf?: string | null): RuleSimulationInput => {
  const end = asOf ? new Date(asOf) : new Date()
  return {
    period: { from: iso(new Date(end.getTime() - 365 * 86_400_000)), to: iso(end) },
    population: { segment: rule.scope?.segment?.[0] || 'SME', sectors: rule.scope?.sectors, regions: rule.scope?.regions },
  }
}

const matches = (result: RuleSimulationResult) => result.matchedCustomers ?? result.expectedMatches ?? 0
const matchRate = (result: RuleSimulationResult) => result.matchRate ?? (result.populationAnalyzed ? matches(result) / result.populationAnalyzed : 0)

/** État « simulation en cours » : progression visuelle sans chiffres inventés (compteur borné par la réponse API). */
export function SimulationProgress({ label: text = 'Analyse de l’historique des PME du périmètre…' }: { label?: string }) {
  const [tick, setTick] = useState(0)
  useEffect(() => { const timer = window.setInterval(() => setTick((value) => (value + 1) % 4), 400); return () => window.clearInterval(timer) }, [])
  return <div className="sim-progress" role="status" aria-live="polite" data-demo="simulation">
    <div className="row" style={{ gap: 10 }}><FlaskConical size={18} className="spin" /><div><strong>Simulation en cours{'.'.repeat(tick)}</strong><span className="muted">{text}</span></div></div>
    <div className="bar thick sim-bar"><i /></div>
    <span className="faint" style={{ fontSize: 11 }}>Les résultats affichés seront ceux retournés par l’API de simulation.</span>
  </div>
}

export function SimulationForm({ rule, pending, onSubmit, asOf }: { rule: RuleDefinition; pending: boolean; onSubmit: (input: RuleSimulationInput) => void; asOf?: string | null }) {
  const initial = defaultSimulationInput(rule, asOf)
  const [from, setFrom] = useState(initial.period.from)
  const [to, setTo] = useState(initial.period.to)
  return <form className="row wrap" style={{ gap: 10, alignItems: 'flex-end' }} onSubmit={(event) => { event.preventDefault(); onSubmit({ ...initial, period: { from, to } }) }}>
    <label className="field">Du<input className="input sm" type="date" required value={from} max={to} onChange={(event) => setFrom(event.target.value)} aria-label="Début de période" /></label>
    <label className="field">Au<input className="input sm" type="date" required value={to} min={from} onChange={(event) => setTo(event.target.value)} aria-label="Fin de période" /></label>
    <label className="field">Population<input className="input sm" value={`${initial.population.segment} · ${(initial.population.sectors || ['ALL']).join(', ')}`} readOnly aria-label="Population" /></label>
    <Button type="submit" variant="primary" size="sm" loading={pending} icon={<Play size={14} />}>Lancer la simulation</Button>
  </form>
}

export function SimulationResults({ result, compact }: { result?: RuleSimulationResult; compact?: boolean }) {
  if (!result) return <EmptyState compact icon={<FlaskConical />} title="Aucune simulation" message="Lancez une simulation sur l’historique : population, correspondances et impact proviendront exclusivement de l’API." />
  const customers = (result.topCustomers || result.customers || []).slice(0, compact ? 8 : 20)
  const warnings = result.warnings || []
  return <div className="stack" data-demo="simulation">
    {warnings.map((warning, index) => <div className="notice" key={index}><AlertTriangle size={16} /><div><strong>Règle potentiellement trop large</strong>{typeof warning === 'string' ? warning : warning.message}{typeof warning !== 'string' && warning.affectedRate != null ? ` (${formatPercent(warning.affectedRate, 1)} de la population)` : ''}. Le warning informe la décision, il ne bloque pas la publication.</div></div>)}
    <div className="grid cols-4">
      <Kpi label="PME analysées" value={result.populationAnalyzed} tone="navy" icon={<Users size={18} />} note={result.period ? `${formatDate(result.period.from)} → ${formatDate(result.period.to)}` : 'Historique persisté'} />
      <Kpi label="Correspondances" value={matches(result)} tone="blue" note={`${formatPercent(matchRate(result), 1)} de la population`} />
      <Kpi label="Confiance élevée" value={result.highConfidence ?? 0} tone="green" note={`${formatNumber(result.mediumConfidence ?? 0)} moyenne · ${formatNumber(result.lowConfidence ?? 0)} faible`} />
      <Kpi label="Opportunités / CC" value={result.impact?.averageOpportunitiesPerRm ?? result.averageOpportunitiesPerRm ?? 0} tone="violet" format={(value) => value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} note="charge commerciale moyenne" />
    </div>
    <div className="grid cols-3">
      <Panel eyebrow="Impact" title="Par secteur" id="sim-sector"><BreakdownBars items={(result.impact?.bySector || []).map((item) => ({ count: item.count, share: item.rate, sector: item.sector || item.name }))} nameKey="sector" colorFor={() => CHART.teal} /></Panel>
      <Panel eyebrow="Impact" title="Par région" id="sim-region"><BreakdownBars items={(result.impact?.byRegion || []).map((item) => ({ count: item.count, share: item.rate, sector: item.region || item.name }))} nameKey="sector" colorFor={() => CHART.blue} /></Panel>
      <Panel eyebrow="Impact" title="Par segment" id="sim-segment"><BreakdownBars items={(result.impact?.bySegment || []).map((item) => ({ count: item.count, share: item.rate, sector: item.segment || item.name }))} nameKey="sector" colorFor={() => CHART.violet} /></Panel>
    </div>
    <Panel eyebrow="Preview" title={`Top ${customers.length} PME correspondantes`} id="sim-preview" flush tools={<span className="muted" style={{ fontSize: 12 }}>Conversion historique : <strong>{result.conversionRate === 'NOT_AVAILABLE' || result.conversionRate == null ? 'non disponible (aucune donnée inventée)' : formatPercent(Number(result.conversionRate), 1)}</strong></span>}>
      {!customers.length ? <EmptyState compact title="Aucune PME retournée" /> : <div className="table-wrap"><table className="table"><thead><tr><th>PME</th><th>Signaux</th><th className="num">Confiance</th><th>Opportunité</th></tr></thead><tbody>{customers.map((customer) => <tr key={customer.customerId}><td><strong>{customer.company || customer.legalName || customer.customerId}</strong><small className="mono">{customer.customerId}</small></td><td><div className="row wrap" style={{ gap: 4 }}>{customer.signals?.map((signal) => <span className="chip signal" key={signal}>{label(signal)}</span>)}</div>{customer.values && <small className="muted">{Object.entries(customer.values).slice(0, 3).map(([metric, value]) => `${label(metric)} ${typeof value === 'number' ? formatPercent(value > 1 ? value / 100 : value, 0) : String(value)}`).join(' · ')}</small>}</td><td className="num"><strong><AnimatedNumber value={customer.confidence * 100} format={(value) => `${Math.round(value)} %`} /></strong></td><td><Badge tone="info">{label(customer.opportunityType)}</Badge></td></tr>)}</tbody></table></div>}
    </Panel>
  </div>
}
