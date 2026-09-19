# Frontend — BOA SME Opportunity Intelligence

Application React 19 + TypeScript + Vite pour les chargés de clientèle PME, les responsables d’agence et le back office métier. L’interface appelle **exclusivement le Gateway `/api/v1`** : aucune donnée métier, opportunité, règle, KPI ou série graphique n’est codée en dur.

L’architecture UX (cockpit unique, écrans prioritaires, design system, micro-interactions, états) est décrite dans `../docs/ux-architecture.md` ; le parcours de démonstration dans `../docs/demo-scenario.md`.

## Structure

```
src/
  api/        client HTTP typé, hooks TanStack Query, types des contrats, formats fr-FR
  auth/       OIDC Keycloak (PKCE) + personas de démonstration (mode sans Keycloak)
  ui/         design system : Button, Badge, Panel, Kpi, Ring, Delta, Tabs, Drawer, Modal, Toast, Tooltip, States, Stepper
  charts/     Recharts (palette validée), répartitions, facteurs ML, sparklines, entonnoir
  layout/     AppShell (sidebar, topbar, fil d’Ariane) et cockpit (rail + scène)
  features/   dashboard (CC), customer (fiche PME, drawers, actions), branch (agence), rules (Rule Studio), backoffice, demo
  pages/      listes (clients, opportunités, actions, signaux, produits), connexion, états
  styles/     tokens, base, composants, layout, écrans
```

## Configuration

Copier `.env.example` vers `.env` (ou `.env.local`). `VITE_API_BASE_URL` peut rester vide lorsque Vite proxyfie `/api` vers `VITE_GATEWAY_PROXY_TARGET`. L’authentification utilise Keycloak en Authorization Code + PKCE.

`VITE_AUTH_DISABLED=true` active le **mode démonstration sans Keycloak** : l’écran de connexion propose des personas (CC, responsable d’agence, approbatrice, back office) envoyées au Gateway via le header `X-Dev-Principal`. Le backend doit tourner avec `BOA_AUTH_DISABLED=true` ; ce header est ignoré dès que l’OIDC est actif. Toutes les pages continuent d’appeler le Gateway réel.

## Commandes

```bash
npm install
npm run typecheck
npm test            # vitest (composants, parseur de signaux, actions commerciales, Rule Studio)
npm run build
npm run dev         # http://127.0.0.1:5173
```

## E2E avec stack réelle

Les tests Playwright (`../tests/e2e`) ne mockent aucune API. Deux modes :

```bash
# Mode Keycloak (stack Docker)
E2E_BASE_URL=http://localhost:5173 E2E_USERNAME=rm.demo E2E_PASSWORD='<mot-de-passe>' npm run test:e2e

# Mode personas (stack locale sans Docker : scripts/local-stack.sh up && scripts/local-stack.sh rules)
E2E_DEV_MODE=true E2E_BASE_URL=http://127.0.0.1:5173 npm run test:e2e
```

`E2E_CHROMIUM_PATH` permet d’utiliser un Chromium déjà installé. Les identifiants ne sont pas stockés dans le dépôt.

## Écrans

Dashboard CC (« Mon portefeuille PME »), fiche PME en cockpit avec drawers opportunité et propension, chaîne « Pourquoi cette opportunité ? », action commerciale (chaque choix crée une action auditée via l’API), dashboard agence avec drill-down, back office (Rule Studio visuel SI/ET/ALORS, simulation, approbation, publication, Model Registry, simulations, audit, seuils moteur, catalogue), démo guidée de cinq minutes.

Les états de chargement (skeletons), liste vide, erreur normalisée avec `correlationId`, session expirée et accès interdit sont traités explicitement. Le libellé `FINANCIAL_STRESS_SIGNAL` reste toujours « signal de tension financière » et n’est jamais présenté comme une décision de crédit.
