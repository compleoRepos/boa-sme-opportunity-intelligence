# BOA SME Opportunity Intelligence

MVP d’intelligence commerciale pour portefeuilles PME, composé de microservices FastAPI, PostgreSQL, Keycloak, React et Docker Compose.

Le produit combine des **règles métier versionnées** et un **score de propension commerciale ML CPU-ready** en mode **POC assistif**. Il ne prend aucune décision de crédit. Le LLM reste une extension architecturale future et n’est ni appelé ni requis par le runtime.

> État du commit initial public : intégration ML, Feature Store et dashboards CC/agence en cours de validation complète. Les résultats d’acceptation définitifs seront publiés dans `docs/ml-integration-status.md` après exécution des tests PostgreSQL, RBAC, Docker et Playwright.

## Démarrage local

```bash
cp infrastructure/.env.example infrastructure/.env
./scripts/migrate.sh
./scripts/seed.sh
sudo docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml up -d --build --wait
```

L’interface est ensuite disponible sur `http://localhost:3000`, l’API Gateway sur `http://localhost:8080` et Keycloak sur `http://localhost:8081`.

## Documentation

Consultez `architecture/architecture.md`, `docs/api.md`, `docs/ml-engine.md`, `docs/portfolio-scoping.md` et `docs/test-plan.md`.

Toutes les données et identités de démonstration sont synthétiques.
