import { useState, type FormEvent } from 'react'
import { useCreateAction } from '../api/hooks'
import type { ActionType } from '../api/types'
import { label } from '../api/format'
import { Modal } from './UI'

const types: ActionType[] = ['ACCEPT_OPPORTUNITY', 'DISMISS_OPPORTUNITY', 'CONTACT_CUSTOMER', 'CREATE_FOLLOW_UP', 'SCHEDULE_MEETING', 'MARK_CONVERTED']

export function ActionDialog({ opportunityId, initialType, onClose, onSuccess }: { opportunityId: string; initialType?: ActionType; onClose: () => void; onSuccess?: () => void }) {
  const [actionType, setActionType] = useState<ActionType>(initialType || 'CONTACT_CUSTOMER')
  const [note, setNote] = useState('')
  const [dueAt, setDueAt] = useState('')
  const mutation = useCreateAction(opportunityId)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({
      actionType,
      note: note || undefined,
      dueAt: dueAt ? new Date(dueAt).toISOString() : undefined,
    }, { onSuccess: () => { onSuccess?.(); onClose() } })
  }

  return <Modal title="Enregistrer une action" onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <label>Type d’action<select value={actionType} onChange={(event) => setActionType(event.target.value as ActionType)}>{types.map((type) => <option key={type} value={type}>{label(type)}</option>)}</select></label>
      <label>Échéance<input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
      <label>Note<textarea rows={4} maxLength={4000} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Contexte utile pour le suivi commercial" /></label>
      {mutation.isError && <p className="form-error" role="alert">{mutation.error.message}</p>}
      <footer className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Annuler</button><button type="submit" className="button primary" disabled={mutation.isPending}>{mutation.isPending ? 'Enregistrement…' : 'Enregistrer via API'}</button></footer>
    </form>
  </Modal>
}
