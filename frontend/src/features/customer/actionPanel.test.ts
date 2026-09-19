import { afterEach, describe, expect, it, vi } from 'vitest'
import { COMMERCIAL_CHOICES, recordCommercialChoice } from './ActionPanel'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => vi.unstubAllGlobals())

describe('recordCommercialChoice', () => {
  it('crée une action puis enregistre le résultat via PATCH quand le choix porte un outcome', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ actionId: 'ACT-1', opportunityId: 'OPP-1', customerId: 'SME-1', actionType: 'CONTACT_CUSTOMER', status: 'OPEN', createdAt: 'x' }, 201)).mockResolvedValueOnce(json({ actionId: 'ACT-1', opportunityId: 'OPP-1', customerId: 'SME-1', actionType: 'CONTACT_CUSTOMER', status: 'COMPLETED', outcome: 'CONTACTED', createdAt: 'x' }))
    vi.stubGlobal('fetch', fetchMock)
    const contacted = COMMERCIAL_CHOICES.find((choice) => choice.id === 'contacted')!
    const action = await recordCommercialChoice('OPP-1', contacted, 'note')
    expect(action.outcome).toBe('CONTACTED')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [createUrl, createInit] = fetchMock.mock.calls[0]!
    expect(createUrl).toBe('/api/v1/opportunities/OPP-1/actions')
    expect(JSON.parse(String(createInit.body))).toMatchObject({ actionType: 'CONTACT_CUSTOMER', note: 'note' })
    expect((createInit.headers as Headers).get('Idempotency-Key')).toMatch(/^ui-OPP-1-contacted-/)
    const [patchUrl, patchInit] = fetchMock.mock.calls[1]!
    expect(patchUrl).toBe('/api/v1/actions/ACT-1')
    expect(patchInit.method).toBe('PATCH')
    expect(JSON.parse(String(patchInit.body))).toEqual({ outcome: 'CONTACTED', status: 'COMPLETED' })
  })

  it('n’émet qu’un POST pour « À contacter » avec une échéance à 7 jours', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ actionId: 'ACT-2', opportunityId: 'OPP-1', customerId: 'SME-1', actionType: 'CONTACT_CUSTOMER', status: 'OPEN', createdAt: 'x' }, 201))
    vi.stubGlobal('fetch', fetchMock)
    await recordCommercialChoice('OPP-1', COMMERCIAL_CHOICES.find((choice) => choice.id === 'to-contact')!)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1].body))
    expect(new Date(body.dueAt).getTime() - Date.now()).toBeGreaterThan(6 * 86_400_000)
  })

  it('diffère réellement l’opportunité pour le choix « À revoir »', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ actionId: 'ACT-3', opportunityId: 'OPP-1', customerId: 'SME-1', actionType: 'DEFER_OPPORTUNITY', status: 'COMPLETED', outcome: 'REVIEW_LATER', createdAt: 'x' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    const action = await recordCommercialChoice('OPP-1', COMMERCIAL_CHOICES.find((choice) => choice.id === 'later')!)

    expect(action.outcome).toBe('REVIEW_LATER')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1].body))
    expect(body.actionType).toBe('DEFER_OPPORTUNITY')
    expect(new Date(body.dueAt).getTime() - Date.now()).toBeGreaterThan(29 * 86_400_000)
  })

  it('propage l’erreur normalisée du Gateway (ex. conversion sans contact préalable)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json({ code: 'STATE_CONFLICT', message: 'Conversion requires a prior customer engagement action.' }, 409)))
    await expect(recordCommercialChoice('OPP-1', COMMERCIAL_CHOICES.find((choice) => choice.id === 'converted')!)).rejects.toMatchObject({ status: 409, code: 'STATE_CONFLICT' })
  })
})
