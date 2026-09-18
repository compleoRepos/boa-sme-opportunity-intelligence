import { expect, test, type Page } from '@playwright/test'

const username = process.env.E2E_USERNAME || 'rm.demo'
const password = process.env.E2E_PASSWORD || 'DevOnly-Rm1-ChangeMe!'
const targetOpportunityId = process.env.E2E_OPPORTUNITY_ID

async function login(page: Page) {
  await page.goto('/login')
  const loginButton = page.getByRole('button', { name: /Se connecter avec Keycloak/i })
  await expect(loginButton).toBeVisible()
  await loginButton.click()
  await page.waitForURL((url) => url.origin === 'http://localhost:8081', { timeout: 15_000 })
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: /Sign In|Connexion|Se connecter/i }).click()
  await expect(page).toHaveURL(/\/$/, { timeout: 30_000 })
  await expect(page.getByRole('heading', { name: /priorités commerciales/i })).toBeVisible()
}

test('parcours RM réel : opportunité → preuves → acceptation → contact → conversion', async ({ page }) => {
  await login(page)
  if (targetOpportunityId) await page.goto(`/opportunites/${targetOpportunityId}`)
  else {
    const first = page.getByTestId('opportunity-card').first()
    await expect(first).toBeVisible()
    await first.getByRole('link', { name: /Examiner/i }).click()
  }

  await expect(page.getByTestId('evidence-section')).toBeVisible()
  await expect(page.getByText(/WHY · POURQUOI/i)).toBeVisible()
  await expect(page.getByText(/CONFIDENCE · CONFIANCE/i)).toBeVisible()
  await expect(page.getByText(/EVIDENCE · PREUVES/i)).toBeVisible()

  await page.getByRole('button', { name: /Accepter/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByLabel(/Note/i).fill('Acceptation E2E du dossier')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.getByText(/Opportunité acceptée/i).last()).toBeVisible()

  await page.getByRole('button', { name: /Contacter/i }).click()
  await page.getByLabel(/Note/i).fill('Client joint dans le cadre du parcours E2E')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByText(/Contact client/i).last()).toBeVisible()

  await page.getByRole('link', { name: /Actions/i }).click()
  const contactRow = page.locator('.action-item').filter({ hasText: 'Client joint dans le cadre du parcours E2E' }).first()
  await expect(contactRow).toBeVisible()
  await contactRow.getByLabel(/Résultat de/i).selectOption('CONTACTED')
  await expect(contactRow.locator('.badge.success', { hasText: 'Contacté' })).toBeVisible()

  await page.goBack()
  await page.getByRole('button', { name: /Créer un suivi/i }).click()
  await page.getByLabel(/Type d’action/i).selectOption('MARK_CONVERTED')
  await page.getByLabel(/Note/i).fill('Conversion E2E confirmée')
  await page.getByRole('button', { name: /Enregistrer via API/i }).click()
  await expect(page.getByText(/Conversion enregistrée/i).last()).toBeVisible()
})

test('navigation et pagination restent utilisables sur mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  await page.getByRole('button', { name: /Ouvrir le menu/i }).click()
  await page.getByRole('link', { name: 'Opportunités', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Opportunités ouvertes' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Appliquer les filtres/i })).toBeVisible()
})
