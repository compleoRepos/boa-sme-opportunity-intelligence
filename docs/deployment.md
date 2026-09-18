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

Le Compose local n’est pas une cible de haute disponibilité. Avant une exploitation BOA, il faudra définir orchestration, sauvegarde/restauration, gestion des secrets, chiffrement, rotation des clés, supervision et objectifs de reprise.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../architecture/data-flow.md "Flux de données"
[3]: https://docs.docker.com/compose/ "Docker Compose documentation"
[4]: https://alembic.sqlalchemy.org/en/latest/ "Alembic documentation"
[5]: https://fastapi.tiangolo.com/ "FastAPI documentation"
