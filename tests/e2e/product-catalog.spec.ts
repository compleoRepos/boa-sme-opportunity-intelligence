import { expect, test } from '@playwright/test'

import { login } from './auth'

test('catalogue indicatif : 28 produits, 7 familles et provenance publique', async ({ page }) => {
  await login(page, 'backoffice')
  await page.goto('/produits')

  await expect(
    page.getByRole('heading', { name: 'Produits BANK OF AFRICA visibles publiquement' }),
  ).toBeVisible()
  await expect(page.getByText(/ciblages et critères restent à valider avec BOA/i)).toBeVisible()
  await expect(page.locator('section.panel[id^="product-BOA_"]')).toHaveCount(28)
  await expect(page.locator('section.stack > .row h2')).toHaveCount(7)
  await expect(page.getByText('6 produits · famille TRADE_FINANCE')).toBeVisible()
  await expect(page.locator('a[href^="https://www.bankofafrica.ma/"]')).toHaveCount(28)
  await expect(page.getByText('Crédit documentaire', { exact: true })).toBeVisible()
  await expect(page.getByText('BOA_CREDIT_DOCUMENTAIRE', { exact: true })).toBeVisible()
})
