import { expect, test, type Browser, type Page } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000'
const authorUsername = process.env.E2E_BUSINESS_ANALYST_USERNAME || 'business.analyst.demo'
const authorPassword = process.env.E2E_BUSINESS_ANALYST_PASSWORD || 'DevOnly-BusinessAnalyst1-ChangeMe!'
const approverUsername = process.env.E2E_RULE_APPROVER_USERNAME || 'rule.approver.demo'
const approverPassword = process.env.E2E_RULE_APPROVER_PASSWORD || 'DevOnly-RuleApprover1-ChangeMe!'

async function login(page: Page, username: string, password: string) {
  await page.goto(`${baseURL}/login`)
  await page.getByRole('button', { name: /Se connecter avec Keycloak/i }).click()
  await page.waitForURL(/localhost:8081\/realms\/boa-sme-mvp\/protocol\/openid-connect\/auth/)
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.locator('#kc-login').click()
  await page.waitForURL(/localhost:3000\//)
}

async function authorPage(browser: Browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await login(page, authorUsername, authorPassword)
  return { context, page }
}

async function approverPage(browser: Browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await login(page, approverUsername, approverPassword)
  return { context, page }
}

test('Rule Studio couvre le cycle complet sur PostgreSQL réel et deux rôles séparés', async ({ browser }) => {
  test.setTimeout(180_000)
  const runId = Date.now().toString(36).toUpperCase()
  const ruleName = `PME — investissement E2E ${runId}`
  const author = await authorPage(browser)
  const page = author.page

  const authorTokenRequest = page.waitForRequest((request) => request.url().includes('/api/v1/rules') && Boolean(request.headers().authorization))
  await page.goto(`${baseURL}/rule-studio`)
  const authorToken = (await authorTokenRequest).headers().authorization
  await expect(page.getByRole('heading', { name: 'Rule Studio' })).toBeVisible()
  await page.getByRole('link', { name: /Créer une règle/i }).click() // 1. créer sans code
  await page.getByLabel('Nom de la règle').fill(ruleName)
  await page.getByLabel('Métrique condition 1').selectOption('INFLOW_GROWTH') // 2. métrique
  await page.getByLabel('Opérateur condition 1').selectOption('GREATER_THAN') // 3. opérateur
  await page.getByLabel('Valeur condition 1').fill('-100000') // 4. seuil
  await page.getByRole('button', { name: /Groupe imbriqué/i }).click()
  await page.getByRole('button', { name: 'OU' }).last().click()
  await page
    .getByRole('group', { name: 'Groupe logique niveau 2' })
    .getByLabel('Valeur condition 1')
    .fill('-100000')
  await page.getByLabel('Opportunité').selectOption('INVESTMENT_FINANCING') // 5. opportunité
  await expect(page.locator('.product-selector input[type="checkbox"]').first()).toBeVisible()
  if (page.url().endsWith('/nouvelle')) {
    await page.locator('.product-selector input[type="checkbox"]').first().check()
    if (page.url().endsWith('/nouvelle')) {
      await page.getByRole('button', { name: /Enregistrer le brouillon/i }).click() // 6. brouillon
      await page.waitForURL(/\/rule-studio\/RULE-[A-F0-9]+\/modifier/)
    }
  }
  const ruleId = page.url().match(/\/rule-studio\/([^/]+)\/modifier/)?.[1]
  expect(ruleId).toBeTruthy()

  const editedProduct = page.locator('.product-selector input[type="checkbox"]').first()
  await expect(editedProduct).toBeVisible()
  if (!(await editedProduct.isChecked())) await editedProduct.check()
  await page.getByLabel('Motif de versionnement').fill('Ajustement E2E avant validation')
  await page.getByLabel('Valeur condition 1').first().fill('-99999')
  await page.getByRole('button', { name: /Sauvegarder une nouvelle version/i }).click() // 14. version 2
  await expect(page.getByText('v2')).toBeVisible()

  await page.getByRole('button', { name: /Valider via API/i }).click()
  await expect(page.getByText('Configuration valide', { exact: true })).toBeVisible()
  await page.getByLabel('Début de période').fill('2026-09-01')
  await page.getByLabel('Fin de période').fill('2026-09-30')
  await page.getByRole('button', { name: /Lancer la simulation/i }).click() // 7. simulation réelle
  await expect(page.getByText('Population analysée').locator('..').locator('strong')).not.toHaveText('0') // 8. population
  await expect(page.getByRole('heading', { name: 'Top 20 clients correspondants' })).toBeVisible() // 9. preview
  await expect(page.getByRole('alert')).toContainText(/règle potentiellement trop large/i)
  await expect(page.getByText('Par secteur')).toBeVisible()
  await expect(page.getByText('Par région')).toBeVisible()
  await expect(page.getByText('Par segment')).toBeVisible()
  await expect(page.getByText(/aucune donnée commerciale inventée/i)).toBeVisible()

  await page.getByRole('button', { name: /Tester la règle/i }).click() // 10. PME réelle
  await expect(page.getByText('Condition 1')).toBeVisible()
  await expect(page.getByText('CORRESPONDANCE', { exact: true })).toBeVisible()

  await page.goto(`${baseURL}/rule-studio/${ruleId}`)
  await expect(page.getByText('SIMULATED', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /Approuver/i })).toHaveCount(0)
  await page.getByRole('button', { name: /Soumettre/i }).click() // 11. soumission auteur
  await page.getByLabel(/Motif métier/i).fill('Prête pour revue indépendante E2E')
  await page.getByRole('button', { name: /Soumettre via API/i }).click()
  await expect(page.getByText('SUBMITTED', { exact: true }).first()).toBeVisible()
  const forbiddenApproval = await page.request.post(`${baseURL}/api/v1/rules/${ruleId}/approve`, {
    headers: { Authorization: authorToken, 'Content-Type': 'application/json' },
    data: { reason: 'Cette tentative doit être refusée par le Gateway.' },
  })
  expect(forbiddenApproval.status()).toBe(403)
  await author.context.close()

  const approver = await approverPage(browser)
  const approvalPage = approver.page
  const approverTokenRequest = approvalPage.waitForRequest((request) => request.url().includes('/api/v1/rules') && Boolean(request.headers().authorization))
  await approvalPage.goto(`${baseURL}/rule-studio/${ruleId}`)
  const approverToken = (await approverTokenRequest).headers().authorization
  const forbiddenCreation = await approvalPage.request.post(`${baseURL}/api/v1/rules`, {
    headers: { Authorization: approverToken, 'Content-Type': 'application/json' },
    data: {},
  })
  expect(forbiddenCreation.status()).toBe(403)
  await expect(approvalPage.getByRole('button', { name: /Modifier/i })).toHaveCount(0)
  await approvalPage.getByRole('button', { name: /Approuver/i }).click() // 12. approbation distincte
  await approvalPage.getByLabel(/Motif métier/i).fill('Revue indépendante conforme E2E')
  await approvalPage.getByRole('button', { name: /Approuver via API/i }).click()
  await expect(approvalPage.getByText('APPROVED', { exact: true }).first()).toBeVisible()
  await approvalPage.getByRole('button', { name: /Publier/i }).click() // 13. publication/activation
  await approvalPage.getByLabel(/Motif métier/i).fill('Publication E2E après approbation')
  await approvalPage.getByRole('button', { name: /Publier via API/i }).click()
  await expect(approvalPage.getByText('ACTIVE', { exact: true }).first()).toBeVisible()

  await expect(approvalPage.getByRole('heading', { name: 'Historique complet' })).toBeVisible() // 15. audit
  await expect(approvalPage.getByText('Version 2').first()).toBeVisible()
  await expect(approvalPage.getByText('Version 1').first()).toBeVisible()
  await approvalPage.getByRole('button', { name: /Désactiver/i }).click() // 16. désactivation
  await approvalPage.getByLabel(/Motif métier/i).fill('Fin de campagne E2E')
  await approvalPage.getByRole('button', { name: /Désactiver via API/i }).click()
  await expect(approvalPage.getByText('Désactivée', { exact: true }).first()).toBeVisible()

  await approvalPage.getByRole('button', { name: /Restaurer cette version/i }).last().click() // 17. rollback
  await approvalPage.getByLabel(/Motif métier/i).fill('Retour à la version initiale E2E')
  await approvalPage.getByRole('button', { name: /Restaurer via API/i }).click()
  await expect(approvalPage.getByText('Brouillon', { exact: true }).first()).toBeVisible()
  await expect(approvalPage.getByText('v3')).toBeVisible()
  await approver.context.close()
})

test('Rule Studio reste accessible et responsive sur mobile avec le rôle auteur', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await login(page, authorUsername, authorPassword)
  await page.goto(`${baseURL}/rule-studio`)
  await expect(page.getByRole('heading', { name: 'Rule Studio' })).toBeVisible()
  await page.getByRole('button', { name: /Ouvrir le menu/i }).click()
  await expect(page.getByRole('link', { name: 'Rule Studio', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Fermer', exact: true }).click()
  await page.getByRole('link', { name: /Créer une règle/i }).click()
  await expect(page.getByRole('heading', { name: 'Créer une règle' })).toBeVisible()
  await expect(page.getByLabel('Métrique condition 1')).toBeVisible()
  await context.close()
})
