import { Braces, Plus, Trash2 } from 'lucide-react'
import type { RuleConditionDefinition, RuleConditionGroup, RuleExpression, RuleLogic, RuleOperator, RuleUnit } from '../../api/types'

export const metricOptions = [
  ['INFLOW_GROWTH', 'Croissance des encaissements'],
  ['SUPPLIER_PAYMENT_GROWTH', 'Croissance des paiements fournisseurs'],
  ['TRANSACTION_VOLUME_GROWTH', 'Croissance du volume transactionnel'],
  ['INTERNATIONAL_FLOW_GROWTH', 'Croissance des flux internationaux'],
  ['BALANCE_SURPLUS', 'Excédent de trésorerie'],
  ['BALANCE_DECLINE', 'Baisse du solde'],
  ['CREDIT_UTILIZATION_INCREASE', 'Hausse de l’utilisation des lignes'],
  ['NO_RECENT_INVESTMENT_FINANCING', 'Aucun financement investissement récent'],
] as const

export const operatorOptions: Array<[RuleOperator, string]> = [
  ['GREATER_THAN', 'Supérieur à'], ['GREATER_THAN_OR_EQUAL', 'Supérieur ou égal à'],
  ['LESS_THAN', 'Inférieur à'], ['LESS_THAN_OR_EQUAL', 'Inférieur ou égal à'],
  ['EQUAL', 'Égal à'], ['NOT_EQUAL', 'Différent de'], ['BETWEEN', 'Entre'],
  ['IN', 'Dans la liste'], ['NOT_IN', 'Hors de la liste'], ['INCREASE_BY', 'Augmente de'],
  ['DECREASE_BY', 'Diminue de'], ['PERSISTENT_FOR', 'Persistant pendant'],
]

const units: Array<[RuleUnit, string]> = [['PERCENT', '%'], ['MAD', 'MAD'], ['COUNT', 'Nombre'], ['RATIO', 'Ratio'], ['DAYS', 'Jours'], ['BOOLEAN', 'Oui / non']]
const periods = [['7D', '7 jours'], ['30D', '30 jours'], ['90D', '90 jours'], ['180D', '180 jours'], ['365D', '12 mois']]
const logicLabels: Record<RuleLogic, string> = { AND: 'ET', OR: 'OU', NOT: 'NON' }

export const newCondition = (): RuleConditionDefinition => ({
  id: crypto.randomUUID(), type: 'CONDITION', metric: 'INFLOW_GROWTH', operator: 'GREATER_THAN', value: 25, unit: 'PERCENT', period: '90D', weight: 20,
})

export const newGroup = (): RuleConditionGroup => ({ id: crypto.randomUUID(), type: 'GROUP', logic: 'AND', conditions: [newCondition()] })

export function isGroup(item: RuleExpression): item is RuleConditionGroup {
  return item.type === 'GROUP' || 'conditions' in item
}

function valueText(value: RuleConditionDefinition['value']) {
  return Array.isArray(value) ? value.join(', ') : String(value)
}

function parseValue(text: string, operator: RuleOperator, unit: string) {
  if (unit === 'BOOLEAN') return text === 'true'
  if (operator === 'BETWEEN' || operator === 'IN' || operator === 'NOT_IN') {
    return text.split(',').map((part) => part.trim()).filter(Boolean).map((part) => Number.isNaN(Number(part)) ? part : Number(part))
  }
  return Number.isNaN(Number(text)) || text.trim() === '' ? text : Number(text)
}

interface BuilderProps {
  group: RuleConditionGroup
  onChange: (group: RuleConditionGroup) => void
  depth?: number
  removable?: boolean
  onRemove?: () => void
}

export function ConditionBuilder({ group, onChange, depth = 0, removable, onRemove }: BuilderProps) {
  const updateChild = (index: number, next: RuleExpression) => onChange({ ...group, conditions: group.conditions.map((item, i) => i === index ? next : item) })
  const removeChild = (index: number) => onChange({ ...group, conditions: group.conditions.filter((_, i) => i !== index) })

  return <fieldset className="condition-group" data-depth={depth}>
    <legend className="sr-only">Groupe logique niveau {depth + 1}</legend>
    <div className="group-toolbar">
      <div className="logic-switch" aria-label={`Logique du groupe niveau ${depth + 1}`}>
        {(['AND', 'OR', 'NOT'] as RuleLogic[]).map((logic) => <button key={logic} type="button" className={group.logic === logic ? 'active' : ''} aria-pressed={group.logic === logic} onClick={() => onChange({ ...group, logic })}>{logicLabels[logic]}</button>)}
      </div>
      <span className="group-caption"><Braces size={15} /> Groupe {depth + 1}</span>
      {removable && <button type="button" className="icon-button danger-icon" aria-label={`Supprimer le groupe niveau ${depth + 1}`} onClick={onRemove}><Trash2 size={16} /></button>}
    </div>
    <div className="condition-stack">
      {group.conditions.map((item, index) => <div className="condition-node" key={item.id || index}>
        {index > 0 && <span className="logic-connector">{logicLabels[group.logic]}</span>}
        {isGroup(item)
          ? <ConditionBuilder group={item} onChange={(next) => updateChild(index, next)} depth={depth + 1} removable onRemove={() => removeChild(index)} />
          : <ConditionRow condition={item} index={index} onChange={(next) => updateChild(index, next)} onRemove={() => removeChild(index)} canRemove={group.conditions.length > 1} />}
      </div>)}
    </div>
    <div className="group-actions">
      <button type="button" className="button secondary" onClick={() => onChange({ ...group, conditions: [...group.conditions, newCondition()] })}><Plus size={15} /> Condition</button>
      <button type="button" className="button ghost" onClick={() => onChange({ ...group, conditions: [...group.conditions, newGroup()] })}><Braces size={15} /> Groupe imbriqué</button>
    </div>
  </fieldset>
}

function ConditionRow({ condition, index, onChange, onRemove, canRemove }: { condition: RuleConditionDefinition; index: number; onChange: (condition: RuleConditionDefinition) => void; onRemove: () => void; canRemove: boolean }) {
  const set = <K extends keyof RuleConditionDefinition>(key: K, value: RuleConditionDefinition[K]) => onChange({ ...condition, [key]: value })
  const valueHelp = condition.operator === 'BETWEEN' ? 'Deux valeurs séparées par une virgule' : ['IN', 'NOT_IN'].includes(condition.operator) ? 'Valeurs séparées par des virgules' : 'Seuil métier'
  return <div className="condition-row" data-testid="rule-condition">
    <div className="condition-index" aria-hidden="true">{index + 1}</div>
    <label>Métrique<select aria-label={`Métrique condition ${index + 1}`} value={condition.metric} onChange={(event) => set('metric', event.target.value)}>{metricOptions.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
    <label>Opérateur<select aria-label={`Opérateur condition ${index + 1}`} value={condition.operator} onChange={(event) => set('operator', event.target.value as RuleOperator)}>{operatorOptions.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
    <label>Valeur<input aria-label={`Valeur condition ${index + 1}`} type={condition.unit === 'BOOLEAN' ? 'text' : 'text'} value={valueText(condition.value)} placeholder={valueHelp} onChange={(event) => set('value', parseValue(event.target.value, condition.operator, condition.unit))} /></label>
    <label>Unité<select aria-label={`Unité condition ${index + 1}`} value={condition.unit} onChange={(event) => set('unit', event.target.value as RuleUnit)}>{units.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
    <label>Période<select aria-label={`Période condition ${index + 1}`} value={condition.period} onChange={(event) => set('period', event.target.value)}>{periods.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
    <label>Poids<input aria-label={`Poids confiance condition ${index + 1}`} type="number" min="0" max="100" value={condition.weight ?? 0} onChange={(event) => set('weight', Number(event.target.value))} /></label>
    <button type="button" className="icon-button danger-icon condition-remove" aria-label={`Supprimer la condition ${index + 1}`} disabled={!canRemove} onClick={onRemove}><Trash2 size={16} /></button>
  </div>
}
