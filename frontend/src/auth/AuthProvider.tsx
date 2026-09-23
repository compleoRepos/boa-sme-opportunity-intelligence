import Keycloak, { type KeycloakTokenParsed } from 'keycloak-js'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import type { DevPersona, Role } from '../api/types'
import { DEV_PERSONAS, PERSONA_STORAGE_KEY, personaHeader } from './personas'

type BoaToken = KeycloakTokenParsed & {
  preferred_username?: string
  name?: string
  email?: string
  realm_access?: { roles: string[] }
  resource_access?: Record<string, { roles: string[] }>
}

interface AuthContextValue {
  initialized: boolean
  authenticated: boolean
  token?: string
  username: string
  displayName: string
  roles: Role[]
  login: (redirectPath?: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: Role) => boolean
  /** Mode démonstration sans Keycloak : persona active et bascule. */
  devMode: boolean
  persona?: DevPersona
  personas: DevPersona[]
  selectPersona: (id: string) => void
  devPersonaHeader?: string
}

const AuthContext = createContext<AuthContextValue | null>(null)
const authDisabled = import.meta.env.VITE_AUTH_DISABLED === 'true'
const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'boa-sme-spa'
const keycloak = authDisabled
  ? null
  : new Keycloak({
      url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8081',
      realm: import.meta.env.VITE_KEYCLOAK_REALM || 'boa-sme-mvp',
      clientId,
    })

const knownRoles: Role[] = ['RELATIONSHIP_MANAGER', 'BRANCH_MANAGER', 'ADMIN', 'DATA_ANALYST', 'BUSINESS_ANALYST', 'ML_STEWARD', 'RULE_APPROVER', 'EXTERNAL_CONSUMER']

function extractRoles(token?: BoaToken) {
  const all = [...(token?.realm_access?.roles ?? []), ...(token?.resource_access?.[clientId]?.roles ?? [])]
  return knownRoles.filter((role) => all.includes(role))
}

function storedPersona(): DevPersona | undefined {
  try {
    const id = window.localStorage.getItem(PERSONA_STORAGE_KEY)
    return DEV_PERSONAS.find((item) => item.id === id)
  } catch {
    return undefined
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [persona, setPersona] = useState<DevPersona | undefined>(() => (authDisabled ? storedPersona() : undefined))
  const [initialized, setInitialized] = useState(authDisabled)
  const [authenticated, setAuthenticated] = useState(() => authDisabled && Boolean(storedPersona()))
  const [token, setToken] = useState<string>()
  const [parsed, setParsed] = useState<BoaToken>()
  const started = useRef(false)

  useEffect(() => {
    if (!keycloak || started.current) return
    started.current = true
    keycloak.onTokenExpired = () => {
      void keycloak.updateToken(30).then((refreshed) => {
        if (refreshed) {
          setToken(keycloak.token)
          setParsed(keycloak.tokenParsed as BoaToken | undefined)
        }
      }).catch(() => void keycloak.login({ redirectUri: window.location.href }))
    }
    keycloak.onAuthLogout = () => {
      setAuthenticated(false)
      setToken(undefined)
    }
    void keycloak
      .init({
        onLoad: 'check-sso',
        pkceMethod: 'S256',
        checkLoginIframe: false,
        silentCheckSsoFallback: false,
      })
      .then((isAuthenticated) => {
        setAuthenticated(isAuthenticated)
        setToken(keycloak.token)
        setParsed(keycloak.tokenParsed as BoaToken | undefined)
      })
      .catch(() => setAuthenticated(false))
      .finally(() => setInitialized(true))
  }, [])

  useEffect(() => {
    if (!keycloak || !authenticated) return
    const timer = window.setInterval(() => {
      void keycloak.updateToken(45).then(() => {
        setToken(keycloak.token)
        setParsed(keycloak.tokenParsed as BoaToken | undefined)
      }).catch(() => setAuthenticated(false))
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [authenticated])

  const selectPersona = useCallback((id: string) => {
    const next = DEV_PERSONAS.find((item) => item.id === id)
    if (!next) return
    try { window.localStorage.setItem(PERSONA_STORAGE_KEY, next.id) } catch { /* stockage indisponible */ }
    setPersona(next)
    setAuthenticated(true)
  }, [])

  const login = useCallback(async (redirectPath?: string) => {
    if (authDisabled) return
    const destination = new URL(redirectPath || '/', window.location.origin).toString()
    await keycloak?.login({ redirectUri: destination })
  }, [])

  const logout = useCallback(async () => {
    if (authDisabled) {
      try { window.localStorage.removeItem(PERSONA_STORAGE_KEY) } catch { /* stockage indisponible */ }
      setPersona(undefined)
      setAuthenticated(false)
      window.location.assign('/login')
      return
    }
    await keycloak?.logout({ redirectUri: `${window.location.origin}/login` })
  }, [])

  const roles = useMemo(() => {
    if (authDisabled) {
      if (persona) return persona.roles
      const configured = (import.meta.env.VITE_DEV_ROLES || 'RELATIONSHIP_MANAGER').split(',')
      return knownRoles.filter((role) => configured.includes(role))
    }
    return extractRoles(parsed)
  }, [parsed, persona])

  const value = useMemo<AuthContextValue>(() => ({
    initialized,
    authenticated,
    token,
    username: persona?.username || parsed?.preferred_username || 'utilisateur',
    displayName: persona?.displayName || parsed?.name || parsed?.preferred_username || 'Chargé d’affaires',
    roles,
    login,
    logout,
    hasRole: (role) => roles.includes(role),
    devMode: authDisabled,
    persona,
    personas: DEV_PERSONAS,
    selectPersona,
    devPersonaHeader: persona ? personaHeader(persona) : undefined,
  }), [initialized, authenticated, token, parsed, roles, login, logout, persona, selectPersona])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth doit être utilisé dans AuthProvider')
  return context
}
