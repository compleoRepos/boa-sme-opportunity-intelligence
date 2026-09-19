import { expect, test } from '@playwright/test'
import { login } from './auth'

test('administrateur : versionner puis restaurer un libellé sans changer son code', async ({ page }) => {
  await login(page, 'admin')
  await page.getByRole('link', { name: /Libellés Terminologie/ }).click()
  await expect(page.getByRole('heading', { name: 'Libellés fonctionnels' })).toBeVisible()

  const row = page.locator('tr', { hasText: 'OPEN' })
  const initialLabel = await row.locator('td').nth(1).locator('strong').innerText()
  const initialVersion = Number((await row.locator('td').nth(2).innerText()).replace(/\D/g, ''))
  await row.getByRole('button', { name: 'Modifier' }).click()
  await page.getByLabel('Libellé français').fill('Traitement commercial pilote')
  await page.getByLabel('Justification').fill('Validation E2E du catalogue versionné')
  await page.getByRole('button', { name: 'Créer la version' }).click()
  await expect(page.locator('.toast.success')).toContainText('Libellé versionné')
  await expect(row).toContainText('Traitement commercial pilote')
  await expect(row).toContainText(`v${initialVersion + 1}`)

  await row.getByRole('button', { name: 'Modifier' }).click()
  await page.getByLabel('Libellé français').fill(initialLabel)
  await page.getByLabel('Justification').fill('Restauration après validation E2E')
  await page.getByRole('button', { name: 'Créer la version' }).click()
  await expect(row).toContainText(initialLabel)
  await expect(row).toContainText(`v${initialVersion + 2}`)
})
