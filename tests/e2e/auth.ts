import { expect, type Page } from '@playwright/test'

/**
 * Authentification E2E.
 * - Mode Keycloak (par défaut) : Authorization Code + PKCE via l'écran de connexion réel.
 * - Mode persona (E2E_DEV_MODE=true) : la stack tourne avec BOA_AUTH_DISABLED=true et
 *   VITE_AUTH_DISABLED=true ; la persona est choisie sur l'écran de connexion (header X-Dev-Principal).
 * Aucune API n'est mockée dans les deux cas.
 */
export const devMode = process.env.E2E_DEV_MODE === 'true'
const keycloakOrigin = process.env.E2E_KEYCLOAK_ORIGIN || 'http://localhost:8081'

export const accounts = {
  cc: { persona: 'cc', username: process.env.E2E_USERNAME || 'rm.demo', password: process.env.E2E_PASSWORD || 'DevOnly-Rm1-ChangeMe!' },
  agence: { persona: 'agence', username: process.env.E2E_BRANCH_USERNAME || 'branch.manager.demo', password: process.env.E2E_BRANCH_PASSWORD || 'DevOnly-BranchManager1-ChangeMe!' },
  backoffice: { persona: 'backoffice', username: process.env.E2E_BUSINESS_ANALYST_USERNAME || 'business.analyst.demo', password: process.env.E2E_BUSINESS_ANALYST_PASSWORD || 'DevOnly-BusinessAnalyst1-ChangeMe!' },
  approbateur: { persona: 'approbateur', username: process.env.E2E_RULE_APPROVER_USERNAME || 'rule.approver.demo', password: process.env.E2E_RULE_APPROVER_PASSWORD || 'DevOnly-RuleApprover1-ChangeMe!' },
} as const

export async function login(page: Page, account: keyof typeof accounts) {
  const target = accounts[account]
  await page.goto('/login')
  if (devMode) {
    await page.getByRole('button', { name: new RegExp(target.persona === 'cc' ? 'Ahmed' : target.persona === 'agence' ? 'Salma' : target.persona === 'approbateur' ? 'Nadia' : 'Youssef') }).click()
  } else {
    await page.getByRole('button', { name: /Se connecter avec Keycloak/i }).click()
    await page.waitForURL((url) => url.origin === keycloakOrigin, { timeout: 20_000 })
    await page.locator('#username').fill(target.username)
    await page.locator('#password').fill(target.password)
    await page.getByRole('button', { name: /Sign In|Connexion|Se connecter/i }).click()
  }
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 })
  await expect(page.locator('.topbar')).toBeVisible()
}
