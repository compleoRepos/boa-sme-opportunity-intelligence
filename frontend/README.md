# Frontend — BOA SME Opportunity Intelligence

Application React 19 + TypeScript + Vite destinée aux chargés d’affaires PME. L’interface appelle **exclusivement le Gateway `/api/v1`** : aucune donnée métier, opportunité, règle, KPI ou série graphique n’est codée en dur dans les composants.

## Configuration

Copier `.env.example` vers `.env` et adapter les URLs de l’environnement. `VITE_API_BASE_URL` peut rester vide lorsque Vite proxyfie `/api` vers `VITE_GATEWAY_PROXY_TARGET`. L’authentification utilise Keycloak en Authorization Code + PKCE ; le client navigateur doit être public, sans secret.

`VITE_AUTH_DISABLED=true` est réservé au développement local quand Keycloak n’est pas disponible. Ce mode est explicitement opt-in et ne fournit aucune donnée métier : toutes les pages continuent d’appeler le Gateway réel.

## Commandes

```bash
npm install
npm run typecheck
npm test
npm run build
npm run dev
```

## E2E avec stack réelle

Les tests Playwright ne mockent aucune API. Ils nécessitent le frontend, le Gateway, Keycloak et les services réels :

```bash
E2E_BASE_URL=http://localhost:5173 \
E2E_USERNAME=rm.demo \
E2E_PASSWORD='<mot-de-passe-de-test>' \
npm run test:e2e
```

`E2E_OPPORTUNITY_ID` permet de sélectionner une opportunité déterministe du dataset ; sinon le test ouvre la première recommandation renvoyée par le Gateway. Les identifiants ne sont pas stockés dans le dépôt.

## Écrans

Le frontend fournit la connexion/déconnexion OIDC, le dashboard et ses KPI, les opportunités filtrées et paginées, le détail WHY/WHAT/WHEN/CONFIDENCE/EVIDENCE, Customer 360, les signaux, les actions/outcomes, le catalogue et l’administration des règles protégée par le rôle `ADMIN`.

Les états de chargement, liste vide, erreur normalisée avec `correlationId`, session expirée et accès interdit sont traités explicitement. Le libellé `FINANCIAL_STRESS_SIGNAL` reste toujours « signal de tension financière » et n’est jamais présenté comme une décision de crédit.
