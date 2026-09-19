import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { login } from './auth'

const captureDirectory = path.resolve(
  process.cwd(),
  process.env.E2E_CAPTURE_DIR ?? '../../docs/evidence/accessibility',
)

async function expectNoUncontainedHorizontalOverflow(page: Page, expectedWidth: number) {
  const layout = await page.evaluate(() => {
    const viewport = window.innerWidth
    const isContainedByHorizontalScroller = (element: HTMLElement) => {
      let ancestor = element.parentElement
      while (ancestor && ancestor !== document.body) {
        const style = window.getComputedStyle(ancestor)
        if (['auto', 'scroll'].includes(style.overflowX) && ancestor.scrollWidth > ancestor.clientWidth) return true
        ancestor = ancestor.parentElement
      }
      return false
    }
    return {
      viewport,
      documentWidth: document.documentElement.scrollWidth,
      offenders: Array.from(document.querySelectorAll<HTMLElement>('body *'))
        .filter((element) => element.getClientRects().length > 0 && !element.closest('[inert]'))
        .map((element) => {
          const bounds = element.getBoundingClientRect()
          return {
            element: element.tagName.toLowerCase(),
            className: typeof element.className === 'string' ? element.className : '',
            left: Math.round(bounds.left),
            right: Math.round(bounds.right),
            width: Math.round(bounds.width),
            contained: isContainedByHorizontalScroller(element),
          }
        })
        .filter((item) => (item.left < -1 || item.right > viewport + 1) && item.width > 0 && !item.contained)
        .slice(0, 20),
    }
  })
  expect(layout.viewport).toBe(expectedWidth)
  expect(layout.documentWidth - layout.viewport, JSON.stringify(layout, null, 2)).toBeLessThanOrEqual(1)
  expect(layout.offenders, JSON.stringify(layout, null, 2)).toEqual([])
}

test.beforeAll(async () => {
  await mkdir(captureDirectory, { recursive: true })
})

test('preuve responsive : dashboard CC desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page, 'cc')
  await expect(page.locator('.kpi')).toHaveCount(4)
  await expectNoUncontainedHorizontalOverflow(page, 1440)
  await page.screenshot({
    path: path.join(captureDirectory, 'dashboard-cc-viewport-1440x900.png'),
    animations: 'disabled',
  })
})

test('preuve responsive : dashboard agence tablette', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  await login(page, 'agence')
  await expect(page.getByRole('heading', { name: /^Agence / })).toBeVisible()
  await expectNoUncontainedHorizontalOverflow(page, 1024)
  await page.screenshot({
    path: path.join(captureDirectory, 'dashboard-agence-viewport-1024x768.png'),
    animations: 'disabled',
  })
})

test('preuve responsive : fiche PME mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'cc')
  await page.locator('.priority-row .priority-main').first().click()
  await expect(page.locator('#health')).toBeVisible()
  await expectNoUncontainedHorizontalOverflow(page, 390)
  await page.screenshot({
    path: path.join(captureDirectory, 'fiche-pme-viewport-390x844.png'),
    animations: 'disabled',
  })
})
