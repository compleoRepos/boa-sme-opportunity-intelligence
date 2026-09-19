import { expect, test } from '@playwright/test'
import { login } from './auth'

test('cockpit CC : dashboard → fiche PME → opportunité → action → dashboard mis à jour', async ({ page }) => {
  let apiHeaders: Record<string, string> = {}
  page.on('request', (request) => {
    if (!request.url().includes('/api/v1/')) return
    const headers = request.headers()
    if (headers.authorization) apiHeaders = { authorization: headers.authorization }
    if (headers['x-dev-principal']) {
      apiHeaders = { 'x-dev-principal': headers['x-dev-principal'] }
    }
  })
  await login(page, 'cc')
  await expect(page.getByRole('heading', { name: /Bon(jour|soir| après-midi)/ })).toBeVisible()
  await expect.poll(() => Object.keys(apiHeaders).length).toBeGreaterThan(0)

  const ownDashboard = await page.request.get(
    '/api/v1/dashboards/me?relationshipManagerId=rm-02',
    { headers: apiHeaders },
  )
  expect(ownDashboard.status()).toBe(200)
  expect((await ownDashboard.json()).scope.relationshipManagerId).toBe('rm-01')
  const maliciousList = await page.request.get(
    '/api/v1/customers?relationshipManagerId=rm-02&pageSize=100',
    { headers: apiHeaders },
  )
  expect(maliciousList.status()).toBe(200)
  expect((await maliciousList.json()).data).toEqual([])
  expect(
    (await page.request.get('/api/v1/customers/SME-00006', { headers: apiHeaders })).status(),
  ).toBe(404)
  expect(
    (await page.request.get('/api/v1/opportunities', { headers: apiHeaders })).status(),
  ).toBe(403)

  const kpis = page.locator('.kpi')
  await expect(kpis).toHaveCount(4)
  const actionsBefore = Number((await kpis.nth(3).locator('.kpi-value').innerText()).replace(/\D/g, '') || '0')

  const firstRow = page.locator('.priority-row').filter({ hasNotText: 'Suivi standard' }).first()
  await expect(firstRow).toBeVisible()
  const customerName = await firstRow.locator('h3').innerText()
  await firstRow.locator('.priority-main').click()

  await expect(page).toHaveURL(/\/clients\/SME-\d+/)
  await expect(page.locator('.rail')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: customerName })).toBeVisible()
  await expect(page.locator('#health')).toBeVisible()
  await expect(page.locator('#why')).toBeVisible()
  await page.getByRole('button', { name: /^6 mois$/ }).click()
  await expect(page.locator('#activity .recharts-wrapper')).toBeVisible()

  await page.getByRole('button', { name: /Voir l’opportunité/ }).first().click()
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('tab', { name: /Signaux & évidence/ })).toBeVisible()
  await drawer.locator('.choice', { hasText: /^Contacté/ }).click()
  await page.locator('#choice-form textarea').fill('Contact réalisé dans le parcours E2E')
  await page.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.locator('.toast.success')).toContainText('Action enregistrée')
  await expect(page.getByRole('dialog')).toHaveCount(1)
  const historyTab = drawer.getByRole('tab', { name: /Historique/ })
  await historyTab.focus()
  await historyTab.press('Enter')
  await expect(drawer.locator('.timeline')).toContainText('Contact réalisé dans le parcours E2E')
  await page.keyboard.press('Escape')

  await page.locator('.sheet-actions .ring').click()
  await expect(page.getByRole('dialog')).toContainText('Propension')
  await expect(page.getByRole('dialog')).toContainText('Aucune décision de crédit')
  await page.keyboard.press('Escape')

  await page.goto('/')
  await expect(page.locator('.kpi')).toHaveCount(4)
  const actionsAfter = Number((await page.locator('.kpi').nth(3).locator('.kpi-value').innerText()).replace(/\D/g, '') || '0')
  expect(actionsAfter).toBeGreaterThanOrEqual(actionsBefore)
})

test('dashboard agence : drill-down CC → portefeuille → PME → opportunité', async ({ page }) => {
  let apiHeaders: Record<string, string> = {}
  page.on('request', (request) => {
    if (!request.url().includes('/api/v1/')) return
    const headers = request.headers()
    if (headers.authorization) apiHeaders = { authorization: headers.authorization }
    if (headers['x-dev-principal']) {
      apiHeaders = { 'x-dev-principal': headers['x-dev-principal'] }
    }
  })
  await login(page, 'agence')
  await expect(page.getByRole('heading', { name: /^Agence / })).toBeVisible()
  await expect.poll(() => Object.keys(apiHeaders).length).toBeGreaterThan(0)
  const branchDashboard = await page.request.get('/api/v1/dashboards/branch', {
    headers: apiHeaders,
  })
  expect(branchDashboard.status()).toBe(200)
  expect((await branchDashboard.json()).scope.branchId).toBe('BR-01')
  expect(
    (
      await page.request.get('/api/v1/dashboards/relationship-managers/rm-07', {
        headers: apiHeaders,
      })
    ).status(),
  ).toBe(404)
  await expect(page.locator('#rms table tbody tr').first()).toBeVisible()
  await page.locator('#rms table tbody tr').first().click()
  await expect(page).toHaveURL(/\/agence\/cc\//)
  await expect(page.locator('.priority-row').first()).toBeVisible()
  await page
    .locator('.priority-row')
    .filter({ hasNotText: 'Suivi standard' })
    .first()
    .locator('.priority-main')
    .click()
  await expect(page).toHaveURL(/\/clients\/SME-\d+\?cc=/)
  await expect(page.locator('.rail')).toContainText('Portefeuille de')
  await page.getByRole('button', { name: /Voir l’opportunité/ }).first().click()
  await expect(page.getByRole('dialog')).toContainText('Confiance')
})

test('la navigation reste utilisable en largeur tablette', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  await login(page, 'cc')
  await expect(page.locator('.kpi')).toHaveCount(4)
  await page.locator('.priority-row .priority-main').first().click()
  await expect(page.locator('#health')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
