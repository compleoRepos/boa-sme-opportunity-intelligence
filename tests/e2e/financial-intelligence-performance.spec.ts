import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { devMode, login } from './auth'

const asOf = '2026-09-30'
const iterations = Number(process.env.FI_PERFORMANCE_ITERATIONS || '5')
const evidenceDirectory = path.resolve(
  process.cwd(),
  process.env.FI_EVIDENCE_DIR ?? '../../docs/evidence/financial-intelligence',
)
const outputFile = path.join(evidenceDirectory, 'RESULTATS-PERFORMANCE-FI.json')
const cases = [
  { size: 10, portfolioId: 'PORTFOLIO-PERF-010', p95ThresholdMs: 30_000 },
  { size: 50, portfolioId: 'PORTFOLIO-PERF-050', p95ThresholdMs: 90_000 },
  { size: 100, portfolioId: 'PORTFOLIO-PERF-100', p95ThresholdMs: 180_000 },
  { size: 500, portfolioId: 'PORTFOLIO-PERF-500', p95ThresholdMs: 600_000 },
] as const

function percentile(values: number[], ratio: number) {
  const sorted = [...values].sort((left, right) => left - right)
  return sorted[Math.max(0, Math.ceil(sorted.length * ratio) - 1)]
}

test('benchmark portfolio FI 10/50/100/500 PME avec P50/P95 documentés', async ({ page }) => {
  test.skip(devMode, 'Le benchmark final est exécuté avec un token OIDC Fonds réel.')
  test.setTimeout(35 * 60_000)
  let authorization = ''
  page.on('request', (request) => {
    const candidate = request.headers().authorization
    if (candidate?.startsWith('Bearer ')) authorization = candidate
  })
  await login(page, 'fonds')
  await page.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
  await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
  expect(authorization).toMatch(/^Bearer /)
  await mkdir(evidenceDirectory, { recursive: true })

  const results = []
  for (const benchmark of cases) {
    const durationsMs: number[] = []
    const downstreamCallCounts: number[] = []
    const mlGovernanceStatuses: string[] = []
    for (let iteration = 1; iteration <= iterations; iteration += 1) {
      authorization = ''
      await page.goto(`/financial-intelligence/portfolios?asOf=${asOf}`)
      await expect(page.getByRole('heading', { name: /Portfolios autorisés/i })).toBeVisible()
      expect(authorization).toMatch(/^Bearer /)
      const startedAt = Date.now()
      const response = await page.request.get(
        `/api/v1/financial-intelligence/portfolios/${benchmark.portfolioId}/summary?asOf=${asOf}`,
        {
          headers: {
            Authorization: authorization,
            'X-Correlation-ID': `fi-perf-${benchmark.size}-${iteration}`,
          },
          timeout: benchmark.p95ThresholdMs,
        },
      )
      expect(response.status(), await response.text()).toBe(200)
      const payload = await response.json()
      expect(payload.data.companyCount).toBe(benchmark.size)
      expect(payload.meta.executionMode).toBe('DETERMINISTIC_RULES')
      expect(['VERIFIED', 'UNAVAILABLE']).toContain(payload.meta.mlGovernanceStatus)
      mlGovernanceStatuses.push(payload.meta.mlGovernanceStatus)
      if (payload.meta.mlGovernanceStatus === 'VERIFIED') {
        expect(payload.meta.deploymentMode).toBe('POC_SHADOW')
        expect(payload.meta.mlMode).toBe('POC_SHADOW')
        expect(payload.meta.rulesWeight).toBe(1)
        expect(payload.meta.mlWeight).toBe(0)
      } else {
        expect(payload.meta.deploymentMode).toBeNull()
        expect(payload.meta.mlMode).toBeNull()
        expect(payload.meta.rulesWeight).toBeNull()
        expect(payload.meta.mlWeight).toBeNull()
      }
      expect(payload.meta.downstreamCallCount).toBe(benchmark.size * 5)
      expect(payload.meta.fanOutConcurrency).toBeLessThanOrEqual(20)
      downstreamCallCounts.push(payload.meta.downstreamCallCount)
      durationsMs.push(Date.now() - startedAt)
    }
    const p50Ms = percentile(durationsMs, 0.5)
    const p95Ms = percentile(durationsMs, 0.95)
    const dashboardStartedAt = Date.now()
    await page.goto(
      `/financial-intelligence/portfolios/${benchmark.portfolioId}?asOf=${asOf}`,
    )
    await expect(page.getByRole('heading', { name: benchmark.portfolioId })).toBeVisible({
      timeout: benchmark.p95ThresholdMs,
    })
    const dashboardDurationMs = Date.now() - dashboardStartedAt
    results.push({
      portfolioId: benchmark.portfolioId,
      customerCount: benchmark.size,
      iterations,
      durationsMs,
      downstreamCallCounts,
      mlGovernanceStatuses: [...new Set(mlGovernanceStatuses)],
      p50Ms,
      p95Ms,
      dashboardDurationMs,
      p95ThresholdMs: benchmark.p95ThresholdMs,
      thresholdStatus: p95Ms <= benchmark.p95ThresholdMs ? 'PASS' : 'FAIL',
      thresholdQualification: 'HYPOTHÈSE À VALIDER AVEC BOA',
    })
  }
  const status = results.every((item) => item.thresholdStatus === 'PASS') ? 'PASS' : 'FAIL'
  await writeFile(
    outputFile,
    `${JSON.stringify({
      schemaVersion: '1.0',
      status,
      generatedAt: new Date().toISOString(),
      source: {
        branch: process.env.FI_SOURCE_BRANCH || 'UNKNOWN',
        revision: process.env.FI_SOURCE_REVISION || 'UNKNOWN',
        codeDigest: process.env.FI_CODE_DIGEST || 'UNKNOWN',
        digestScope: process.env.FI_DIGEST_SCOPE || 'runtime',
        digestManifest: process.env.FI_DIGEST_MANIFEST || 'SOURCE-MANIFEST-FI.json',
        digestAlgorithm: 'SHA-256 of path-sorted sha256sum lines',
      },
      environment: {
        stack: 'Docker Compose isolated',
        authentication: 'Keycloak OIDC Authorization Code + PKCE',
        portfolioConcurrency: Number(process.env.FI_PORTFOLIO_CONCURRENCY || '20'),
      },
      results,
      limitations: [
        'POC / SYNTHETIC DATA / NON-PRODUCTION.',
        'Les seuils de performance sont une HYPOTHÈSE À VALIDER AVEC BOA.',
        'Mesure mono-nœud sans charge concurrente multi-utilisateur.',
      ],
    }, null, 2)}\n`,
    'utf8',
  )
  expect(status).toBe('PASS')
})
