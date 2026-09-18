import { expect, test, type Page } from '@playwright/test'

const rmUsername = process.env.E2E_USERNAME || 'rm.demo'
const rmPassword = process.env.E2E_PASSWORD || 'DevOnly-Rm1-ChangeMe!'
const branchUsername = process.env.E2E_BRANCH_USERNAME || 'branch.demo'
const branchPassword = process.env.E2E_BRANCH_PASSWORD || 'DevOnly-Branch1-ChangeMe!'
const targetOpportunityId = process.env.E2E_OPPORTUNITY_ID

async function login(page: Page, username: string, password: string) {
  let bearer = ''
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) {
      const value = request.headers().authorization
      if (value?.startsWith('Bearer ')) bearer = value
    }
  })
  await page.goto('/login')
  const loginButton = page.getByRole('button', { name: /Se connecter avec Keycloak/i })
  await expect(loginButton).toBeVisible()
  await loginButton.click()
  await page.waitForURL((url) => url.origin === 'http://localhost:8081', { timeout: 15_000 })
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: /Sign In|Connexion|Se connecter/i }).click()
  await expect(page).toHaveURL(/\/$/, { timeout: 30_000 })
  await expect(
    page.getByRole('heading', { name: /voici vos priorités|performance commerciale|agence/i }).first(),
  ).toBeVisible()
  await expect.poll(() => bearer, { timeout: 15_000 }).toMatch(/^Bearer /)
  return bearer
}

test('parcours CC réel : scope inviolable → propension → opportunité → outcome', async ({ page }) => {
  const bearer = await login(page, rmUsername, rmPassword)
  await expect(page.getByText(/Propension/i).first()).toBeVisible()
  await expect(page.getByText(/priorité commerciale, pas risque de crédit/i)).toBeVisible()

  const ownDashboard = await page.request.get(
    '/api/v1/dashboards/me?relationshipManagerId=rm-02',
    { headers: { Authorization: bearer } },
  )
  expect(ownDashboard.status()).toBe(200)
  const ownBody = await ownDashboard.json()
  expect(ownBody.scope.relationshipManagerId).toBe('rm-01')
  expect(ownBody.portfolio.some((item: { customerId: string }) => item.customerId === 'SME-00002')).toBe(false)
  expect(ownBody.portfolio[0].propensityScore).toBeGreaterThanOrEqual(0)
  expect(ownBody.portfolio[0].combinedPriorityScore).toBeGreaterThanOrEqual(0)

  const maliciousList = await page.request.get(
    '/api/v1/customers?relationshipManagerId=rm-02&pageSize=100',
    { headers: { Authorization: bearer } },
  )
  expect(maliciousList.status()).toBe(200)
  expect((await maliciousList.json()).data).toEqual([])
  expect(
    (await page.request.get('/api/v1/customers/SME-00002', {
      headers: { Authorization: bearer },
    })).status(),
  ).toBe(404)
  expect(
    (await page.request.get('/api/v1/opportunities', {
      headers: { Authorization: bearer },
    })).status(),
  ).toBe(403)

  if (targetOpportunityId) await page.goto(`/opportunites/${targetOpportunityId}`)
  else {
    const first = page.getByRole('link', { name: /Traiter l’opportunité/i }).first()
    await expect(first).toBeVisible()
    await first.click()
  }

  await expect(page.getByTestId('evidence-section')).toBeVisible()
  await expect(page.getByText(/WHY · POURQUOI/i)).toBeVisible()
  await expect(page.getByText(/CONFIDENCE · CONFIANCE/i)).toBeVisible()
  await expect(page.getByText(/EVIDENCE · PREUVES/i)).toBeVisible()
  const opportunityUrl = page.url()

  await page.getByRole('button', { name: /Accepter/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByLabel(/Note/i).fill('Acceptation E2E du dossier')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.getByText(/Opportunité acceptée/i).last()).toBeVisible()

  await page.getByRole('button', { name: /Contacter/i }).click()
  await page.getByLabel(/Note/i).fill('Client joint dans le cadre du parcours E2E')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByText(/Contact client/i).last()).toBeVisible()

  await page.goto('/actions')
  const contactRow = page.locator('.action-item').filter({
    hasText: 'Client joint dans le cadre du parcours E2E',
  }).first()
  await expect(contactRow).toBeVisible()
  await contactRow.getByLabel(/Résultat de/i).selectOption('CONTACTED')
  await expect(contactRow.locator('.badge.success', { hasText: 'Contacté' })).toBeVisible()

  await page.goto(opportunityUrl)
  await expect(page.getByTestId('evidence-section')).toBeVisible()
  await page.getByRole('button', { name: /Créer un suivi/i }).click()
  await page.getByLabel(/Type d’action/i).selectOption('MARK_CONVERTED')
  await page.getByLabel(/Note/i).fill('Conversion E2E confirmée')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByText(/Conversion enregistrée/i).last()).toBeVisible()
})

test('dashboard responsable agence : consolidation des CC et navigation mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const bearer = await login(page, branchUsername, branchPassword)
  await expect(page.getByRole('heading', { name: /KPIs par chargé de clientèle/i })).toBeVisible()
  await expect(page.getByText(/CC consolidés/i)).toBeVisible()

  const branchDashboard = await page.request.get('/api/v1/dashboards/branch', {
    headers: { Authorization: bearer },
  })
  expect(branchDashboard.status()).toBe(200)
  const body = await branchDashboard.json()
  expect(body.scope.branchId).toBe('BR-01')
  expect(body.relationshipManagers.length).toBeGreaterThan(1)
  expect(body.relationshipManagers.every((item: { relationshipManagerId: string }) => item.relationshipManagerId.startsWith('rm-'))).toBe(true)

  const crossBranch = await page.request.get(
    '/api/v1/dashboards/relationship-managers/rm-07',
    { headers: { Authorization: bearer } },
  )
  expect(crossBranch.status()).toBe(404)

  await page.getByRole('button', { name: /Ouvrir le menu/i }).click()
  await page.getByRole('link', { name: 'Portefeuille PME', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Clients PME/i })).toBeVisible()
})
