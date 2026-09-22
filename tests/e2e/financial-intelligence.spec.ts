import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { expect, test, type Browser } from '@playwright/test'
import { devMode, login } from './auth'

const asOf = '2026-09-30'
const keycloakOrigin = process.env.E2E_KEYCLOAK_ORIGIN ?? 'http://localhost:8081'
const evidenceDirectory = path.resolve(
  process.cwd(),
  process.env.FI_EVIDENCE_DIR ?? '../../docs/evidence/financial-intelligence',
)

async function authenticatedPage(browser: Browser, account: Parameters<typeof login>[1]) {
  const context = await browser.newContext()
  const page = await context.newPage()
  let identityHeaders: Record<string, string> = {}
  page.on('request', (request) => {
    const candidate = request.headers().authorization
    const devPrincipal = request.headers()['x-dev-principal']
    if (candidate?.startsWith('Bearer ')) identityHeaders = { Authorization: candidate }
    if (devPrincipal) identityHeaders = { 'X-Dev-Principal': devPrincipal }
  })
  await login(page, account)
  return { context, page, identityHeaders: () => identityHeaders }
}

function expectNoRawFinancialFields(payload: unknown) {
  const serialized = JSON.stringify(payload).toLowerCase()
  for (const forbidden of [
    'iban',
    'accountnumber',
    'transactionid',
    'counterpartyname',
    'remittanceinformation',
  ]) {
    expect(serialized).not.toContain(forbidden)
  }
}

test.beforeAll(async () => {
  await mkdir(evidenceDirectory, { recursive: true })
})

test('la surface FI refuse un appel sans authentification', async ({ request }) => {
  test.skip(devMode, 'Le mode persona local est volontairement sans OIDC.')
  const response = await request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}`,
  )
  expect(response.status()).toBe(401)
})

test('Fonds A parcourt le catalogue autorisé, le portfolio et le drill-down PME', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page, 'fonds')
  await page.goto('/financial-intelligence/portfolios')
  await expect(page.getByRole('heading', { name: /Portfolio Intelligence overview/i })).toBeVisible()
  await page.getByLabel('Date asOf').fill(asOf)
  await page.getByRole('button', { name: /Afficher les portfolios autorisés/i }).click()
  await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
  const fundRow = page.locator('li').filter({ hasText: 'Synthetic Fund A' })
  await expect(fundRow).toContainText('PORTFOLIO-FUND-001')
  await expect(fundRow).toContainText('2 PME')
  await page.screenshot({
    path: path.join(evidenceDirectory, 'FI-PORTFOLIOS-FONDS-A-1440x900.png'),
    animations: 'disabled',
  })
  await fundRow.getByRole('link', { name: 'Ouvrir' }).click()
  await expect(page.getByRole('heading', { name: 'PORTFOLIO-FUND-001' })).toBeVisible()
  await expect(page.getByText(/Fonds FUND-001/)).toBeVisible()
  await expect(page.getByText(/NO_CREDIT_DECISION/)).toBeVisible()
  await expect(page.locator('#fi-companies tbody tr')).toHaveCount(2)
  await page.screenshot({
    path: path.join(evidenceDirectory, 'FI-PORTFOLIO-FUND-001-1440x900.png'),
    animations: 'disabled',
  })
  await page
    .locator('#fi-companies tbody tr')
    .filter({ hasText: 'SME-00001' })
    .getByRole('link', { name: 'Ouvrir' })
    .click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByText(/SME-00001 · fonds FUND-001/)).toBeVisible()
  const governance = page.getByRole('region', {
    name: 'Gouvernance Financial Intelligence',
  })
  await expect(governance).toContainText('POC_SHADOW')
  await expect(governance).toContainText('rulesWeight=1')
  await expect(governance).toContainText('mlWeight=0')
  await page.screenshot({
    path: path.join(evidenceDirectory, 'FI-COMPANY-SME-00001-1440x900.png'),
    animations: 'disabled',
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByText(/SME-00001 · fonds FUND-001/)).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
  await page.screenshot({
    path: path.join(evidenceDirectory, 'FI-COMPANY-SME-00001-390x844.png'),
    animations: 'disabled',
  })
})

test('le token Fonds A ne peut ni lire le Fonds B ni élargir son scope par consumerId', async ({ browser }) => {
  test.skip(devMode, 'Ce scénario exige les sujets OIDC distincts du realm Keycloak.')
  const { context, page, identityHeaders } = await authenticatedPage(browser, 'fonds')
  await page.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
  await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
  expect(identityHeaders().Authorization).toMatch(/^Bearer /)

  const own = await page.request.get(
    `/api/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary?asOf=${asOf}`,
    { headers: { ...identityHeaders(), 'X-Correlation-ID': 'fi-e2e-own' } },
  )
  expect(own.status()).toBe(200)
  const ownPayload = await own.json()
  expect(ownPayload.data.portfolioId).toBe('PORTFOLIO-FUND-001')
  expect(ownPayload.data.fundId).toBe('FUND-001')
  expect(ownPayload.meta.requestId).toBe('fi-e2e-own')

  const injection = await page.request.get(
    `/api/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary?asOf=${asOf}&consumerId=CONSUMER-B`,
    { headers: { ...identityHeaders(), 'X-Correlation-ID': 'fi-e2e-consumer-injection' } },
  )
  expect(injection.status()).toBe(400)
  expect((await injection.json()).code).toBe('UNKNOWN_FILTER')

  const secondCatalogPage = await page.request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}&pageSize=1&offset=1`,
    { headers: { ...identityHeaders(), 'X-Correlation-ID': 'fi-e2e-catalog-offset' } },
  )
  expect(secondCatalogPage.status()).toBe(200)
  const secondCatalogPayload = await secondCatalogPage.json()
  expect(secondCatalogPayload.data.totalCount).toBeGreaterThan(1)
  expect(secondCatalogPayload.data.portfolios).toHaveLength(1)
  expect(secondCatalogPayload.data.portfolios[0].portfolioId).not.toBe('PORTFOLIO-FUND-001')

  const unsupportedCursor = await page.request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}&cursor=opaque`,
    { headers: identityHeaders() },
  )
  expect(unsupportedCursor.status()).toBe(400)
  expect((await unsupportedCursor.json()).code).toBe('UNKNOWN_FILTER')

  const forbidden = await page.request.get(
    `/api/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-002/summary?asOf=${asOf}`,
    { headers: { ...identityHeaders(), 'X-Correlation-ID': 'fi-e2e-cross-fund' } },
  )
  expect(forbidden.status()).toBe(404)
  expect((await forbidden.json()).code).toBe('RESOURCE_NOT_FOUND')
  await context.close()
})

test('le token Fonds B reste limité à son portfolio', async ({ browser }) => {
  test.skip(devMode, 'Ce scénario exige les sujets OIDC distincts du realm Keycloak.')
  const { context, page, identityHeaders } = await authenticatedPage(browser, 'fondsB')
  await page.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
  await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
  const catalog = await page.request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}`,
    { headers: identityHeaders() },
  )
  expect(catalog.status()).toBe(200)
  expect((await catalog.json()).data.portfolios.map((item: { portfolioId: string }) => item.portfolioId)).toEqual([
    'PORTFOLIO-FUND-002',
  ])
  const crossFund = await page.request.get(
    `/api/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary?asOf=${asOf}`,
    { headers: identityHeaders() },
  )
  expect(crossFund.status()).toBe(404)
  await context.close()
})

test('grant expiré et scope manquant sont refusés sans fuite de ressource', async ({ browser }) => {
  test.skip(devMode, 'Ce scénario exige les sujets et scopes OIDC distincts du realm Keycloak.')
  const {
    context: adminContext,
    page: adminPage,
    identityHeaders: adminIdentityHeaders,
  } = await authenticatedPage(browser, 'admin')
  const adminResponse = await adminPage.request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}`,
    { headers: adminIdentityHeaders() },
  )
  expect(adminResponse.status()).toBe(403)
  expect((await adminResponse.json()).code).toBe('FI_ROLE_MISSING')
  await adminContext.close()

  const serviceSecret = process.env.E2E_FI_SERVICE_CLIENT_SECRET
  expect(serviceSecret, 'Le secret E2E du client technique FI doit être injecté.').toBeTruthy()
  const serviceContext = await browser.newContext()
  const servicePage = await serviceContext.newPage()
  const serviceTokenResponse = await servicePage.request.post(
    `${keycloakOrigin}/realms/boa-sme-mvp/protocol/openid-connect/token`,
    {
      form: {
        grant_type: 'client_credentials',
        client_id: 'financial-intelligence-service',
        client_secret: serviceSecret!,
      },
    },
  )
  expect(serviceTokenResponse.status()).toBe(200)
  const serviceToken = (await serviceTokenResponse.json()).access_token as string
  const serviceResponse = await servicePage.request.get(
    `/api/v1/financial-intelligence/portfolios?asOf=${asOf}`,
    { headers: { Authorization: `Bearer ${serviceToken}` } },
  )
  expect(serviceResponse.status()).toBe(403)
  expect((await serviceResponse.json()).code).toBe('FI_ROLE_MISSING')
  await serviceContext.close()

  const expiredContext = await browser.newContext()
  const expiredPage = await expiredContext.newPage()
  await login(expiredPage, 'fondsExpire')
  const expiredPromise = expiredPage.waitForResponse((response) => response.url().includes('/api/v1/financial-intelligence/companies/SME-00001/summary'))
  await expiredPage.goto(`/financial-intelligence/companies/SME-00001?asOf=${asOf}`)
  expect((await expiredPromise).status()).toBe(404)
  await expiredContext.close()

  const limitedContext = await browser.newContext()
  const limitedPage = await limitedContext.newPage()
  await login(limitedPage, 'fondsScopeLimite')
  const limitedPromise = limitedPage.waitForResponse((response) => response.url().includes('/api/v1/financial-intelligence/portfolios?'))
  await limitedPage.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
  expect((await limitedPromise).status()).toBe(403)
  await limitedContext.close()
})

test('contrats FI : point-in-time, minimisation, lineage et cohérence des références', async ({ browser }) => {
  const { context, page, identityHeaders } = await authenticatedPage(browser, 'fonds')
  await page.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
  await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
  const headers = { ...identityHeaders(), 'X-Correlation-ID': 'fi-contract-e2e' }
  const summary = await page.request.get(
    `/api/v1/financial-intelligence/companies/SME-00001/summary?asOf=${asOf}`,
    { headers },
  )
  expect(summary.status()).toBe(200)
  const payload = await summary.json()
  expect(payload.meta.contractVersion).toBe('fi.v1')
  expect(payload.meta.executionMode).toBe('DETERMINISTIC_RULES')
  expect(payload.meta.mlGovernanceStatus).toBe('VERIFIED')
  expect(payload.meta.deploymentMode).toBe('POC_SHADOW')
  expect(payload.meta.mlMode).toBe('POC_SHADOW')
  expect(payload.meta.rulesWeight).toBe(1)
  expect(payload.meta.mlWeight).toBe(0)
  expect(payload.meta.syntheticData).toBe(true)
  expect(payload.meta.nonProduction).toBe(true)
  expect(payload.meta.downstreamCallCount).toBe(5)
  if (!devMode) expect(payload.meta.requestId).toBe('fi-contract-e2e')
  expect(payload.data.disclaimer).toBe('NO_CREDIT_DECISION')
  expect(payload.data.metrics.length).toBeGreaterThan(0)
  expect(payload.data.cashPosition.averageBalance).not.toBeNull()
  expect(payload.data.flowSummary.inflows).not.toBeNull()
  expectNoRawFinancialFields(payload)

  const signals = await page.request.get(
    `/api/v1/financial-intelligence/companies/SME-00001/signals?asOf=${asOf}`,
    { headers },
  )
  const opportunities = await page.request.get(
    `/api/v1/financial-intelligence/companies/SME-00001/opportunities?asOf=${asOf}`,
    { headers },
  )
  expect(signals.status()).toBe(200)
  expect(opportunities.status()).toBe(200)
  const signalPayload = await signals.json()
  const opportunityPayload = await opportunities.json()
  expect(signalPayload.data.length).toBeGreaterThan(0)
  expect(opportunityPayload.data.length).toBeGreaterThan(0)
  expect(signalPayload.data.map((item: { signalRef: string }) => item.signalRef)).toEqual(
    payload.data.signals.map((item: { signalRef: string }) => item.signalRef),
  )
  expect(
    opportunityPayload.data.map((item: { opportunityId: string }) => item.opportunityId),
  ).toEqual(
    payload.data.opportunities.map((item: { opportunityId: string }) => item.opportunityId),
  )
  for (const signal of signalPayload.data) {
    expect(signal.status).toBeNull()
    expect(signal.stateAsOfStatus).toBe('NOT_IMPLEMENTED')
  }
  for (const opportunity of opportunityPayload.data) {
    expect(opportunity.status).toBeNull()
    expect(opportunity.stateAsOfStatus).toBe('NOT_IMPLEMENTED')
  }

  const historical = await page.request.get(
    '/api/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary?asOf=2024-12-31',
    { headers },
  )
  expect(historical.status()).toBe(200)
  expect((await historical.json()).data.companyCount).toBe(0)
  await context.close()
})
