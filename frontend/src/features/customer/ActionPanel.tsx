import { CalendarClock, Check, CircleSlash, Handshake, PhoneCall, RotateCcw, Trophy, UserCheck } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { label } from '../../api/format'
import type { ActionType, Opportunity, OpportunityAction, Outcome } from '../../api/types'
import { Button, Modal, useToast } from '../../ui'

/**
 * Actions commerciales du CC. Chaque bouton est traduit en appel(s) réel(s) vers
 * POST /opportunities/{id}/actions et PATCH /actions/{id} : aucun état local simulé.
 */
export interface CommercialChoice {
  id: string
  label: string
  icon: ReactNode
  description: string
  actionType: ActionType
  outcome?: Outcome
  dueInDays?: number
  tone?: 'primary' | 'success' | 'danger' | 'secondary'
}

export const COMMERCIAL_CHOICES: CommercialChoice[] = [
  { id: 'to-contact', label: 'À contacter', icon: <PhoneCall size={15} />, description: 'Planifie un contact sous 7 jours.', actionType: 'CONTACT_CUSTOMER', dueInDays: 7, tone: 'primary' },
  { id: 'contacted', label: 'Contacté', icon: <UserCheck size={15} />, description: 'Le client a été joint : résultat CONTACTÉ enregistré.', actionType: 'CONTACT_CUSTOMER', outcome: 'CONTACTED' },
  { id: 'interested', label: 'Intéressé', icon: <Handshake size={15} />, description: 'Rendez-vous planifié, opportunité acceptée.', actionType: 'SCHEDULE_MEETING', outcome: 'MEETING_SCHEDULED', dueInDays: 10, tone: 'success' },
  { id: 'offer', label: 'Offre créée', icon: <Check size={15} />, description: 'Une offre commerciale a été formalisée.', actionType: 'CREATE_FOLLOW_UP', outcome: 'OFFER_CREATED' },
  { id: 'converted', label: 'Converti', icon: <Trophy size={15} />, description: 'Souscription réalisée (nécessite un contact préalable).', actionType: 'MARK_CONVERTED', tone: 'success' },
  { id: 'not-interested', label: 'Non intéressé', icon: <CircleSlash size={15} />, description: 'L’opportunité est écartée avec le motif NON PERTINENT.', actionType: 'DISMISS_OPPORTUNITY', tone: 'danger' },
  { id: 'later', label: 'À revoir', icon: <RotateCcw size={15} />, description: 'Opportunité différée et non réémise pendant 30 jours.', actionType: 'DEFER_OPPORTUNITY', dueInDays: 30 },
]

const isoInDays = (days?: number) => (days ? new Date(Date.now() + days * 86_400_000).toISOString() : undefined)

export async function recordCommercialChoice(opportunityId: string, choice: CommercialChoice, note?: string): Promise<OpportunityAction> {
  const created = await apiRequest<OpportunityAction>(`/api/v1/opportunities/${opportunityId}/actions`, {
    method: 'POST',
    body: JSON.stringify({ actionType: choice.actionType, dueAt: isoInDays(choice.dueInDays), note: note || undefined }),
    idempotencyKey: `ui-${opportunityId}-${choice.id}-${crypto.randomUUID()}`,
  })
  if (!choice.outcome) return created
  return apiRequest<OpportunityAction>(`/api/v1/actions/${created.actionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ outcome: choice.outcome, status: 'COMPLETED' }),
  })
}

export function useRecordChoice(customerId?: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [pending, setPending] = useState<string>()
  const record = async (opportunity: Pick<Opportunity, 'opportunityId' | 'opportunityType'> & { customerName?: string }, choice: CommercialChoice, note?: string) => {
    setPending(choice.id)
    try {
      const action = await recordCommercialChoice(opportunity.opportunityId, choice, note)
      toast.push('success', 'Action enregistrée', `${choice.label} · ${label(opportunity.opportunityType)}${opportunity.customerName ? ` · ${opportunity.customerName}` : ''}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dashboards'] }),
        queryClient.invalidateQueries({ queryKey: ['opportunity', opportunity.opportunityId] }),
        queryClient.invalidateQueries({ queryKey: ['actions'] }),
        queryClient.invalidateQueries({ queryKey: ['customer', customerId || action.customerId] }),
        queryClient.invalidateQueries({ queryKey: ['metrics', 'dashboard'] }),
      ])
      return action
    } catch (error) {
      toast.push('error', 'Action refusée par le Gateway', error instanceof Error ? error.message : 'Erreur inattendue')
      throw error
    } finally {
      setPending(undefined)
    }
  }
  return { record, pending }
}

export function ActionChoiceGrid({ opportunity, customerId, onDone, compact }: { opportunity: Pick<Opportunity, 'opportunityId' | 'opportunityType'> & { customerName?: string }; customerId?: string; onDone?: (action: OpportunityAction) => void; compact?: boolean }) {
  const { record, pending } = useRecordChoice(customerId)
  const [confirm, setConfirm] = useState<CommercialChoice>()
  const [note, setNote] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!confirm) return
    const action = await record(opportunity, confirm, note).catch(() => undefined)
    if (action) { setConfirm(undefined); setNote(''); onDone?.(action) }
  }
  return <>
    <div className={`choice-grid ${compact ? 'compact' : ''}`} role="group" aria-label="Action commerciale" data-demo="action">
      {COMMERCIAL_CHOICES.map((choice) => <button type="button" key={choice.id} className={`choice ${choice.tone || ''}`} onClick={() => setConfirm(choice)} disabled={Boolean(pending)} title={choice.description}>
        <span className="choice-icon">{choice.icon}</span><span className="choice-label">{choice.label}</span>{!compact && <span className="choice-desc">{choice.description}</span>}
      </button>)}
    </div>
    {confirm && <Modal title={`${confirm.label} · ${label(opportunity.opportunityType)}`} onClose={() => setConfirm(undefined)} footer={<><Button onClick={() => setConfirm(undefined)}>Annuler</Button><Button variant="primary" type="submit" form="choice-form" loading={pending === confirm.id} icon={<CalendarClock size={15} />}>Enregistrer</Button></>}>
      <form id="choice-form" className="stack" onSubmit={submit}>
        <p className="muted">{confirm.description}{confirm.dueInDays ? ` Échéance automatique dans ${confirm.dueInDays} jours.` : ''} L’action est créée via l’API et auditée avec votre identité.</p>
        <label className="field">Note commerciale (facultative)<textarea className="textarea" rows={3} maxLength={4000} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Contexte utile : interlocuteur, besoin exprimé, montant envisagé…" /></label>
      </form>
    </Modal>}
  </>
}
