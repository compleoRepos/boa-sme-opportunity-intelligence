import { ApiError, apiRequest, buildSearch, configureApiAuth } from './client'

describe('buildSearch', () => {
  it('omet les valeurs vides et conserve les filtres valides', () => {
    expect(buildSearch({ q: '', pageSize: 25, active: true, cursor: undefined })).toBe('?pageSize=25&active=true')
  })
})

describe('apiRequest', () => {
  it('envoie le bearer token et transforme une erreur normalisée', async () => {
    configureApiAuth(() => 'token-test', () => undefined)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'FORBIDDEN', message: 'Accès refusé', correlationId: 'corr-1' }), { status: 403, headers: { 'Content-Type': 'application/json' } })))
    await expect(apiRequest('/api/v1/admin/rules')).rejects.toMatchObject({ status: 403, code: 'FORBIDDEN', correlationId: 'corr-1' } satisfies Partial<ApiError>)
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/admin/rules', expect.objectContaining({ headers: expect.any(Headers) }))
    const headers = vi.mocked(fetch).mock.calls[0]?.[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer token-test')
    vi.unstubAllGlobals()
  })
})
