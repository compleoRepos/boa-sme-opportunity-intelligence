import { expect, test } from '@playwright/test'
import { login } from './auth'

const mailpit = 'http://127.0.0.1:8025/api/v1'

test('notification : une action planifiée par le CC produit un email SMTP audité', async ({ page }) => {
  await page.request.delete(`${mailpit}/messages`)
  await login(page, 'cc')
  await expect(page.locator('.priority-row').filter({ hasNotText: 'Suivi standard' }).first()).toBeVisible()
  await page
    .locator('.priority-row')
    .filter({ hasNotText: 'Suivi standard' })
    .first()
    .locator('.priority-main')
    .click()
  await page.getByRole('button', { name: /Voir l’opportunité/ }).first().click()
  const drawer = page.getByRole('dialog')
  await drawer.locator('.choice', { hasText: /^À contacter/ }).click()
  await page.locator('#choice-form textarea').fill('Rappel SMTP du parcours E2E')
  await page.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.locator('.toast.success')).toContainText('Action enregistrée')

  await expect
    .poll(
      async () => {
        const response = await page.request.get(`${mailpit}/messages`)
        if (!response.ok()) return []
        return (await response.json()).messages as Array<Record<string, unknown>>
      },
      { timeout: 20_000 },
    )
    .toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          Subject: "BOA SME — rappel d'action commerciale",
        }),
      ]),
    )
})


test('administrateur : configure et génère la synthèse quotidienne d’un CC', async ({ page }) => {
  await login(page, 'admin')
  await expect(page.getByRole('heading', { name: /Back office|Gouvernance/ })).toBeVisible()
  await page.getByRole('link', { name: /Notifications/ }).click()
  await expect(page.getByRole('heading', { name: 'Notifications email' })).toBeVisible()

  const existing = page.locator('#digest-subscriptions tbody tr', { hasText: 'rm-01' })
  if (await existing.count()) {
    await existing.getByRole('button', { name: 'Modifier' }).click()
  } else {
    await page.getByRole('button', { name: 'Ajouter un CC' }).click()
    await page.getByLabel('Identifiant CC').fill('rm-01')
  }
  await page.getByLabel('Adresse email').fill('rm.demo@synthetic.invalid')
  await page.getByLabel('Fuseau IANA').fill('Africa/Abidjan')
  await page.getByLabel('Heure locale').fill('0')
  await page.getByLabel('Envoi quotidien actif').check()
  await page.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.locator('.toast.success')).toContainText('Abonnement enregistré')

  const generationResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/notifications/digests/generate') &&
      response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Générer maintenant' }).click()
  const generation = await generationResponse
  expect(generation.ok()).toBeTruthy()
  expect((await generation.json()).failed).toBe(0)
  await expect(page.locator('.toast.success', { hasText: 'Synthèses traitées' })).toBeVisible()
  await expect(page.locator('#notification-deliveries')).toContainText('Synthèse quotidienne')
  await expect(page.locator('#notification-deliveries')).toContainText('Sent')
})
