# BOA SME Opportunity Intelligence

MVP d’intelligence commerciale pour portefeuilles PME, composé de microservices FastAPI, PostgreSQL, Keycloak, React et Docker Compose.

Le produit combine des **règles métier versionnées** et un **score de propension commerciale ML CPU-ready** en mode **POC assistif**. Il ne prend aucune décision de crédit. Le LLM reste une extension architecturale future et n’est ni appelé ni requis par le runtime.

> État : intégration technique validée en mode `POC_ASSISTIVE` sur 500 PME synthétiques. Cette validation ne vaut ni performance ML de production ni autorisation de déploiement bancaire. Voir [`docs/ml-integration-status.md`](docs/ml-integration-status.md) pour la matrice PASS / NON IMPLÉMENTÉ.

## Démarrage local

```bash
cp infrastructure/.env.example infrastructure/.env
./scripts/migrate.sh
./scripts/seed.sh
sudo docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml up -d --build --wait
```

L’interface est ensuite disponible sur `http://localhost:3000`, l’API Gateway sur `http://localhost:8080` et Keycloak sur `http://localhost:8081`.

## Documentation

Consultez `architecture/architecture.md`, `docs/api.md`, `docs/ml-engine.md`, `docs/ml-integration-status.md`, `docs/portfolio-scoping.md` et `docs/test-plan.md`.

La validation reproductible des invariants ML s’exécute avec :

```bash
./scripts/validate-ml-integration.sh
```

Toutes les données et identités de démonstration sont synthétiques.
