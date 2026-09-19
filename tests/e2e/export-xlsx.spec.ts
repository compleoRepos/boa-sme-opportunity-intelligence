import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { login } from './auth'

test('un CC télécharge un vrai classeur limité à son portefeuille', async ({ page }) => {
  let apiHeaders: Record<string, string> = {}
  page.on('request', (request) => {
    if (!request.url().includes('/api/v1/')) return
    const headers = request.headers()
    if (headers.authorization) apiHeaders = { authorization: headers.authorization }
    if (headers['x-dev-principal']) apiHeaders = { 'x-dev-principal': headers['x-dev-principal'] }
  })

  await login(page, 'cc')
  await expect(page.getByRole('heading', { name: /Bon(jour|soir| après-midi)/ })).toBeVisible()
  await expect.poll(() => Object.keys(apiHeaders).length).toBeGreaterThan(0)

  const denied = await page.request.get(
    '/api/v1/exports/portfolio.xlsx?relationshipManagerId=rm-02',
    { headers: apiHeaders },
  )
  expect(denied.status()).toBe(404)

  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/exports/portfolio.xlsx'))
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exporter Excel' }).click()
  const [download, exportResponse] = await Promise.all([downloadPromise, responsePromise])
  expect(exportResponse.status()).toBe(200)
  expect(exportResponse.headers()['content-type']).toContain('spreadsheetml.sheet')
  expect(download.suggestedFilename()).toMatch(/^portefeuille-pme-\d{4}-\d{2}-\d{2}\.xlsx$/)
  const target = process.env.E2E_EXPORT_PATH || '/tmp/boa-e2e-portfolio.xlsx'
  await download.saveAs(target)
  const content = await readFile(target)
  expect(content.subarray(0, 4).toString('hex')).toBe('504b0304')
  expect(content.length).toBeGreaterThan(2_000)
  expect(createHash('sha256').update(content).digest('hex')).toBe(exportResponse.headers()['x-content-sha256'])
  await expect(page.locator('.toast.success')).toContainText('Export Excel prêt')
})
