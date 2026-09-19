import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { login } from './auth'

async function expectNoWcagViolation(page: Page, testInfo: TestInfo, name: string) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  await testInfo.attach(`${name}-axe.json`, {
    body: JSON.stringify(result, null, 2),
    contentType: 'application/json',
  })
  const violations = result.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => node.target.join(' ')),
  }))
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
}

test('accessibilité WCAG : dashboard CC et drawer Opportunity', async ({ page }, testInfo) => {
  await login(page, 'cc')
  await expect(page.locator('.kpi')).toHaveCount(4)
  await expectNoWcagViolation(page, testInfo, 'dashboard-cc')

  await page.locator('.priority-row .priority-main').first().click()
  await expect(page.locator('#health')).toBeVisible()
  await page.getByRole('button', { name: /Voir l’opportunité/ }).first().click()
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Fermer' })).toBeFocused()
  await page.waitForTimeout(400)
  await expectNoWcagViolation(page, testInfo, 'drawer-opportunity')

  const firstTab = drawer.getByRole('tab', { name: /Signaux & évidence/ })
  await firstTab.focus()
  await firstTab.press('ArrowRight')
  await expect(drawer.getByRole('tab', { name: /Règle & confiance/ })).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(page.getByRole('button', { name: /Voir l’opportunité/ }).first()).toBeFocused()
})

test('accessibilité WCAG : dashboard agence', async ({ page }, testInfo) => {
  await login(page, 'agence')
  await expect(page.getByRole('heading', { name: /^Agence / })).toBeVisible()
  await expectNoWcagViolation(page, testInfo, 'dashboard-agence')
})

test('accessibilité WCAG : back office administrateur', async ({ page }, testInfo) => {
  await login(page, 'admin')
  await page.goto('/back-office')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expectNoWcagViolation(page, testInfo, 'back-office')
})

test('navigation clavier mobile : menu borné, Échap et lien d’évitement', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'cc')
  const skip = page.locator('.skip-link')
  await page.keyboard.press('Tab')
  await expect(skip).toBeFocused()
  await skip.press('Enter')
  await expect(page.locator('#main')).toBeFocused()

  const openMenu = page.locator('.menu-btn')
  await openMenu.click()
  await expect(openMenu).toHaveAttribute('aria-expanded', 'true')
  const closeMenu = page.getByRole('button', { name: 'Fermer', exact: true })
  const appMain = page.locator('.main')
  const scrim = page.locator('.sidebar-scrim')
  await expect(page.locator('body')).toHaveClass(/dialog-open/)
  await expect(appMain).toHaveAttribute('aria-hidden', 'true')
  expect(await appMain.evaluate((element) => (element as HTMLElement).inert)).toBe(true)
  await expect(skip).toHaveAttribute('aria-hidden', 'true')
  expect(await skip.evaluate((element) => (element as HTMLElement).inert)).toBe(true)
  await expect(scrim).toHaveAttribute('aria-hidden', 'true')
  await expect(closeMenu).toBeFocused()
  await page.locator('#main').evaluate((element) => element.focus())
  await expect(closeMenu).toBeFocused()
  await skip.evaluate((element) => element.focus())
  await expect(closeMenu).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(openMenu).toBeFocused()
  await expect(openMenu).toHaveAttribute('aria-expanded', 'false')
  await expect(appMain).not.toHaveAttribute('aria-hidden', 'true')
  expect(await appMain.evaluate((element) => (element as HTMLElement).inert)).toBe(false)
  await expect(skip).not.toHaveAttribute('aria-hidden', 'true')
  expect(await skip.evaluate((element) => (element as HTMLElement).inert)).toBe(false)
  await expect(page.locator('body')).not.toHaveClass(/dialog-open/)
})
