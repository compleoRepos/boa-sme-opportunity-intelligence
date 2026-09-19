import { expect, test } from '@playwright/test'
import { login } from './auth'

test('cockpit CC : dashboard → fiche PME → opportunité → action → dashboard mis à jour', async ({ page }) => {
  await login(page, 'cc')
  await expect(page.getByRole('heading', { name: /Bon(jour|soir| après-midi)/ })).toBeVisible()
  const kpis = page.locator('.kpi')
  await expect(kpis).toHaveCount(4)
  const actionsBefore = Number((await kpis.nth(3).locator('.kpi-value').innerText()).replace(/\D/g, '') || '0')

  const firstRow = page.locator('.priority-row').first()
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
  await drawer.locator('.choice', { hasText: 'À contacter' }).click()
  await page.locator('#choice-form textarea').fill('Contact planifié dans le parcours E2E')
  await page.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.locator('.toast.success')).toContainText('Action enregistrée')
  await drawer.getByRole('tab', { name: /Historique/ }).click()
  await expect(drawer.locator('.timeline')).toContainText('Contact planifié dans le parcours E2E')
  await page.keyboard.press('Escape')

  await page.locator('.sheet-actions .ring').click()
  await expect(page.getByRole('dialog')).toContainText('Propension')
  await expect(page.getByRole('dialog')).toContainText('Aucune décision de crédit')
  await page.keyboard.press('Escape')

  await page.goto('/')
  await expect(page.locator('.kpi')).toHaveCount(4)
  const actionsAfter = Number((await page.locator('.kpi').nth(3).locator('.kpi-value').innerText()).replace(/\D/g, '') || '0')
  expect(actionsAfter).toBeGreaterThanOrEqual(actionsBefore + 1)
})

test('dashboard agence : drill-down CC → portefeuille → PME → opportunité', async ({ page }) => {
  await login(page, 'agence')
  await expect(page.getByRole('heading', { name: /^Agence / })).toBeVisible()
  await expect(page.locator('#rms table tbody tr').first()).toBeVisible()
  await page.locator('#rms table tbody tr').first().click()
  await expect(page).toHaveURL(/\/agence\/cc\//)
  await expect(page.locator('.priority-row').first()).toBeVisible()
  await page.locator('.priority-row .priority-main').first().click()
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
