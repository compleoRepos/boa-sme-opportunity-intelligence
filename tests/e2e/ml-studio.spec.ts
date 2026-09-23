import { expect, test } from '@playwright/test'
import path from 'node:path'

import { login } from './auth'

function evidencePath(name: string) {
  return path.resolve(process.cwd(), `../../docs/evidence/ml/${name}-1440x900.png`)
}

async function logout(page: import('@playwright/test').Page) {
  await page.locator('.profile-btn').click()
  await page.getByRole('menuitem', { name: /Se déconnecter/ }).click()
  await page.waitForURL(/\/login/, { timeout: 30_000 })
}

async function dismissToasts(page: import('@playwright/test').Page) {
  const closeButtons = page.getByRole('button', { name: 'Fermer la notification' })
  while (await closeButtons.count()) await closeButtons.first().click()
}

async function captureViewport(
  page: import('@playwright/test').Page,
  name: string,
  focus?: import('@playwright/test').Locator,
) {
  if (focus) await focus.scrollIntoViewIfNeeded()
  else await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: evidencePath(name) })
}

async function openTab(page: import('@playwright/test').Page, name: string, expected: RegExp) {
  await page.getByRole('tab', { name }).click()
  await expect(page.getByText(expected).first()).toBeVisible()
}

test('Karim entraîne un modèle DEMO_ONLY et consulte les six onglets gouvernés', async ({ page }) => {
  let authHeaders: Record<string, string> = {}
  page.on('request', (request) => {
    if (!request.url().includes('/api/v1/admin/')) return
    const requestHeaders = request.headers()
    if (requestHeaders.authorization?.startsWith('Bearer '))
      authHeaders = { Authorization: requestHeaders.authorization }
    else if (requestHeaders['x-dev-principal'])
      authHeaders = { 'X-Dev-Principal': requestHeaders['x-dev-principal'] }
  })
  await login(page, 'karim')
  await page.goto('/back-office/studio-ml')

  await expect(page.getByRole('heading', { name: 'Analyser, entraîner, comparer, gouverner' })).toBeVisible()
  await expect(page.getByText('POC_SHADOW', { exact: true })).toBeVisible()
  await expect(page.getByText(/Aucun LLM, aucun GPU, aucune décision de crédit/)).toBeVisible()
  await expect(page.getByText(/Pourquoi le ML n’influence pas encore les priorités/)).toBeVisible()
  const activePolicyResponse = await page.request.get('/api/v1/admin/scoring-policies/active', { headers: authHeaders })
  const summaryResponse = await page.request.get('/api/v1/admin/ml/governance/studio-summary', { headers: authHeaders })
  expect(activePolicyResponse.status()).toBe(200)
  expect(summaryResponse.status()).toBe(200)
  const activePolicy = await activePolicyResponse.json()
  const summary = await summaryResponse.json()
  expect(summary.activePolicy).toMatchObject({
    policyId: activePolicy.policyId,
    version: activePolicy.version,
    status: 'ACTIVE',
    rulesWeight: activePolicy.weights.rules,
    mlWeight: activePolicy.weights.ml,
  })
  const g3 = summary.gates.find((gate: { gate: string }) => gate.gate === 'G3')
  expect(g3?.status).toBe(activePolicy.weights.ml > 0 ? 'PASSED' : 'BLOCKED')
  await captureViewport(page, 'STUDIO-ML-01-VUE-ENSEMBLE')

  await openTab(page, 'Données et étiquettes', /Définitions de cible/)
  await expect(page.getByText(/Jeu de démonstration, étiquettes synthétiques, non promouvable/)).toBeVisible()
  await captureViewport(page, 'STUDIO-ML-02-DONNEES')

  await openTab(page, 'Entraînement', /Lancer un entraînement/)
  await page.getByLabel('Manifeste').selectOption({ index: 1 })
  await expect(page.getByText(/DEMO_ONLY/).first()).toBeVisible()
  await page.getByLabel('Justification').fill('Preuve E2E Karim de l’entraînement CPU gouverné et non promouvable')
  await page.getByRole('button', { name: /Lancer l’entraînement/ }).click()
  await expect(page.getByRole('progressbar')).toBeVisible()
  await dismissToasts(page)
  await captureViewport(page, 'STUDIO-ML-03A-PROGRESSION')
  await expect(page.getByRole('button', { name: /Enregistrer comme version candidate/ })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('DEMO_ONLY', { exact: true }).first()).toBeVisible()
  await expect(page.locator('#training-history tbody tr').first()).toContainText(/Succeeded|Réussi/)
  await dismissToasts(page)
  await captureViewport(page, 'STUDIO-ML-03-ENTRAINEMENT', page.locator('#training-result'))
  const firstRegistration = page.waitForResponse(
    (response) => response.url().includes('/ml/governance/runs') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: /Enregistrer comme version candidate/ }).click()
  const firstRegistrationResponse = await firstRegistration
  expect(firstRegistrationResponse.ok()).toBeTruthy()
  const firstModelVersion = String((await firstRegistrationResponse.json()).run.modelVersion)

  await page.getByLabel('Graine aléatoire').fill('20260922')
  await page.getByLabel('Justification').fill('Second modèle de démonstration pour comparaison sur un jeu de test commun')
  await page.getByRole('button', { name: /Lancer l’entraînement/ }).click()
  await expect(page.getByRole('progressbar')).toBeVisible()
  await expect(page.getByRole('button', { name: /Enregistrer comme version candidate/ })).toBeVisible({ timeout: 60_000 })
  const secondRegistration = page.waitForResponse(
    (response) => response.url().includes('/ml/governance/runs') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: /Enregistrer comme version candidate/ }).click()
  const secondRegistrationResponse = await secondRegistration
  expect(secondRegistrationResponse.ok()).toBeTruthy()
  const secondModelVersion = String((await secondRegistrationResponse.json()).run.modelVersion)

  await openTab(page, 'Évaluation', /Choisir deux versions|Aucun modèle enregistré/)
  const modelA = page.getByRole('combobox', { name: 'Modèle A' })
  const modelB = page.getByRole('combobox', { name: 'Modèle B' })
  await expect(modelA).toBeVisible()
  const demoValues: string[] = []
  for (const option of await modelA.locator('option').all()) {
    if ((await option.textContent())?.includes('DEMO_ONLY')) {
      const value = await option.getAttribute('value')
      if (value) demoValues.push(value)
    }
  }
  expect(demoValues.length).toBeGreaterThanOrEqual(2)
  expect(demoValues).toEqual(expect.arrayContaining([firstModelVersion, secondModelVersion]))
  await modelA.selectOption(firstModelVersion)
  await modelB.selectOption(secondModelVersion)
  await expect(page.getByText(/Dix plus grands changements/)).toBeVisible()
  await dismissToasts(page)
  await captureViewport(page, 'STUDIO-ML-04-EVALUATION')

  await openTab(page, 'Fusion règles / ML', /Ratio règles \/ ML/)
  const slider = page.getByRole('slider', { name: 'Part ML' })
  if (await slider.isVisible().catch(() => false)) {
    await expect(slider).toHaveAttribute('min', '0')
    await expect(slider).toHaveAttribute('max', '50')
    await expect(slider).toHaveAttribute('step', '5')
  }
  await page.getByRole('button', { name: /Créer la version/ }).click()
  await expect(page.getByText(/Version \d+ créée/)).toBeVisible()
  await page.getByRole('button', { name: 'Simuler' }).click()
  await page.getByRole('button', { name: 'Confirmer' }).click()
  await expect(page.getByText(/Simulation uniquement/)).toBeVisible()
  await expect(page.getByText(/Opportunités simulées/)).toBeVisible()
  await expect(page.getByText('SIMULATED', { exact: true })).toBeVisible()
  await dismissToasts(page)
  await captureViewport(page, 'STUDIO-ML-05-FUSION', page.getByText(/Impact portefeuille fourni par l’API/))
  await page.getByRole('button', { name: 'Soumettre' }).click()
  await page.getByRole('button', { name: 'Confirmer' }).click()
  await expect(page.getByText('SUBMITTED', { exact: true })).toBeVisible()
  const submittedTitle = await page
    .getByText(/commercial-rules-shadow-poc · v\d+/)
    .last()
    .textContent()
  const submittedVersion = submittedTitle?.match(/v(\d+)/)?.[1]
  expect(Object.keys(authHeaders).length).toBeGreaterThan(0)
  expect(submittedVersion).toBeTruthy()
  const selfApproval = await page.request.post(
    `/api/v1/admin/scoring-policies/commercial-rules-shadow-poc/versions/${submittedVersion}/approve`,
    {
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      data: { reason: 'Cette auto-approbation doit être refusée par le serveur' },
    },
  )
  expect(selfApproval.status()).toBe(403)

  await openTab(page, 'Approbation et journal', /Journal append-only/)
  await expect(
    page.getByText(/DEMO_ONLY : soumission, approbation et promotion désactivées/).first(),
  ).toBeVisible()
  await expect(page.getByText(/l’auteur ne peut pas approuver sa propre politique/i).first()).toBeVisible()
  await dismissToasts(page)
  await captureViewport(page, 'STUDIO-ML-06-APPROBATION')

  await logout(page)
  await login(page, 'approbateur')
  await page.goto('/back-office/studio-ml')
  await openTab(page, 'Approbation et journal', /Journal append-only/)
  const submittedPolicy = page
    .getByText(`commercial-rules-shadow-poc · v${submittedVersion}`, { exact: true })
    .locator('xpath=ancestor::article')
  await submittedPolicy.getByRole('button', { name: 'Approuver' }).click()
  await page.getByRole('button', { name: 'Confirmer' }).click()
  await expect(page.getByText(/Transition de politique enregistrée/)).toBeVisible()
  await submittedPolicy.getByRole('button', { name: 'Publier' }).click()
  await page.getByRole('button', { name: 'Confirmer' }).click()
  await expect(page.getByText(/Transition de politique enregistrée/).last()).toBeVisible()

  await logout(page)
  await login(page, 'admin')
  await page.goto('/back-office/studio-ml')
  await openTab(page, 'Approbation et journal', /Journal append-only/)
  const demoPromotion = await page.request.post(
    `/api/v1/admin/ml/governance/runs/sales-propensity/${firstModelVersion}/promote`,
    {
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      data: { reason: 'La promotion du modèle DEMO_ONLY doit rester refusée' },
    },
  )
  expect(demoPromotion.status()).toBe(409)
  await expect(page.getByRole('button', { name: 'Activer' }).last()).toBeDisabled()
  await expect(page.getByText(/La porte G3 n’est pas franchie/).first()).toBeVisible()
})
