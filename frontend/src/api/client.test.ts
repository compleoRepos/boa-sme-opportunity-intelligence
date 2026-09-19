import { ApiError, apiDownload, apiRequest, buildSearch, configureApiAuth } from './client'

describe('buildSearch', () => {
  it('omet les valeurs vides et conserve les filtres valides', () => {
    expect(buildSearch({ q: '', pageSize: 25, active: true, cursor: undefined })).toBe('?pageSize=25&active=true')
  })
})

describe('apiRequest', () => {
  it('envoie la persona de développement uniquement en l’absence de jeton', async () => {
    configureApiAuth(() => undefined, () => undefined, () => '{"subject":"rm-01"}')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"data":[]}', { status: 200, headers: { 'Content-Type': 'application/json' } })))
    await apiRequest('/api/v1/dashboards/me')
    const headers = vi.mocked(fetch).mock.calls[0]?.[1]?.headers as Headers
    expect(headers.get('X-Dev-Principal')).toBe('{"subject":"rm-01"}')
    expect(headers.get('Authorization')).toBeNull()
    vi.unstubAllGlobals()
  })

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

describe('apiDownload', () => {
  it('télécharge le classeur et utilise le nom fourni par le Gateway', async () => {
    configureApiAuth(() => undefined, () => undefined, () => '{"subject":"rm-01"}')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const createObjectURL = vi.fn(() => 'blob:export')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Blob(['PK']), {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="portefeuille.xlsx"',
        'X-Correlation-ID': 'corr-export',
      },
    })))

    await expect(apiDownload('/api/v1/exports/portfolio.xlsx')).resolves.toEqual({
      filename: 'portefeuille.xlsx',
      correlationId: 'corr-export',
    })
    expect(click).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export')
    const headers = vi.mocked(fetch).mock.calls[0]?.[1]?.headers as Headers
    expect(headers.get('X-Dev-Principal')).toBe('{"subject":"rm-01"}')
    click.mockRestore()
    vi.unstubAllGlobals()
  })

  it('conserve le problème JSON quand un export est refusé', async () => {
    configureApiAuth(() => 'token-test', () => undefined)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'EXPORT_LIMIT_EXCEEDED',
      message: 'Limite dépassée',
    }), {
      status: 413,
      headers: { 'Content-Type': 'application/problem+json', 'X-Correlation-ID': 'corr-limit' },
    })))

    await expect(apiDownload('/api/v1/exports/opportunities.xlsx')).rejects.toMatchObject({
      status: 413,
      code: 'EXPORT_LIMIT_EXCEEDED',
      correlationId: 'corr-limit',
    } satisfies Partial<ApiError>)
    vi.unstubAllGlobals()
  })
})
