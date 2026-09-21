import { expect, test, type Page } from '@playwright/test'

import { devMode, login } from './auth'

const businessAnalystDevHeader = JSON.stringify({
  subject: 'analyst-e2e',
  username: 'business.analyst.e2e',
  roles: ['BUSINESS_ANALYST', 'DATA_ANALYST'],
  branchIds: ['ALL'],
})

async function authenticatedHeaders(
  page: Page,
  route: string,
  devPrincipal?: string,
): Promise<Record<string, string>> {
  if (devMode && devPrincipal) {
    await page.goto(route)
    return { 'X-Dev-Principal': devPrincipal }
  }
  let headers: Record<string, string> = {}
  page.on('request', (request) => {
    if (!request.url().includes('/api/v1/')) return
    const requestHeaders = request.headers()
    if (requestHeaders.authorization?.startsWith('Bearer ')) {
      headers = { Authorization: requestHeaders.authorization }
    } else if (requestHeaders['x-dev-principal']) {
      headers = { 'X-Dev-Principal': requestHeaders['x-dev-principal'] }
    }
  })
  await page.goto(route)
  await expect.poll(() => Object.keys(headers).length, { timeout: 20_000 }).toBeGreaterThan(0)
  return headers
}

test('gouvernance persistée, readiness prudente et RBAC administratif', async ({ browser }) => {
  const analystContext = await browser.newContext()
  const analyst = await analystContext.newPage()
  await login(analyst, 'analyste')
  const analystAuthHeaders = await authenticatedHeaders(
    analyst,
    '/produits',
    businessAnalystDevHeader,
  )

  const policyResponse = await analyst.request.get('/api/v1/admin/scoring-policies/active', {
    headers: { ...analystAuthHeaders, 'X-Correlation-ID': 'e2e-governance-policy' },
  })
  expect(policyResponse.status()).toBe(200)
  const policy = await policyResponse.json()
  expect(policy.policyId).toBe('commercial-rules-shadow-poc')
  expect(policy.status).toBe('ACTIVE')
  expect(Number(policy.weights.rules)).toBe(1)
  expect(Number(policy.weights.ml)).toBe(0)
  expect(policy.operationalMode).toBe('RULES_ONLY')
  expect(policy.mlObservationMode).toBe('POC_SHADOW')

  const readinessResponse = await analyst.request.get('/api/v1/admin/readiness', {
    headers: { ...analystAuthHeaders, 'X-Correlation-ID': 'e2e-governance-readiness' },
  })
  expect(readinessResponse.status()).toBe(200)
  const readiness = await readinessResponse.json()
  expect(readiness.overallStatus).toMatch(/^(READY|BLOCKED)$/)
  expect(readiness.deploymentMode).toBe('POC_SHADOW')
  expect(readiness.productionPerformanceClaim).toBe(false)
  expect(readiness.checks.length).toBeGreaterThan(0)

  const championResponse = await analyst.request.get('/api/v1/admin/ml/governance/champion', {
    headers: { ...analystAuthHeaders, 'X-Correlation-ID': 'e2e-governance-champion' },
  })
  expect(championResponse.status()).toBe(200)
  const champion = await championResponse.json()
  expect(champion.mode).toBe('POC_SHADOW')

  const driftTrace = `e2e-drift-${Date.now()}`
  const driftObservation = await analyst.request.post(
    '/api/v1/admin/monitoring/observations',
    {
      headers: { ...analystAuthHeaders, 'X-Correlation-ID': driftTrace },
      data: {
        domain: 'FEATURE',
        metric: 'cash_inflow_growth_90d_psi',
        value: 0.04,
        thresholds: {
          warning: 0.1,
          critical: 0.2,
          method: 'PSI',
          referenceVersion: 'synthetic-baseline-2026-09',
        },
        sampleSize: 500,
        segment: 'SME',
        population: 'synthetic-poc',
        referenceVersion: 'synthetic-baseline-2026-09',
      },
    },
  )
  expect(driftObservation.status()).toBe(202)
  expect((await driftObservation.json()).status).toBe('OK')
  const operationalObservation = await analyst.request.post(
    '/api/v1/admin/monitoring/observations',
    {
      headers: { ...analystAuthHeaders },
      data: {
        domain: 'OPERATIONAL',
        metric: 'latency_ms',
        latencyMs: 120,
        requests: 100,
        errors: 1,
        volume: 100,
        rulesOnlyCount: 5,
        thresholds: {},
      },
    },
  )
  expect(operationalObservation.status()).toBe(202)
  const monitoringHistory = await analyst.request.get(
    '/api/v1/admin/monitoring/history?limit=10',
    { headers: { ...analystAuthHeaders } },
  )
  expect(monitoringHistory.status()).toBe(200)
  const monitoring = await monitoringHistory.json()
  expect(monitoring.meta.count).toBeGreaterThanOrEqual(2)
  expect(monitoring.data.some((item: { traceId: string }) => item.traceId === driftTrace)).toBe(true)

  await analystContext.close()

  const ccContext = await browser.newContext()
  const cc = await ccContext.newPage()
  await login(cc, 'cc')
  const ccAuthHeaders = await authenticatedHeaders(cc, '/')
  const forbidden = await cc.request.get('/api/v1/admin/readiness', {
    headers: { ...ccAuthHeaders, 'X-Correlation-ID': 'e2e-governance-forbidden' },
  })
  expect(forbidden.status()).toBe(403)
  await ccContext.close()
})

test('workflow MLOps shadow avec séparation des rôles et promotion bloquée', async ({ browser }) => {
  const analystContext = await browser.newContext()
  const analyst = await analystContext.newPage()
  await login(analyst, 'analyste')
  const analystAuthHeaders = await authenticatedHeaders(
    analyst,
    '/produits',
    businessAnalystDevHeader,
  )

  const approverContext = await browser.newContext()
  const approver = await approverContext.newPage()
  await login(approver, 'approbateur')
  const approverAuthHeaders = await authenticatedHeaders(approver, '/back-office/regles')

  const adminContext = await browser.newContext()
  const admin = await adminContext.newPage()
  await login(admin, 'admin')
  const adminAuthHeaders = await authenticatedHeaders(admin, '/back-office/modeles')

  const suffix = Date.now().toString()
  const firstVersion = `gov-a-${suffix}`
  const secondVersion = `gov-b-${suffix}`
  const featureOrder = [
    'cash_inflow_growth_90d',
    'supplier_payment_growth_90d',
    'international_activity_ratio_90d',
    'balance_strength_90d',
    'activity_density_90d',
    'analytics_coverage_90d',
    'customer_tenure_ratio',
    'segment_medium',
    'confirmed_signal_ratio',
    'published_rule_match_strength',
  ]
  const coefficients = {
    cash_inflow_growth_90d: 0.8,
    supplier_payment_growth_90d: 0.35,
    international_activity_ratio_90d: 1.1,
    balance_strength_90d: 0.65,
    activity_density_90d: 0.45,
    analytics_coverage_90d: 0.3,
    customer_tenure_ratio: 0.2,
    segment_medium: 0.25,
    confirmed_signal_ratio: 0.4,
    published_rule_match_strength: 0.75,
  }
  const payload = (modelVersion: string, intercept: number) => ({
    modelId: 'sales-propensity',
    modelVersion,
    featureVersion: 'sales-features-v2',
    datasetVersion: `synthetic-governance-${suffix}`,
    trainingPeriodFrom: '2026-01-01',
    trainingPeriodTo: '2026-06-30',
    validationPeriodFrom: '2026-07-01',
    validationPeriodTo: '2026-07-31',
    testPeriodFrom: '2026-08-01',
    testPeriodTo: '2026-08-31',
    codeVersion: 'e2e-governance',
    hyperparameters: { solver: 'deterministic-cpu' },
    metrics: {
      'Precision@K': 'N/A',
      'Recall@K': 'N/A',
      'PR-AUC': 'N/A',
      calibrationStatus: 'NOT_VALIDATED',
      productionPerformanceClaim: false,
    },
    lineage: {
      datasetId: `synthetic-governance-${suffix}`,
      featureSetVersion: 'sales-features-v2',
      trainingCutoff: '2026-06-30',
      sourceSnapshots: ['synthetic-seed-2026-09'],
      codeRevision: 'e2e-governance',
      labelDefinition: 'commercial_conversion_30d',
      datasetManifestHash: 'a'.repeat(64),
      sourceKind: 'SYNTHETIC',
      targetOutcome: 'CONVERTED',
      horizonDays: 30,
      population: { segment: 'SME', country: 'MA' },
      examples: [
        {
          entityId: 'SME-E2E',
          observationAsOf: '2026-06-15',
          features: [
            {
              featureName: 'cash_inflow_growth_90d',
              featureTimestamp: '2026-06-14',
              observationAsOf: '2026-06-15',
              source: 'analytics:snapshot',
            },
          ],
        },
      ],
    },
    deploymentMode: 'POC_SHADOW',
    datasetManifestHash: 'a'.repeat(64),
    artifactChecksum: 'b'.repeat(64),
    targetOutcome: 'CONVERTED',
    horizonDays: 30,
    reason: 'E2E gouvernance sans revendication de performance',
    artifact: {
      algorithm: 'LOGISTIC_REGRESSION',
      featureOrder,
      coefficients,
      intercept,
      threshold: 0.65,
    },
  })
  const analystHeaders = {
    ...analystAuthHeaders,
    'Content-Type': 'application/json',
  }
  const approverHeaders = {
    ...approverAuthHeaders,
    'Content-Type': 'application/json',
  }
  const adminHeaders = {
    ...adminAuthHeaders,
    'Content-Type': 'application/json',
  }

  for (const [modelVersion, intercept] of [
    [firstVersion, -1.15],
    [secondVersion, -1.05],
  ] as const) {
    const registered = await analyst.request.post('/api/v1/admin/ml/governance/runs', {
      headers: analystHeaders,
      data: payload(modelVersion, intercept),
    })
    expect(registered.status()).toBe(202)
    for (const action of ['lineage/validate', 'submit']) {
      const response = await analyst.request.post(
        `/api/v1/admin/ml/governance/runs/sales-propensity/${modelVersion}/${action}`,
        { headers: analystHeaders, data: { reason: `E2E ${action}` } },
      )
      expect(response.status()).toBe(202)
    }
    const selfApproval = await analyst.request.post(
      `/api/v1/admin/ml/governance/runs/sales-propensity/${modelVersion}/approve`,
      { headers: analystHeaders, data: { reason: 'auto-approbation interdite' } },
    )
    expect(selfApproval.status()).toBe(403)
    const approved = await approver.request.post(
      `/api/v1/admin/ml/governance/runs/sales-propensity/${modelVersion}/approve`,
      { headers: approverHeaders, data: { reason: 'revue indépendante E2E' } },
    )
    expect(approved.status()).toBe(202)
    const selfPromotion = await approver.request.post(
      `/api/v1/admin/ml/governance/runs/sales-propensity/${modelVersion}/promote`,
      { headers: approverHeaders, data: { reason: 'promotion par le reviewer interdite' } },
    )
    expect(selfPromotion.status()).toBe(403)
    const blockedPromotion = await admin.request.post(
      `/api/v1/admin/ml/governance/runs/sales-propensity/${modelVersion}/promote`,
      { headers: adminHeaders, data: { reason: 'release manager E2E' } },
    )
    expect(blockedPromotion.status()).toBe(409)
    expect(JSON.stringify(await blockedPromotion.json())).toContain('ML_ACTIVATION_BLOCKED')
  }

  const activeModel = await analyst.request.get('/api/v1/ml/models/active', {
    headers: { ...analystAuthHeaders },
  })
  expect(activeModel.status()).toBe(200)
  const activeModelBody = await activeModel.json()
  expect(activeModelBody.modelVersion).not.toBe(firstVersion)
  expect(activeModelBody.modelVersion).not.toBe(secondVersion)

  await analystContext.close()
  await approverContext.close()
  await adminContext.close()
})

test('Scoring Policy hybride simulable mais non activable sans labels BOA', async ({ browser }) => {
  const analystContext = await browser.newContext()
  const analyst = await analystContext.newPage()
  await login(analyst, 'analyste')
  const analystAuthHeaders = await authenticatedHeaders(
    analyst,
    '/produits',
    businessAnalystDevHeader,
  )
  const approverContext = await browser.newContext()
  const approver = await approverContext.newPage()
  await login(approver, 'approbateur')
  const approverAuthHeaders = await authenticatedHeaders(approver, '/back-office/regles')
  const adminContext = await browser.newContext()
  const admin = await adminContext.newPage()
  await login(admin, 'admin')
  const adminAuthHeaders = await authenticatedHeaders(admin, '/back-office')
  const trace = `e2e-policy-${Date.now()}`
  const analystHeaders = {
    ...analystAuthHeaders,
    'Content-Type': 'application/json',
    'X-Correlation-ID': trace,
  }
  const approverHeaders = {
    ...approverAuthHeaders,
    'Content-Type': 'application/json',
    'X-Correlation-ID': trace,
  }
  const adminHeaders = {
    ...adminAuthHeaders,
    'Content-Type': 'application/json',
    'X-Correlation-ID': trace,
  }
  const policyId = 'commercial-rules-shadow-poc'
  const created = await analyst.request.post(
    `/api/v1/admin/scoring-policies/${policyId}/versions`,
    {
      headers: analystHeaders,
      data: {
        weights: { rules: 0.6, ml: 0.4 },
        reason: 'simulation E2E de pondération assistive',
      },
    },
  )
  expect(created.status()).toBe(202)
  const version = Number((await created.json()).version)
  expect(version).toBeGreaterThan(1)
  const simulationId = `policy-simulation-${Date.now()}`
  const simulated = await analyst.request.post(
    `/api/v1/admin/scoring-policies/${policyId}/versions/${version}/simulate`,
    {
      headers: analystHeaders,
      data: {
        reason: 'simulation POC sans performance de production',
        simulationId,
      },
    },
  )
  expect(simulated.status()).toBe(202)
  const simulation = await simulated.json()
  expect(simulation.simulationId).toBe(simulationId)
  expect(simulation.simulation.sampleCount).toBeGreaterThan(0)
  expect(simulation.simulation.source).toBe('PERSISTED_OPPORTUNITIES_WITH_ML_SHADOW')
  const submitted = await analyst.request.post(
    `/api/v1/admin/scoring-policies/${policyId}/versions/${version}/submit`,
    { headers: analystHeaders, data: { reason: 'soumission E2E', simulationId } },
  )
  expect(submitted.status()).toBe(202)
  const selfApproval = await analyst.request.post(
    `/api/v1/admin/scoring-policies/${policyId}/versions/${version}/approve`,
    { headers: analystHeaders, data: { reason: 'auto-approbation interdite', simulationId } },
  )
  expect(selfApproval.status()).toBe(403)
  for (const action of ['approve', 'publish']) {
    const response = await approver.request.post(
      `/api/v1/admin/scoring-policies/${policyId}/versions/${version}/${action}`,
      {
        headers: approverHeaders,
        data: { reason: `E2E ${action}`, simulationId },
      },
    )
    expect(response.status()).toBe(202)
  }
  const blockedActivation = await admin.request.post(
    `/api/v1/admin/scoring-policies/${policyId}/versions/${version}/activate`,
    {
      headers: adminHeaders,
      data: { reason: 'activation interdite sans labels BOA', simulationId },
    },
  )
  expect(blockedActivation.status()).toBe(409)
  expect(JSON.stringify(await blockedActivation.json())).toContain('ML_SHADOW_POLICY_REQUIRED')
  const activeBaseline = await analyst.request.get('/api/v1/admin/scoring-policies/active', {
    headers: { ...analystAuthHeaders },
  })
  expect(activeBaseline.status()).toBe(200)
  const baseline = await activeBaseline.json()
  expect(baseline.version).not.toBe(version)
  expect(Number(baseline.weights.rules)).toBe(1)
  expect(Number(baseline.weights.ml)).toBe(0)
  await analystContext.close()
  await approverContext.close()
  await adminContext.close()
})
