import Keycloak, { type KeycloakProfile, type KeycloakTokenParsed } from 'keycloak-js'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import type { Role } from '../api/types'

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

const knownRoles: Role[] = ['RELATIONSHIP_MANAGER', 'BRANCH_MANAGER', 'ADMIN', 'DATA_ANALYST', 'BUSINESS_ANALYST', 'RULE_APPROVER']

function extractRoles(token?: BoaToken) {
  const all = [...(token?.realm_access?.roles ?? []), ...(token?.resource_access?.[clientId]?.roles ?? [])]
  return knownRoles.filter((role) => all.includes(role))
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [initialized, setInitialized] = useState(authDisabled)
  const [authenticated, setAuthenticated] = useState(authDisabled)
  const [token, setToken] = useState<string>()
  const [profile, setProfile] = useState<KeycloakProfile>()
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
      .then(async (isAuthenticated) => {
        setAuthenticated(isAuthenticated)
        setToken(keycloak.token)
        setParsed(keycloak.tokenParsed as BoaToken | undefined)
        if (isAuthenticated) {
          try {
            setProfile(await keycloak.loadUserProfile())
          } catch {
            setProfile(undefined)
          }
        }
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

  const login = useCallback(async (redirectPath?: string) => {
    if (authDisabled) return
    const destination = new URL(redirectPath || '/', window.location.origin).toString()
    await keycloak?.login({ redirectUri: destination })
  }, [])

  const logout = useCallback(async () => {
    if (authDisabled) {
      window.location.assign('/login')
      return
    }
    await keycloak?.logout({ redirectUri: `${window.location.origin}/login` })
  }, [])

  const roles = useMemo(() => {
    if (authDisabled) {
      const configured = (import.meta.env.VITE_DEV_ROLES || 'RELATIONSHIP_MANAGER').split(',')
      return knownRoles.filter((role) => configured.includes(role))
    }
    return extractRoles(parsed)
  }, [parsed])

  const value = useMemo<AuthContextValue>(() => ({
    initialized,
    authenticated,
    token,
    username: parsed?.preferred_username || profile?.username || 'utilisateur',
    displayName: parsed?.name || [profile?.firstName, profile?.lastName].filter(Boolean).join(' ') || parsed?.preferred_username || 'Chargé d’affaires',
    roles,
    login,
    logout,
    hasRole: (role) => roles.includes(role),
  }), [initialized, authenticated, token, parsed, profile, roles, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth doit être utilisé dans AuthProvider')
  return context
}
