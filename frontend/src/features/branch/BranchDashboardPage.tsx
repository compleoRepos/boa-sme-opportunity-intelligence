import { ArrowRight, BriefcaseBusiness, CalendarCheck2, Flame, TrendingUp, UsersRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { formatNumber, formatPercent, label } from '../../api/format'
import { useBranchDashboard } from '../../api/hooks'
import { BreakdownBars } from '../../charts/BreakdownBars'
import { Funnel } from '../../charts/Funnel'
import { TimelineChart } from '../../charts/TimelineChart'
import { CHART, OPPORTUNITY_COLORS, OUTCOME_COLORS } from '../../charts/theme'
import { EmptyState, ErrorState, Kpi, Panel, SkeletonStack } from '../../ui'
import { PriorityStack } from '../dashboard/CcDashboardPage'

export function BranchDashboardPage() {
  const dashboard = useBranchDashboard()
  const navigate = useNavigate()
  if (dashboard.isPending) return <div className="stack" aria-busy="true"><div className="grid cols-4"><div className="skeleton block" /><div className="skeleton block" /><div className="skeleton block" /><div className="skeleton block" /></div><SkeletonStack rows={4} /></div>
  if (dashboard.isError || !dashboard.data) return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
  const data = dashboard.data
  const { kpis } = data
  const managers = [...data.relationshipManagers].sort((a, b) => b.highPriorityCustomers - a.highPriorityCustomers)

  return <>
    <header className="page-head" data-demo="branch">
      <div><p className="eyebrow accent">Pilotage commercial</p><h1>Agence {data.scope.branchName || data.scope.branchId}</h1><p className="subtitle"><strong>{formatNumber(data.relationshipManagers.length)} chargés de clientèle</strong> · <strong>{formatNumber(kpis.portfolioCustomers)} PME</strong> · {formatNumber(kpis.openOpportunities)} opportunités ouvertes · priorités et conversions calculées par le Gateway.</p></div>
      <div className="page-actions"><span className="badge outline"><span className="dot live" /> Consolidé {new Date(data.generatedAt || Date.now()).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span></div>
    </header>

    <section className="grid cols-4" aria-label="Indicateurs agence">
      <Kpi label="Chargés de clientèle" value={data.relationshipManagers.length} tone="navy" icon={<UsersRound size={20} />} note={`${formatNumber(kpis.portfolioCustomers)} PME suivies`} />
      <Kpi label="Opportunités" value={kpis.openOpportunities} tone="blue" icon={<BriefcaseBusiness size={20} />} note={`${formatNumber(data.opportunitiesByType?.length || 0)} types détectés`} />
      <Kpi label="Priorités P1" value={kpis.highPriorityCustomers} tone="red" icon={<Flame size={20} />} note={`${formatPercent(kpis.portfolioCustomers ? kpis.highPriorityCustomers / kpis.portfolioCustomers : 0)} du portefeuille agence`} />
      <Kpi label="Actions à traiter" value={kpis.actionsDue} tone="amber" icon={<CalendarCheck2 size={20} />} note={`${formatNumber(kpis.contactedCustomers)} contacts · ${formatNumber(kpis.convertedOpportunities)} conversions`} />
    </section>

    <Panel eyebrow="Équipe commerciale" title="Opportunités par chargé de clientèle" id="rms" flush tools={<span className="muted" style={{ fontSize: 12 }}>Cliquer pour ouvrir le portefeuille</span>}>
      <div className="table-wrap"><table className="table hover clickable"><thead><tr><th>Chargé de clientèle</th><th className="num">PME</th><th className="num">P1</th><th className="num">Opportunités</th><th className="num">Actions dues</th><th className="num">Propension moy.</th><th className="num">Conversions</th><th className="num">Taux</th><th /></tr></thead><tbody>
        {managers.map((manager) => <tr key={manager.relationshipManagerId} onClick={() => navigate(`/agence/cc/${encodeURIComponent(manager.relationshipManagerId)}`)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') navigate(`/agence/cc/${encodeURIComponent(manager.relationshipManagerId)}`) }}>
          <td><strong>{manager.relationshipManagerName}</strong><small>{manager.relationshipManagerId}</small></td>
          <td className="num">{formatNumber(manager.portfolioCustomers)}</td>
          <td className="num"><span className="badge priority" data-level="P1">{formatNumber(manager.highPriorityCustomers)}</span></td>
          <td className="num"><div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}><span className="bar thin" style={{ width: 80 }}><i style={{ width: `${Math.min(100, (manager.openOpportunities / Math.max(1, ...managers.map((item) => item.openOpportunities))) * 100)}%` }} /></span><strong>{formatNumber(manager.openOpportunities)}</strong></div></td>
          <td className="num">{formatNumber(manager.actionsDue)}</td>
          <td className="num">{formatPercent(manager.averagePropensity, 0)}</td>
          <td className="num">{formatNumber(manager.convertedOpportunities)}</td>
          <td className="num"><strong>{formatPercent(manager.conversionRate, 0)}</strong></td>
          <td><ArrowRight size={15} className="muted" /></td>
        </tr>)}
      </tbody></table></div>
    </Panel>

    <section className="grid cols-3">
      <Panel eyebrow="Opportunités" title="Par type" id="by-type"><BreakdownBars items={data.opportunitiesByType} nameKey="opportunityType" colorFor={(name) => OPPORTUNITY_COLORS[name] || CHART.blue} /></Panel>
      <Panel eyebrow="Opportunités" title="Par secteur" id="by-sector"><BreakdownBars items={data.opportunitiesBySector} nameKey="sector" colorFor={() => CHART.teal} /></Panel>
      <Panel eyebrow="Opportunités" title="Par produit potentiel" id="by-product"><BreakdownBars items={data.opportunitiesByProduct} nameKey="product" colorFor={() => CHART.violet} labelFor={(item) => item.product || '—'} /></Panel>
    </section>

    <section className="grid cols-3">
      <Panel eyebrow="Priorités clients" title="Distribution agence" id="priority-dist"><PriorityStack items={data.priorityDistribution} /></Panel>
      <Panel eyebrow="Évolution" title="Opportunités générées" id="timeline" tools={<span className="muted" style={{ fontSize: 12 }}>par date de génération</span>}><TimelineChart points={data.opportunityTimeline} name="Opportunités" />{(data.opportunityTimeline?.length || 0) <= 1 && <p className="faint" style={{ fontSize: 11, marginTop: 6 }}>Une seule exécution du moteur à ce jour : la courbe s’enrichira à chaque recalcul.</p>}</Panel>
      <Panel eyebrow="Actions commerciales" title="Actions et résultats" id="actions">
        {data.actionsByType?.length ? <div className="stack"><BreakdownBars items={data.actionsByType} nameKey="actionType" colorFor={() => CHART.blue} max={6} /><div className="divider" /><p className="eyebrow">Outcomes</p><BreakdownBars items={data.outcomes} nameKey="outcome" colorFor={(name) => OUTCOME_COLORS[name] || CHART.blue} max={6} /></div> : <EmptyState compact title="Aucune action enregistrée" message="Les actions des CC et leurs résultats apparaîtront ici en temps réel." />}
      </Panel>
    </section>

    <section className="grid cols-2">
      <Panel eyebrow="Conversions" title="Entonnoir commercial" id="funnel"><Funnel stages={data.conversionFunnel} /></Panel>
      <Panel eyebrow="Répartition" title="Opportunités par CC" id="by-rm"><BreakdownBars items={data.opportunitiesByRelationshipManager} nameKey="relationshipManagerId" labelFor={(item) => item.relationshipManagerName || item.relationshipManagerId || '—'} colorFor={() => CHART.blue} onSelect={(id) => navigate(`/agence/cc/${encodeURIComponent(id)}`)} /></Panel>
    </section>

    <div className="notice neutral"><TrendingUp size={16} /><div><strong>Pilotage commercial uniquement</strong>Les priorités, propensions et conversions ordonnent le travail de l’agence. Elles ne déclenchent aucune décision de crédit. Types : {data.opportunitiesByType?.map((item) => label(item.opportunityType)).join(', ') || '—'}.</div></div>
  </>
}

