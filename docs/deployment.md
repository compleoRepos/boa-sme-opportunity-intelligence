# Déploiement — BOA SME Opportunity Intelligence

**Statut :** cible de déploiement local et trajectoire ; la disponibilité de production n’est pas certifiée.

## Stack et profil MVP

Le backend cible Python 3.12 avec FastAPI. La persistance utilise SQLAlchemy 2.x et Alembic sur PostgreSQL. Le frontend est React/TypeScript et l’identité est portée par Keycloak. Docker Compose orchestre le profil local avec Gateway, services métier, APIs bancaires simulées, PostgreSQL et les outils nécessaires.

Les services communiquent par HTTP interne. Chaque service persistant applique ses migrations Alembic avec un compte de migration contrôlé, puis démarre avec un compte SQL limité à son schéma. Les événements métier sont conservés dans des outboxes locales. Aucun broker n’est requis au démarrage du MVP ; un broker futur est une extension.

## Séquence de démarrage

1. Fournir un environnement local non versionné et vérifier les ports.
2. Démarrer PostgreSQL et Keycloak et attendre leur disponibilité.
3. Créer schémas et rôles SQL strictement nécessaires.
4. Appliquer les migrations Alembic une seule fois.
5. Démarrer les services et vérifier `/health`, `/ready`, `/metrics` et `/openapi.json`.
6. Démarrer frontend et Gateway ; le navigateur ne voit que le Gateway.
7. Charger les données synthétiques, vérifier zéro opportunité, puis exécuter Analytics → Signals → Opportunities.

## Exploitation et limites

Les URLs, secrets, audiences OIDC, timeouts et paramètres de seed sont configurés par variables d’environnement. Les imports, recalculs et publications outbox sont idempotents. Les migrations suivent une stratégie expand–migrate–contract.

`BOA_AUTH_DISABLED=true` est désormais refusé au démarrage dès que `APP_ENV` est absent, inconnu ou différent de `development`, `local` ou `test`. Le fichier `.env.example` contient uniquement des valeurs synthétiques `DevOnly` destinées à la validation locale. Il ne constitue jamais une configuration pilote ou production.

Le workflow GitHub Actions versionné exécute lint, typage, tests backend/frontend, audits de dépendances, scans d’images, build Compose, migration/seed, pipeline synthétique, 19 parcours E2E, rollback de migration, backup/restore isolé et panne PostgreSQL contrôlée. Une porte finale dépend de chacun de ces jobs. Les images backend, frontend, PostgreSQL 16.15, Keycloak 26.7.4 et Mailpit 1.31.2 sont pinées par digest et scannées sans `--ignore-unfixed`. Le protocole local est **PASS**, mais son gate release est **BLOCKED_IMAGE_CVES**; le job CI `release-image-gate` bloque donc `main` et toute pull request tant que les images ne sont pas `READY`.[8] Le workflow ne publie aucune image et ne déploie aucun environnement bancaire.

Le Compose local n’est pas une cible de haute disponibilité. Une sauvegarde/restauration logique PostgreSQL et une récupération de readiness après panne DB sont prouvées uniquement sur le sandbox synthétique.[6] [7] Avant une exploitation BOA, il reste nécessaire de définir l’orchestration cible, le coffre de secrets, TLS/mTLS, le chiffrement au repos, la rotation des clés, la rétention, le stockage indépendant des backups, la supervision centralisée, l’alerting, le SIEM, la haute disponibilité et les objectifs de reprise.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../architecture/data-flow.md "Flux de données"
[3]: https://docs.docker.com/compose/ "Docker Compose documentation"
[4]: https://alembic.sqlalchemy.org/en/latest/ "Alembic documentation"
[5]: https://fastapi.tiangolo.com/ "FastAPI documentation"
[6]: evidence/backup/RESULTATS-BACKUP-RESTORE.json "Preuve locale de backup et restauration PostgreSQL"
[7]: evidence/operations/RESULTATS-READINESS-OPERATIONNELLE.json "Preuve locale de readiness dégradée et récupération PostgreSQL"
[8]: evidence/security/RESULTATS-SCANS-SECURITE.json "Preuve locale consolidée des scans de sécurité et gate release"
