# BOA SME Opportunity Intelligence

MVP d’intelligence commerciale pour portefeuilles PME, composé de microservices FastAPI, PostgreSQL, Keycloak, React et Docker Compose.

Le produit combine des **règles métier versionnées** et un **score de propension commerciale ML CPU-ready** en mode **POC assistif**. Il ne prend aucune décision de crédit. Le LLM reste une extension architecturale future et n’est ni appelé ni requis par le runtime.

> État : POC technique gouverné et résilient validé en mode `POC_ASSISTIVE` sur 500 PME synthétiques. Le fallback `RULES_ONLY`, la Scoring Policy, le registre MLOps, le monitoring, la readiness prudente et l’UX premium sont intégrés. Cette validation ne vaut ni performance ML de production ni autorisation de déploiement bancaire. Voir le [rapport final PASS/BLOCKED/NON IMPLÉMENTÉ](docs/finalization-status-2026-09-19.md).

## Démarrage Docker

```bash
cp infrastructure/.env.example infrastructure/.env
./scripts/migrate.sh
./scripts/seed.sh
sudo docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml up -d --build --wait
```

L’interface est ensuite disponible sur `http://localhost:3000`, l’API Gateway sur `http://localhost:8080` et Keycloak sur `http://localhost:8081`.

Les règles Rule Studio de démonstration (`database/seed/rule-studio.json`) se créent via `POST /api/v1/rules` avec un compte analyste métier ; en stack locale, `scripts/local-stack.sh rules` s’en charge.

## Stack locale sans Docker

`scripts/local-stack.sh up` démarre un PostgreSQL natif, applique les migrations, charge le seed, lance les services uvicorn avec `BOA_AUTH_DISABLED=true`, exécute le pipeline complet puis crée les règles Rule Studio. Le frontend se lance avec `VITE_AUTH_DISABLED=true` et les personas de démonstration. `scripts/local-stack.sh down` arrête l’ensemble. Ce mode est réservé à la démonstration et au développement : aucun Keycloak et uniquement des données synthétiques.

## Validation

```bash
./scripts/validate.sh
./scripts/validate-ml-integration.sh
```

La seconde commande vérifie les services Docker, la lignée Rule Studio/Signals/Feature Store/ML/Opportunity, les versions de modèle et de features, les futurs labels, l’absence de dépendance LLM/GPU et le moindre privilège SQL du chemin d’inférence. La suite complète couvre aussi le fallback et sa récupération, la Scoring Policy versionnée, le workflow MLOps, le monitoring persistant, le RBAC et huit parcours Playwright authentifiés.

## Documentation

Consultez `architecture/architecture.md`, `docs/api.md`, `docs/ux-architecture.md`, `docs/demo-scenario.md`, `docs/ml-engine.md`, `docs/finalization-status-2026-09-19.md`, `docs/industrialization-governance.md`, `docs/portfolio-scoping.md` et `docs/test-plan.md`.

Toutes les données et identités de démonstration sont synthétiques.
