# BOA SME Opportunity Intelligence

MVP d’intelligence commerciale pour portefeuilles PME, composé de microservices FastAPI, PostgreSQL, Keycloak, React et Docker Compose.

Le produit combine des **règles métier versionnées** et un **score de propension commerciale ML CPU-ready** observé en mode **`POC_SHADOW`**. La priorité opérationnelle reste exclusivement `RULES_ONLY` tant que les labels historiques BOA matures et les validations indépendantes ne sont pas disponibles. Il ne prend aucune décision de crédit. Le LLM reste une extension architecturale future et n’est ni appelé ni requis par le runtime.

> État : POC technique gouverné validé en mode `POC_SHADOW` sur données locales/synthétiques. Le score est persisté avec sa lignée mais ne modifie ni l’éligibilité ni la priorité des opportunités. Les manifests point-in-time, évaluations descriptives et blockers d’activation sont persistés ; `trainingReady=false`, la calibration reste `NOT_VALIDATED` et la production reste `BLOCKED`. Cette validation ne vaut ni performance ML de production ni autorisation de déploiement bancaire.

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
./scripts/validate-load-50k.sh
./scripts/validate-ingestion-governance.sh
./scripts/validate-ml-migration-rollback.sh
./scripts/validate-backup-restore.sh
./scripts/validate-operational-readiness.sh
./scripts/validate-security-scans.sh
./scripts/validate-product-catalog-migration.sh
./scripts/validate-product-catalog.sh
```

La validation ML vérifie les services Docker, la lignée Rule Studio/Signals/Feature Store/ML, l’absence d’influence du score shadow sur Opportunity/Portfolio, la Scoring Policy active `RULES_ONLY`, les labels candidats, le manifest point-in-time bloqué, l’évaluation descriptive sans claim de production, l’absence de dépendance LLM/GPU et le moindre privilège SQL. Les autres commandes produisent des preuves reproductibles de charge isolée, d’ingestion, de migration/rollback, de sauvegarde/restauration, de readiness dégradée et de scans de sécurité. Les deux validations catalogue prouvent séparément les migrations PostgreSQL vierge/existante/downgrade/ré-upgrade et la chaîne Analytics → Signals → Opportunity → produits précis. Les preuves sont versionnées sous `docs/evidence/`.

La préparation pilote locale est **PASS** sur les périmètres documentés. La release reste **`BLOCKED_IMAGE_CVES`** à cause des images externes, et aucun déploiement AWS n’est prévu.

## Documentation

Consultez [`docs/final-status.md`](docs/final-status.md), [`docs/lots/LOT-12-CATALOGUE-PRODUITS-BOA.md`](docs/lots/LOT-12-CATALOGUE-PRODUITS-BOA.md), [`docs/lots/LOT-13-CLOTURE-PILOTE.md`](docs/lots/LOT-13-CLOTURE-PILOTE.md), [`architecture/architecture.md`](architecture/architecture.md), [`docs/api.md`](docs/api.md), [`docs/demo-scenario.md`](docs/demo-scenario.md), [`docs/ml-engine.md`](docs/ml-engine.md), [`docs/industrialization-governance.md`](docs/industrialization-governance.md), [`docs/portfolio-scoping.md`](docs/portfolio-scoping.md) et [`docs/test-plan.md`](docs/test-plan.md).

Toutes les données et identités de démonstration sont synthétiques.

### Référentiel indicatif de produits BANK OF AFRICA

Le référentiel indicatif (28 pages produit publiques relevées sur bankofafrica.ma, regroupées en 7 familles) est décrit dans [`docs/catalogue-produits.md`](docs/catalogue-produits.md) et qualifié par le [rapport du lot 12](docs/lots/LOT-12-CATALOGUE-PRODUITS-BOA.md). Les ciblages et critères restent à valider avec BOA ; ce référentiel n'est pas contractuel. Rule Studio refuse les nouveaux codes inconnus et Opportunity échoue explicitement sur une règle publiée obsolète ou un produit devenu indisponible, au lieu de masquer sa recommandation. Product Service réapplique le scope client côté backend et reste non ready tant que le seed gouverné n'a pas matérialisé exactement le catalogue attendu. Rechargement des seules données synthétiques : `python database/seed/generate.py --database-url "$DATABASE_URL" --products-only`.
