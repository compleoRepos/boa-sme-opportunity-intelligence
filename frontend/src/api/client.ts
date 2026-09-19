import type { ApiProblem } from './types'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
let tokenProvider: () => string | undefined = () => undefined
let authenticationFailure: () => void = () => undefined
let devPersonaProvider: () => string | undefined = () => undefined

export function configureApiAuth(getToken: () => string | undefined, onAuthenticationFailure: () => void, getDevPersona?: () => string | undefined) {
  tokenProvider = getToken
  authenticationFailure = onAuthenticationFailure
  devPersonaProvider = getDevPersona || (() => undefined)
}

export class ApiError extends Error {
  status: number
  code: string
  correlationId?: string
  details?: ApiProblem['details']

  constructor(status: number, problem: ApiProblem) {
    super(problem.message || problem.title || `Erreur HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = problem.code || 'API_ERROR'
    this.correlationId = problem.correlationId
    this.details = problem.details
  }
}

function uuid() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function buildSearch(query: Record<string, string | number | boolean | undefined | null>) {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.append(key, String(value))
  })
  const text = params.toString()
  return text ? `?${text}` : ''
}

export async function apiRequest<T>(path: string, init: RequestInit & { idempotencyKey?: string } = {}): Promise<T> {
  const token = tokenProvider()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  headers.set('X-Correlation-ID', uuid())
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const persona = devPersonaProvider()
  if (persona && !token) headers.set('X-Dev-Principal', persona)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (init.idempotencyKey) headers.set('Idempotency-Key', init.idempotencyKey)

  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: 'Le Gateway est injoignable. Vérifiez la connexion et réessayez.' })
  }

  if (response.status === 401) authenticationFailure()
  if (!response.ok) {
    let problem: ApiProblem = { code: 'HTTP_ERROR', message: `La requête a échoué (${response.status}).` }
    try {
      problem = await response.json() as ApiProblem
    } catch {
      // Le Gateway peut répondre sans JSON en cas d’indisponibilité amont.
    }
    problem.correlationId ||= response.headers.get('X-Correlation-ID') || undefined
    throw new ApiError(response.status, problem)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
