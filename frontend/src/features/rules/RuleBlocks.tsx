import { Braces, Plus, Trash2 } from 'lucide-react'
import { Fragment } from 'react'
import { label } from '../../api/format'
import type { RuleConditionDefinition, RuleConditionGroup, RuleExpression, RuleLogic, RuleOperator, RuleRecommendation, RuleUnit } from '../../api/types'
import { IconButton } from '../../ui'
import { HORIZONS, LOGIC_LABELS, METRICS, OPERATORS, PERIODS, UNITS, conditionSentence, isGroup, newCondition, newGroup, parseValue, valueText } from './ruleModel'

/* ------------------------------------------------------------------
   Lecture : SI … ET … ALORS … (règle publiée, lecture métier)
   ------------------------------------------------------------------ */
export function ReadableRule({ conditions, logic, recommendation, products }: { conditions: RuleExpression[]; logic: RuleLogic; recommendation: RuleRecommendation; products?: Record<string, string> }) {
  return <div className="rule-read" data-demo="rule">
    <ReadableGroup conditions={conditions} logic={logic} first />
    <div className="rule-block"><span className="rule-keyword then">ALORS</span><div className="rule-line rule-then">
      <span className="rule-token">Opportunité <b>{label(recommendation.opportunityType)}</b></span>
      <span className="rule-token">Produit <b>{recommendation.products.length ? recommendation.products.map((id) => products?.[id] || label(id)).join(', ') : '—'}</b></span>
      <span className="rule-token">Horizon <b>{label(recommendation.horizon)}</b></span>
    </div></div>
  </div>
}

function ReadableGroup({ conditions, logic, first, depth = 0 }: { conditions: RuleExpression[]; logic: RuleLogic; first?: boolean; depth?: number }) {
  return <>
    {conditions.map((item, index) => {
      const keyword = index === 0 ? (first && depth === 0 ? 'SI' : LOGIC_LABELS[logic]) : LOGIC_LABELS[logic]
      const tone = keyword === 'SI' ? '' : logic === 'AND' ? 'and' : logic === 'OR' ? 'or' : 'not'
      return <Fragment key={item.id || index}>
        {isGroup(item) ? <div className="rule-block"><span className={`rule-keyword ${tone}`}>{keyword}</span><div className="rule-group" data-depth={depth + 1}><ReadableGroup conditions={item.conditions} logic={item.logic} depth={depth + 1} /></div></div>
          : <div className="rule-block"><span className={`rule-keyword ${tone}`}>{keyword}</span><div className="rule-line" title={conditionSentence(item)}>
            <span className="rule-token metric">{METRICS.find(([value]) => value === item.metric)?.[1] || item.metric}</span>
            <span className="rule-token operator">{OPERATORS.find(([value]) => value === item.operator)?.[1] || item.operator}</span>
            <span className="rule-token value">{['INCREASE_BY', 'DECREASE_BY'].includes(item.operator) && item.unit === 'PERCENT' ? '+' : ''}{valueText(item.value)} {item.unit === 'BOOLEAN' ? '' : UNITS.find(([value]) => value === item.unit)?.[1]}</span>
            <span className="rule-token period">sur {PERIODS.find(([value]) => value === item.period)?.[1] || item.period}</span>
          </div></div>}
      </Fragment>
    })}
  </>
}

/* ------------------------------------------------------------------
   Édition : mêmes blocs, tokens éditables (aucun code, aucun SQL)
   ------------------------------------------------------------------ */
interface BuilderProps { group: RuleConditionGroup; onChange: (group: RuleConditionGroup) => void; depth?: number; onRemove?: () => void; first?: boolean }

export function RuleBuilder({ group, onChange, depth = 0, onRemove, first = true }: BuilderProps) {
  const update = (index: number, next: RuleExpression) => onChange({ ...group, conditions: group.conditions.map((item, i) => (i === index ? next : item)) })
  const remove = (index: number) => onChange({ ...group, conditions: group.conditions.filter((_, i) => i !== index) })
  return <div className={depth ? 'rule-group' : 'rule-edit'} data-depth={depth} data-testid={depth ? 'rule-group' : 'rule-root'}>
    <div className="row between" style={{ marginBottom: 8 }}>
      <div className="logic-switch" role="group" aria-label={`Logique du groupe ${depth + 1}`}>{(['AND', 'OR', 'NOT'] as RuleLogic[]).map((logic) => <button type="button" key={logic} className={group.logic === logic ? 'active' : ''} aria-pressed={group.logic === logic} onClick={() => onChange({ ...group, logic })}>{LOGIC_LABELS[logic]}</button>)}</div>
      <div className="row" style={{ gap: 6 }}>
        <button type="button" className="btn ghost sm" onClick={() => onChange({ ...group, conditions: [...group.conditions, newCondition()] })}><Plus size={14} /> Condition</button>
        <button type="button" className="btn ghost sm" onClick={() => onChange({ ...group, conditions: [...group.conditions, newGroup()] })}><Braces size={14} /> Groupe</button>
        {onRemove && <IconButton label={`Supprimer le groupe ${depth + 1}`} size="sm" onClick={onRemove}><Trash2 size={14} /></IconButton>}
      </div>
    </div>
    {group.conditions.map((item, index) => {
      const keyword = index === 0 ? (first && depth === 0 ? 'SI' : LOGIC_LABELS[group.logic]) : LOGIC_LABELS[group.logic]
      const tone = keyword === 'SI' ? '' : group.logic === 'AND' ? 'and' : group.logic === 'OR' ? 'or' : 'not'
      return <div className="rule-block" key={item.id || index}>
        <span className={`rule-keyword ${tone}`}>{keyword}</span>
        {isGroup(item) ? <RuleBuilder group={item} onChange={(next) => update(index, next)} depth={depth + 1} onRemove={() => remove(index)} first={false} />
          : <ConditionTokens condition={item} index={index} onChange={(next) => update(index, next)} onRemove={group.conditions.length > 1 ? () => remove(index) : undefined} />}
      </div>
    })}
  </div>
}

function ConditionTokens({ condition, index, onChange, onRemove }: { condition: RuleConditionDefinition; index: number; onChange: (condition: RuleConditionDefinition) => void; onRemove?: () => void }) {
  const set = <K extends keyof RuleConditionDefinition>(key: K, value: RuleConditionDefinition[K]) => onChange({ ...condition, [key]: value })
  const listInput = ['BETWEEN', 'IN', 'NOT_IN'].includes(condition.operator)
  return <div className="rule-line" data-testid="rule-condition">
    <span className="rule-token metric"><select aria-label={`Métrique condition ${index + 1}`} value={condition.metric} onChange={(event) => set('metric', event.target.value)}>{METRICS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></span>
    <span className="rule-token operator"><select aria-label={`Opérateur condition ${index + 1}`} value={condition.operator} onChange={(event) => set('operator', event.target.value as RuleOperator)}>{OPERATORS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></span>
    <span className="rule-token value">{condition.unit === 'BOOLEAN' ? <select aria-label={`Valeur condition ${index + 1}`} value={String(condition.value)} onChange={(event) => set('value', event.target.value === 'true')}><option value="true">oui</option><option value="false">non</option></select> : <input aria-label={`Valeur condition ${index + 1}`} type={listInput ? 'text' : 'number'} step="any" value={valueText(condition.value)} placeholder={listInput ? 'a, b' : '25'} onChange={(event) => set('value', parseValue(event.target.value, condition.operator, condition.unit))} />}<select aria-label={`Unité condition ${index + 1}`} value={condition.unit} onChange={(event) => set('unit', event.target.value as RuleUnit)}>{UNITS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></span>
    <span className="rule-token period">sur <select aria-label={`Période condition ${index + 1}`} value={condition.period} onChange={(event) => set('period', event.target.value)}>{PERIODS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></span>
    <span className="rule-token" title="Poids dans le score de confiance">poids <input aria-label={`Poids condition ${index + 1}`} type="number" min={0} max={100} value={condition.weight ?? 0} onChange={(event) => set('weight', Number(event.target.value))} style={{ width: 48 }} /></span>
    {onRemove && <IconButton label={`Supprimer la condition ${index + 1}`} size="sm" onClick={onRemove}><Trash2 size={14} /></IconButton>}
  </div>
}

export function RecommendationTokens({ value, onChange, products }: { value: RuleRecommendation; onChange: (value: RuleRecommendation) => void; products: Array<{ productId: string; name: string }> }) {
  const toggle = (id: string) => onChange({ ...value, products: value.products.includes(id) ? value.products.filter((item) => item !== id) : [...value.products, id] })
  return <div className="rule-block"><span className="rule-keyword then">ALORS</span><div className="stack" style={{ gap: 8 }}>
    <div className="rule-line">
      <span className="rule-token">Opportunité <select aria-label="Type d’opportunité" value={value.opportunityType} onChange={(event) => onChange({ ...value, opportunityType: event.target.value })}>{OPPORTUNITY_TYPES_OPTIONS}</select></span>
      <span className="rule-token">Horizon <select aria-label="Horizon" value={value.horizon} onChange={(event) => onChange({ ...value, horizon: event.target.value })}>{HORIZONS.map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></span>
    </div>
    <div className="row wrap" style={{ gap: 6 }}>{products.length ? products.map((product) => <label key={product.productId} className={`chip product clickable ${value.products.includes(product.productId) ? 'on' : ''}`}><input type="checkbox" className="sr-only" checked={value.products.includes(product.productId)} onChange={() => toggle(product.productId)} />{value.products.includes(product.productId) ? '✓ ' : ''}{product.name}</label>) : <span className="faint">Catalogue produit indisponible.</span>}</div>
  </div></div>
}

const OPPORTUNITY_TYPES_OPTIONS = [['INVESTMENT_FINANCING', 'Financement d’investissement'], ['WORKING_CAPITAL', 'Financement BFR'], ['TRADE_FINANCE', 'Trade finance'], ['CASH_INVESTMENT', 'Placement de trésorerie'], ['FINANCIAL_STRESS_SIGNAL', 'Signal de tension financière']].map(([id, text]) => <option key={id} value={id}>{text}</option>)
