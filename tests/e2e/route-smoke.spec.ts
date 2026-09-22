import { expect, test, type Page } from '@playwright/test'

import { login } from './auth'

async function assertRoutesRender(page: Page, routes: string[]) {
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  for (const route of routes) {
    const errorStart = pageErrors.length
    await page.goto(route, { waitUntil: 'networkidle' })
    await expect(page.locator('#root')).not.toBeEmpty()
    await expect(page.getByRole('heading', { name: "Cette page n’a pas pu être affichée" })).toHaveCount(0)
    await expect(page).not.toHaveURL(/\/interdit$/)
    expect(pageErrors.slice(errorStart), `Erreurs de rendu sur ${route}`).toEqual([])
  }
}

test('toutes les pages CC principales produisent un rendu', async ({ page }) => {
  await login(page, 'cc')
  await assertRoutesRender(page, [
    '/',
    '/clients',
    '/clients/SME-00040',
    '/opportunites',
    '/signaux',
    '/actions',
    '/produits',
  ])
})

test('toutes les pages agence principales produisent un rendu', async ({ page }) => {
  await login(page, 'agence')
  await assertRoutesRender(page, [
    '/',
    '/agence/cc/rm-01',
    '/clients',
    '/opportunites',
    '/signaux',
    '/actions',
    '/produits',
  ])
})

test('toutes les pages back-office produisent un rendu, y compris les règles historiques', async ({ page }) => {
  await login(page, 'backoffice')
  await assertRoutesRender(page, [
    '/back-office',
    '/back-office/opportunites',
    '/back-office/produits',
    '/back-office/seuils',
    '/back-office/regles',
    '/back-office/regles/SYNTHETIC_GROWTH_REVIEW',
    '/back-office/regles/SYNTHETIC_GROWTH_REVIEW/modifier',
    '/back-office/studio-ml',
    '/back-office/simulations',
    '/back-office/modeles',
    '/back-office/audit',
    '/back-office/libelles',
    '/back-office/notifications',
  ])
})
