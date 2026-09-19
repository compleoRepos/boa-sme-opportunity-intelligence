import { expect, test, type Page } from '@playwright/test'
import { login } from './auth'

async function status(page: Page) {
  return (await page.locator('.page-actions .badge').first().innerText()).trim()
}

async function confirmLifecycle(page: Page, button: string, reason: string) {
  await page.getByRole('button', { name: button }).first().click()
  await page.locator('#lifecycle-form textarea').fill(reason)
  await page.locator('#lifecycle-form').evaluate((form) => (form as HTMLFormElement).requestSubmit())
  await expect(page.locator('.toast.success', { hasText: /effectué/ }).last()).toBeVisible()
}

test('Rule Studio : création visuelle → validation → simulation → soumission → approbation → publication', async ({ browser }) => {
  test.setTimeout(240_000)
  const runId = Date.now().toString(36).toUpperCase()
  const ruleName = `PME — investissement E2E ${runId}`

  const author = await (await browser.newContext()).newPage()
  await login(author, 'backoffice')
  await author.goto('/back-office/regles/nouvelle')
  await author.getByLabel('Nom de la règle').fill(ruleName)
  await author.getByLabel('Description').fill('Règle créée par le parcours E2E sans code ni SQL.')
  await author.getByRole('button', { name: /^Condition$/ }).click()
  await expect(author.getByTestId('rule-condition')).toHaveCount(2)
  await author.getByLabel('Métrique condition 2').selectOption('SUPPLIER_PAYMENT_GROWTH')
  await author.getByLabel('Valeur condition 2').fill('20')
  await author.locator('.chip.product', { hasText: 'Investment Financing' }).click()
  await author.getByRole('button', { name: /Enregistrer le brouillon/ }).click()
  await expect(author).toHaveURL(/\/back-office\/regles\/(?!nouvelle)[^/]+$/)
  const ruleUrl = author.url()
  await expect(author.getByRole('heading', { level: 1, name: ruleName })).toBeVisible()
  await expect(author.locator('#readable')).toContainText('SI')
  await expect(author.locator('#readable')).toContainText('ALORS')
  expect(await status(author)).toBe('Brouillon')

  await author.getByRole('button', { name: 'Valider' }).click()
  await expect(author.locator('.toast', { hasText: /Configuration valide/ })).toBeVisible()
  await expect.poll(() => status(author)).toBe('Validée')

  await author.getByRole('button', { name: 'Lancer la simulation' }).click()
  await expect(author.locator('#simulation .kpi').first()).toBeVisible({ timeout: 120_000 })
  await expect.poll(async () => Number((await author.locator('#simulation .kpi').first().locator('.kpi-value').innerText()).replace(/\D/g, ''))).toBeGreaterThan(0)
  await expect.poll(() => status(author)).toBe('Simulée')

  await confirmLifecycle(author, 'Soumettre à approbation', 'Soumission E2E')
  await expect.poll(() => status(author)).toBe('Soumise')
  const selfApprove = author.getByRole('button', { name: 'Approuver' })
  if (await selfApprove.count()) await expect(selfApprove).toBeDisabled()

  const approver = await (await browser.newContext()).newPage()
  await login(approver, 'approbateur')
  await approver.goto(ruleUrl)
  await confirmLifecycle(approver, 'Approuver', 'Revue indépendante E2E')
  await expect.poll(() => status(approver)).toBe('Approuvée')
  await confirmLifecycle(approver, 'Publier', 'Publication E2E')
  await expect.poll(() => status(approver)).toMatch(/Active|Publiée/)

  await approver.getByRole('tab', { name: /Versions & audit/ }).click()
  await expect(approver.locator('#audit')).toContainText('Revue indépendante E2E')
  await expect(approver.locator('#versions')).toContainText('Version 1')
})

test('ML Governance expose le registre réel des modèles', async ({ page }) => {
  await login(page, 'backoffice')
  await page.goto('/back-office/modeles')
  await expect(page.getByRole('heading', { name: 'Model Registry' })).toBeVisible()
  await expect(page.locator('.model-list button').first()).toBeVisible()
  await expect(page.locator('#model')).toContainText('Seuil de décision')
  await expect(page.locator('.coef-list li').first()).toBeVisible()
})
