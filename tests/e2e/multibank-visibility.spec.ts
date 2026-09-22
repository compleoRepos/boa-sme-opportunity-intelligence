import path from 'node:path'
import { expect, test } from '@playwright/test'

import { login } from './auth'

const evidence = (name: string) => path.resolve(
  process.cwd(),
  '../../docs/evidence/visibility',
  name,
)

test('Ahmed déclare une relation secondaire et consulte la reconquête de flux', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page, 'cc')
  await page.goto('/clients/SME-00040?panneau=visibilite')

  const visibility = page.getByRole('dialog')
  await expect(visibility).toContainText('Visibilité des flux · Alizé Tech SARL')
  await expect(visibility).toContainText('faible')
  await expect(visibility).toContainText('Rapport encaissements / chiffre d’affaires')
  await expect(visibility).toContainText('25 %')

  await visibility.getByRole('button', { name: 'Déclarer la relation bancaire' }).click()
  await visibility.getByLabel('Relation bancaire').selectOption('SECONDARY')
  await visibility.getByLabel('Motif').fill('Relation secondaire confirmée lors du parcours pilote multibancarisé')
  await visibility.getByRole('button', { name: 'Enregistrer la déclaration' }).click()

  await expect(visibility).toContainText('Déclaration enregistrée et auditée.')
  await expect(visibility).toContainText('Secondaire')
  await page.screenshot({
    path: evidence('VISIBILITE-FLUX-AHMED-1440x900.png'),
    fullPage: false,
  })

  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText(/Chaîne d’évidence — Domiciliation des flux/)).toBeVisible()
  await page.locator('#why').getByRole('button', { name: 'Voir l’opportunité' }).click()

  const opportunity = page.getByRole('dialog')
  await expect(opportunity).toContainText('Domiciliation des flux')
  await expect(opportunity).toContainText('Reconquête')
  await expect(opportunity).toContainText('Pack Business PME')
  await expect(opportunity).toContainText('Priorité')
  await page.screenshot({
    path: evidence('OPPORTUNITE-DOMICILIATION-AHMED-1440x900.png'),
    fullPage: false,
  })
})

test('Salma consulte la répartition de visibilité et la domiciliation dans son agence', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page, 'agence')

  await expect(page.getByRole('heading', { name: /^Agence / })).toBeVisible()
  const visibility = page.locator('#visibility-dist')
  await expect(visibility).toContainText('Visibilité des flux')
  await expect(visibility).toContainText('Répartition des PME')
  await expect(visibility).toContainText(/Faible|Partielle/)

  const funnel = page.locator('#funnel')
  await expect(funnel).toContainText('Domiciliation des flux')
  await expect(funnel.getByText(/Domiciliation des flux/)).toBeVisible()
  await visibility.scrollIntoViewIfNeeded()
  await page.screenshot({
    path: evidence('DASHBOARD-AGENCE-VISIBILITE-1440x900.png'),
    fullPage: false,
  })
})

test('Youssef versionne un seuil de visibilité avec une justification auditée', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page, 'admin')
  await page.goto('/back-office/seuils')

  await expect(page.getByRole('heading', { name: 'Configuration déterministe' })).toBeVisible()
  const flowRule = page.locator('[id^="rule-"]')
    .filter({ hasText: 'Domiciliation des flux' })
    .filter({ hasText: 'Inactif' })
    .last()
  await expect(flowRule).toContainText('Inactif')
  await flowRule.getByRole('button', { name: 'Modifier' }).click()

  const editor = page.getByRole('dialog')
  await expect(editor).toContainText(/Modifier (Domiciliation des flux|Flow Domiciliation)/)
  const submitVersion = editor.getByRole('button', { name: 'Créer une nouvelle version' })
  await submitVersion.scrollIntoViewIfNeeded()
  await expect(submitVersion).toBeVisible()
  const highThreshold = editor.locator('label.field').filter({ hasText: 'highShare' })
  await highThreshold.locator('input').fill('0.71')
  await editor.getByLabel('Justification').fill(
    'Test E2E de versionnement gouverné ; hypothèse à valider avec BOA.',
  )
  await submitVersion.click()

  await expect(page.getByText('Nouvelle version créée')).toBeVisible()
  const newVersion = page.locator('[id^="rule-"]')
    .filter({ hasText: 'Domiciliation des flux' })
    .filter({ hasText: /v1-v\d+/ })
    .filter({ hasText: 'Inactif' })
    .first()
  await expect(newVersion).toContainText('Inactif')
})
