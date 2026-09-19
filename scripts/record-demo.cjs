/* Enregistrement vidéo de la démonstration BOA SME Opportunity Intelligence.
 * Navigation réelle (Vite + Gateway + 16 services), aucune donnée mockée.
 * Sortie : un fichier .webm par acte + marks.json (horodatages) pour le montage.
 * Prérequis : stack locale démarrée (scripts/local-stack.sh up), Vite sur 5173 avec VITE_AUTH_DISABLED=true.
 * Usage : node scripts/record-demo.cjs [acte1|acte4|acte5|acte6]   puis assemblage ffmpeg (voir docs/demo-scenario.md).
 */
const path = require('node:path')
const fs = require('node:fs')
const { chromium } = require(path.join(__dirname, '..', 'frontend', 'node_modules', 'playwright'))

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const OUT = process.env.DEMO_VIDEO_DIR || path.join(__dirname, '..', '.local-stack', 'video')
fs.mkdirSync(OUT, { recursive: true })
const SIZE = { width: 1440, height: 900 }
const marks = []
let t0 = Date.now()
const mark = (label) => marks.push({ label, t: (Date.now() - t0) / 1000 })
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const OVERLAY = `
(() => {
  const ensure = () => {
    if (document.getElementById('__demo-caption')) return
    const style = document.createElement('style')
    style.textContent = \`
      #__demo-caption { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); max-width: 1080px; padding: 14px 22px; border-radius: 10px;
        background: rgba(11, 31, 68, 0.92); color: #fff; font: 500 19px/1.45 Inter, "Segoe UI", system-ui, sans-serif; letter-spacing: .01em; z-index: 2147483000;
        box-shadow: 0 10px 30px rgba(0,0,0,.25); opacity: 0; transition: opacity .35s ease; pointer-events: none; text-align: center; }
      #__demo-caption.on { opacity: 1; }
      #__demo-chapter { display: block; color: #9fc0ff; font: 600 12px/1.2 Inter, "Segoe UI", system-ui, sans-serif; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 6px; }
      #__demo-chapter:empty { display: none; }
      #__demo-cursor { position: fixed; width: 22px; height: 22px; border-radius: 50%; background: rgba(11,31,68,.75); border: 2.5px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,.35);
        transform: translate(-50%, -50%) scale(1); z-index: 2147483001; pointer-events: none; transition: transform .12s ease; left: -100px; top: -100px; }
      #__demo-cursor.down { transform: translate(-50%, -50%) scale(.7); background: #1f5fd0; }
    \`
    document.head.appendChild(style)
    const cap = document.createElement('div'); cap.id = '__demo-caption'
    const chap = document.createElement('span'); chap.id = '__demo-chapter'
    const txt = document.createElement('span'); txt.id = '__demo-text'
    cap.append(chap, txt)
    const cur = document.createElement('div'); cur.id = '__demo-cursor'
    document.body.append(cap, cur)
    try {
      const saved = JSON.parse(sessionStorage.getItem('__demo') || '{}')
      if (saved.caption) { txt.textContent = saved.caption; cap.classList.add('on') }
      if (saved.chapter) { chap.textContent = saved.chapter }
      if (saved.cursor) { cur.style.left = saved.cursor.x + 'px'; cur.style.top = saved.cursor.y + 'px' }
    } catch {}
    document.addEventListener('mousemove', (e) => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; save({ cursor: { x: e.clientX, y: e.clientY } }) }, true)
    document.addEventListener('mousedown', () => cur.classList.add('down'), true)
    document.addEventListener('mouseup', () => cur.classList.remove('down'), true)
  }
  const save = (patch) => { try { const s = JSON.parse(sessionStorage.getItem('__demo') || '{}'); sessionStorage.setItem('__demo', JSON.stringify({ ...s, ...patch })) } catch {} }
  window.__demo = {
    caption(text) { ensure(); const cap = document.getElementById('__demo-caption'); const txt = document.getElementById('__demo-text'); if (!text) { cap.classList.remove('on'); save({ caption: '' }); return } cap.classList.remove('on'); setTimeout(() => { txt.textContent = text; cap.classList.add('on') }, 180); save({ caption: text }) },
    chapter(text) { ensure(); document.getElementById('__demo-chapter').textContent = text; save({ chapter: text }) },
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure); else ensure()
})()
`

async function say(page, text, hold = 2600) { await page.evaluate((t) => window.__demo.caption(t), text); mark(`caption: ${text}`); await pause(hold) }
async function chapter(page, text) { await page.evaluate((t) => window.__demo.chapter(t), text) }
async function box(locator) { await locator.first().waitFor({ state: 'visible', timeout: 30000 }); const b = await locator.first().boundingBox(); if (!b) throw new Error('no box'); return b }
async function move(page, locator, dwell = 350) {
  let b = await box(locator)
  if (b.y < 90 || b.y > SIZE.height - 80) { await locator.first().evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' })); await pause(900); b = await box(locator) }
  await page.mouse.move(b.x + Math.min(b.width / 2, 260), b.y + b.height / 2, { steps: 28 }); await pause(dwell)
}
async function click(page, locator, dwell = 700) { await move(page, locator, 250); await page.mouse.down(); await pause(90); await page.mouse.up(); await pause(dwell) }
async function type(page, locator, text) { await click(page, locator, 200); await page.keyboard.type(text, { delay: 28 }); await pause(400) }
async function scrollTo(page, selector, block = 'start') { await page.locator(selector).first().evaluate((el, b) => el.scrollIntoView({ behavior: 'smooth', block: b }), block); await pause(1100) }
async function hover(page, locator, dwell = 900) { await move(page, locator, dwell) }
async function switchPersona(page, name, description) {
  await click(page, page.locator('.profile-btn'), 900)
  await say(page, description, 1800)
  await click(page, page.locator('.profile-menu button[role=menuitem]', { hasText: name }), 1600)
  await page.locator('.topbar').waitFor()
  if (await page.locator('.profile-menu').count()) { await click(page, page.locator('.page-head h1'), 600) }
}

async function newContext(browser, name) {
  const context = await browser.newContext({ viewport: SIZE, locale: 'fr-FR', deviceScaleFactor: 1, recordVideo: { dir: OUT, size: SIZE } })
  await context.addInitScript(OVERLAY)
  const page = await context.newPage()
  page.__name = name
  return { context, page }
}
async function closeContext(context, page, name) {
  await pause(600)
  const video = page.video()
  await context.close()
  const file = await video.path()
  fs.renameSync(file, path.join(OUT, `${name}.webm`))
  mark(`end ${name}`)
}

async function login(page, name) {
  await page.goto(`${BASE}/login`)
  await page.locator('.persona').first().waitFor()
  await click(page, page.locator('.persona', { hasText: name }), 1500)
  await page.locator('.topbar').waitFor()
}

async function acte1_2_3(browser) {
  const { context, page } = await newContext(browser, 'acte1')
  t0 = Date.now(); mark('start acte1')
  await page.goto(`${BASE}/login`)
  await page.locator('.persona').first().waitFor()
  await chapter(page, 'Acte 1 · Le chargé de clientèle')
  await say(page, 'Ahmed Mansouri, chargé de clientèle PME à l’agence Casablanca Anfa, ouvre son cockpit.', 2200)
  await click(page, page.locator('.persona', { hasText: 'Ahmed' }), 1800)
  await page.locator('.kpi').nth(3).waitFor()
  await say(page, 'En cinq secondes : combien de PME il gère, combien présentent un signal, lesquelles regarder aujourd’hui, ses actions à traiter.', 1200)
  for (let i = 0; i < 4; i++) await hover(page, page.locator('.kpi').nth(i), 750)
  await pause(600)
  await scrollTo(page, '.priority-row', 'center')
  await say(page, 'Chaque ligne est une carte d’information : signaux chiffrés, propension, produit potentiel. Le pourquoi est visible avant le clic.', 1000)
  await hover(page, page.locator('.priority-row').nth(0), 1400)
  await hover(page, page.locator('.priority-row').nth(1), 1400)
  await hover(page, page.locator('.priority-row').nth(2), 1000)

  // Acte 2 : fiche PME
  await chapter(page, 'Acte 2 · La fiche PME')
  await say(page, 'Un clic ouvre la fiche PME : un cockpit unique, le contexte est conservé.', 800)
  await click(page, page.locator('.priority-row .priority-main').first(), 1800)
  await page.locator('#health').waitFor()
  await say(page, 'Santé de la relation : ce qui change dans l’activité de l’entreprise sur 90 jours, comparé à la période précédente.', 2400)
  await scrollTo(page, '#activity', 'center')
  await say(page, 'Les séries sont agrégées en SQL sur les transactions réelles. On change la période : 30 jours, 6 mois, 12 mois.', 600)
  await click(page, page.getByRole('button', { name: /^30 jours$/ }), 1500)
  await click(page, page.getByRole('button', { name: /^6 mois$/ }), 1500)
  await click(page, page.getByRole('button', { name: /^12 mois$/ }), 1800)
  await hover(page, page.locator('#activity .recharts-wrapper'), 600)
  const chart = await box(page.locator('#activity .recharts-wrapper'))
  for (let i = 0; i <= 8; i++) { await page.mouse.move(chart.x + 60 + (chart.width - 120) * (i / 8), chart.y + chart.height / 2, { steps: 6 }); await pause(220) }
  await scrollTo(page, '#why', 'start')
  await say(page, 'Pourquoi cette opportunité ? Signaux détectés → règle SME_INVESTMENT_001 → propension du modèle → opportunité. Rien n’est une boîte noire.', 3600)
  await hover(page, page.locator('#why'), 1200)

  // Acte 3 : opportunité, propension, action
  await chapter(page, 'Acte 3 · L’action commerciale')
  await click(page, page.locator('#why button', { hasText: 'Voir l’opportunité' }), 1600)
  const drawer = page.getByRole('dialog')
  await drawer.waitFor()
  await say(page, 'Le panneau d’opportunité : chaque signal avec sa valeur observée, son seuil et sa base de comparaison sur 12 mois. Une évidence datée.', 2600)
  const evidenceTab = drawer.getByRole('tab', { name: /Signaux & évidence/ })
  if (await evidenceTab.count()) await click(page, evidenceTab, 1400)
  const drawerBody = drawer.locator('.drawer-body, .drawer').first()
  await drawerBody.evaluate((el) => el.scrollBy({ top: 320, behavior: 'smooth' })).catch(() => {})
  await pause(1400)
  await drawerBody.evaluate((el) => el.scrollBy({ top: -320, behavior: 'smooth' })).catch(() => {})
  await pause(900)
  await say(page, 'Ahmed décide de la suite : À contacter, Contacté, Intéressé, Offre créée, Converti, Non intéressé, À revoir.', 1200)
  await scrollTo(page, '#choice-form, .choice', 'center').catch(() => {})
  await click(page, drawer.locator('.choice', { hasText: 'À contacter' }), 900)
  await type(page, page.locator('#choice-form textarea'), 'Appel prévu avec le DAF pour qualifier le projet d’investissement.')
  await click(page, page.getByRole('button', { name: 'Enregistrer' }), 400)
  await page.locator('.toast.success').waitFor()
  await say(page, 'Action enregistrée via l’API, horodatée et auditée. Le dashboard sera mis à jour.', 2200)
  await click(page, drawer.getByRole('tab', { name: /Historique/ }), 1800)
  await page.keyboard.press('Escape'); await pause(900)

  await scrollTo(page, '.sheet-actions', 'center').catch(() => {})
  await say(page, 'La propension est expliquée : facteurs, contribution de chacun, version du modèle, date de mise à jour.', 600)
  await click(page, page.locator('.sheet-actions .ring'), 1600)
  await page.getByRole('dialog').waitFor()
  await say(page, 'Le modèle assiste le classement des priorités. Il ne prend aucune décision de crédit.', 2800)
  await page.keyboard.press('Escape'); await pause(800)

  await say(page, 'Retour au portefeuille : le compteur « Actions à traiter » est passé de 0 à 1.', 400)
  await click(page, page.locator('.sidebar nav a', { hasText: 'Mon portefeuille' }), 1800)
  await page.locator('.kpi').nth(3).waitFor()
  await hover(page, page.locator('.kpi').nth(3), 2400)
  await say(page, '', 300)
  await closeContext(context, page, 'acte1')
}

async function acte4(browser) {
  const { context, page } = await newContext(browser, 'acte4')
  t0 = Date.now(); mark('start acte4')
  await login(page, 'Ahmed')
  await page.locator('.kpi').nth(3).waitFor()
  await chapter(page, 'Acte 4 · Le responsable d’agence')
  await switchPersona(page, 'Salma Berrada', 'Changeons de rôle : Salma Berrada, responsable de l’agence Casablanca Anfa.')
  await page.locator('#rms table tbody tr').first().waitFor()
  await say(page, 'Salma pilote son agence : opportunités par chargé de clientèle, par secteur, par produit potentiel, résultats commerciaux.', 1800)
  await hover(page, page.locator('.kpi').first(), 600)
  await scrollTo(page, '#by-type', 'center')
  await pause(1200)
  await scrollTo(page, '#funnel', 'center')
  await pause(1400)
  await scrollTo(page, '#rms', 'start')
  await say(page, 'Drill-down complet : agence → chargé de clientèle → portefeuille → PME → opportunité.', 800)
  await hover(page, page.locator('#rms table tbody tr').nth(0), 700)
  await click(page, page.locator('#rms table tbody tr').first(), 1800)
  await page.locator('.priority-row').first().waitFor()
  await say(page, 'Le portefeuille du chargé de clientèle, vu par sa responsable : mêmes priorités, mêmes signaux.', 1600)
  await hover(page, page.locator('.priority-row').nth(1), 800)
  await click(page, page.locator('.priority-row .priority-main').first(), 1800)
  await page.locator('#health').waitFor()
  await say(page, 'Même fiche, même chaîne d’évidence : le contexte « portefeuille de » est conservé dans le rail.', 2600)
  await hover(page, page.locator('.rail'), 1200)
  await say(page, '', 300)
  await closeContext(context, page, 'acte4')
}

async function acte5(browser) {
  const { context, page } = await newContext(browser, 'acte5')
  t0 = Date.now(); mark('start acte5')
  await login(page, 'Youssef')
  await page.locator('.topbar').waitFor()
  await pause(800)
  await chapter(page, 'Acte 5 · Gouvernance des règles')
  await say(page, 'Youssef Tazi, Digital Factory : back office métier, règles, simulations, modèles ML, audit.', 2400)
  await click(page, page.locator('.sidebar nav a', { hasText: 'Rule Studio' }), 1800)
  await page.locator('table tbody tr').first().waitFor()
  await say(page, 'Rule Studio : les règles d’opportunité se lisent SI / ET / ALORS, sans code. Chaque version est auditée ; le moteur n’exécute que les règles publiées.', 2200)
  await hover(page, page.locator('table tbody tr').first(), 1200)
  await click(page, page.getByRole('link', { name: /Nouvelle règle/ }), 1600)
  await page.getByLabel('Nom de la règle').waitFor()
  await say(page, 'Création d’une variante plus sélective de la règle d’investissement : encaissements +30 % ET paiements fournisseurs +20 % sur 90 jours.', 1200)
  await type(page, page.getByLabel('Nom de la règle'), 'PME — investissement, croissance soutenue (+30 %)')
  await type(page, page.getByLabel('Description'), 'Variante plus sélective : encaissements +30 % et paiements fournisseurs +20 % sur 90 jours.')
  await scrollTo(page, '[data-testid=rule-condition]', 'center')
  const value1 = page.getByLabel('Valeur condition 1')
  await click(page, value1, 200); await page.keyboard.press('Control+A'); await page.keyboard.type('30', { delay: 120 }); await pause(700)
  await click(page, page.getByRole('button', { name: /^Condition$/ }), 900)
  await page.getByLabel('Métrique condition 2').selectOption('SUPPLIER_PAYMENT_GROWTH'); await pause(700)
  const value2 = page.getByLabel('Valeur condition 2')
  await click(page, value2, 200); await page.keyboard.press('Control+A'); await page.keyboard.type('20', { delay: 120 }); await pause(700)
  await scrollTo(page, '.chip.product', 'center')
  await click(page, page.locator('.chip.product', { hasText: 'Crédit MLTD Direct' }), 1000)
  await say(page, 'Le bloc ALORS : type d’opportunité, horizon, produits recommandés du catalogue réel.', 1800)
  await click(page, page.getByRole('button', { name: /Enregistrer le brouillon/ }), 1800)
  await page.waitForURL(/\/back-office\/regles\/(?!nouvelle)[^/]+$/)
  const ruleUrl = page.url()
  fs.writeFileSync(path.join(OUT, 'rule-url.txt'), ruleUrl)
  await page.locator('#readable').waitFor()
  await say(page, 'La règle relue en langage métier : SI … ET … ALORS. Statut Brouillon, version 1.', 1400)
  await hover(page, page.locator('#readable'), 1800)
  await click(page, page.getByRole('button', { name: 'Valider' }), 1200)
  await say(page, 'Validation de la configuration par le service de gestion des règles.', 1800)
  mark('sim start')
  await click(page, page.getByRole('button', { name: 'Lancer la simulation' }), 400)
  await say(page, 'Simulation sur le portefeuille réel : 500 PME analysées. Les résultats viennent de l’API, jamais inventés.', 200)
  await page.locator('#simulation .kpi').first().waitFor({ timeout: 180000 })
  mark('sim end')
  await pause(1200)
  await scrollTo(page, '#simulation', 'start')
  await say(page, 'Correspondances, taux de couverture, impact par secteur et par agence : de quoi juger une règle avant de la publier.', 3200)
  await page.locator('#simulation').evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'end' })); await pause(1600)
  await scrollTo(page, '.page-head', 'start')
  await click(page, page.getByRole('button', { name: 'Soumettre à approbation' }).first(), 900)
  await type(page, page.locator('#lifecycle-form textarea'), 'Variante à tester sur les agences de Casablanca.')
  const submitBtn = page.getByRole('dialog').getByRole('button', { name: /^Soumettre$/ })
  if (await submitBtn.count()) await click(page, submitBtn, 800); else await page.locator('#lifecycle-form').evaluate((f) => f.requestSubmit())
  await page.locator('.toast.success', { hasText: /effectué/ }).last().waitFor()
  await say(page, 'Soumise pour approbation. L’auteur ne peut pas approuver sa propre règle : séparation des tâches imposée par le serveur.', 3000)
  const own = page.getByRole('button', { name: 'Approuver' })
  if (await own.count()) await hover(page, own, 1600)
  await say(page, '', 300)
  await closeContext(context, page, 'acte5')
  return ruleUrl
}

async function acte6_7(browser, ruleUrl) {
  const { context, page } = await newContext(browser, 'acte6')
  t0 = Date.now(); mark('start acte6')
  await login(page, 'Nadia')
  await page.locator('.topbar').waitFor()
  await chapter(page, 'Acte 6 · Approbation et publication')
  await say(page, 'Nadia Ouazzani, approbatrice indépendante, relit la version soumise.', 1600)
  await page.goto(ruleUrl)
  await page.locator('#readable').waitFor()
  await hover(page, page.locator('#readable'), 1400)
  await click(page, page.getByRole('button', { name: 'Approuver' }).first(), 900)
  await type(page, page.locator('#lifecycle-form textarea'), 'Revue indépendante : seuils cohérents avec la politique commerciale PME.')
  let btn = page.getByRole('dialog').getByRole('button', { name: /^Approuver$/ })
  if (await btn.count()) await click(page, btn, 800); else await page.locator('#lifecycle-form').evaluate((f) => f.requestSubmit())
  await page.locator('.toast.success', { hasText: /effectué/ }).last().waitFor()
  await say(page, 'Approuvée. Dernière étape : la publication, qui rend la règle exécutable au prochain recalcul.', 2200)
  await click(page, page.getByRole('button', { name: 'Publier' }).first(), 900)
  await type(page, page.locator('#lifecycle-form textarea'), 'Publication pour le prochain recalcul.')
  btn = page.getByRole('dialog').getByRole('button', { name: /^Publier$/ })
  if (await btn.count()) await click(page, btn, 800); else await page.locator('#lifecycle-form').evaluate((f) => f.requestSubmit())
  await page.locator('.toast.success', { hasText: /effectué/ }).last().waitFor()
  await hover(page, page.locator('.page-actions .badge').first(), 1200)
  await say(page, 'Règle active. Chaque transition est tracée : qui, quoi, quand, pourquoi.', 1400)
  await click(page, page.getByRole('tab', { name: /Versions & audit/ }), 1600)
  await scrollTo(page, '#audit', 'center')
  await say(page, 'Journal d’audit en base de données, en ajout seul : impossible de modifier ou d’effacer une entrée.', 3200)

  await chapter(page, 'Acte 7 · Gouvernance du modèle')
  await say(page, 'Le modèle de propension est gouverné comme une règle : registre, versions, seuil, coefficients.', 800)
  await click(page, page.locator('.sidebar nav a', { hasText: 'ML Governance' }), 1800)
  await page.locator('.model-list button').first().waitFor()
  await click(page, page.locator('.model-list button').first(), 1400)
  await page.locator('#model').waitFor()
  await say(page, 'Model Registry : version active, seuil de décision, coefficients lisibles. Le modèle complète les règles ; il ne décide pas du crédit.', 1600)
  await scrollTo(page, '.coef-list', 'center')
  await hover(page, page.locator('.coef-list li').first(), 1000)
  await hover(page, page.locator('.coef-list li').nth(2), 1000)
  await scrollTo(page, '#model-lifecycle', 'center')
  await pause(1500)
  await say(page, 'Application réelle, données synthétiques, aucune API inventée. Prête pour un pilote en agence.', 3200)
  await say(page, '', 300)
  await closeContext(context, page, 'acte6')
}

;(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {}) })
  try {
    const only = process.argv[2]
    let ruleUrl = fs.existsSync(path.join(OUT, 'rule-url.txt')) ? fs.readFileSync(path.join(OUT, 'rule-url.txt'), 'utf8') : ''
    if (!only || only === 'acte1') await acte1_2_3(browser)
    if (!only || only === 'acte4') await acte4(browser)
    if (!only || only === 'acte5') ruleUrl = await acte5(browser)
    if (!only || only === 'acte6') await acte6_7(browser, ruleUrl)
  } finally {
    await browser.close()
    fs.writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify(marks, null, 2))
  }
})().catch((error) => { console.error(error); process.exit(1) })
