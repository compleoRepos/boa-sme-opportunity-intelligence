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

Les règles Rule Studio de démonstration (`database/seed/rule-studio.json`) se créent via `POST /api/v1/rules` avec un compte analyste métier ; en stack locale, `scripts/local-stack.sh rules` s’en charge.

## Stack locale sans Docker

`scripts/local-stack.sh up` démarre un PostgreSQL natif (`/usr/lib/postgresql/16`), applique les migrations, charge le seed, lance les seize services uvicorn (Gateway sur `8080`) avec `BOA_AUTH_DISABLED=true`, exécute le pipeline complet (analytics → signaux → opportunités → features → scoring ML) puis crée les règles Rule Studio. Le frontend se lance ensuite avec `VITE_AUTH_DISABLED=true` (personas de démonstration). `scripts/local-stack.sh down` arrête tout. Ce mode est réservé à la démonstration et au développement : aucun Keycloak, données synthétiques.

## Documentation

Consultez `architecture/architecture.md`, `docs/api.md`, `docs/ux-architecture.md`, `docs/demo-scenario.md`, `docs/ml-engine.md`, `docs/portfolio-scoping.md` et `docs/test-plan.md`.

Toutes les données et identités de démonstration sont synthétiques.

### Catalogue produit BANK OF AFRICA

Le catalogue commercial (28 produits entreprises relevés sur bankofafrica.ma, regroupés en 7 familles) est décrit dans [`docs/catalogue-produits.md`](docs/catalogue-produits.md). Rechargement seul : `python database/seed/generate.py --database-url "$DATABASE_URL" --products-only`.
