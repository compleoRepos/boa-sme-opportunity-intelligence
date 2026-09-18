# Infrastructure locale

Cette infrastructure lance **PostgreSQL 16, Keycloak 25, Nginx et onze processus FastAPI séparés** : API Gateway, Customer, Account, Transaction, Banking Integration, Mock Bank, Analytics, Signal, Opportunity, Product et Action. Une image Python commune réduit le temps de build, mais chaque service possède un conteneur, un module FastAPI, une identité OAuth et un schéma PostgreSQL dédiés.

## Démarrage

```bash
cp infrastructure/.env.example infrastructure/.env
cd infrastructure
docker compose up --build
```

Le frontend est publié sur `http://localhost:3000`, le Gateway sur `http://localhost:8080` et Keycloak sur `http://localhost:8081`. Les réseaux `app` et `data` sont internes; PostgreSQL et les APIs métier ne publient aucun port hôte. Keycloak est lié à `127.0.0.1` car le navigateur doit effectuer le flux OIDC en développement.

Le Dockerfile frontend affiche une page d’état explicite tant que le code React n’existe pas. Il ne fournit ni donnée métier ni faux dashboard. Le Dockerfile backend attend le module configuré par `APP_MODULE` (actuellement `boa_oi.api:app` pour le socle commun); l’infrastructure ne crée volontairement aucun code métier.

## Identifiants synthétiques de développement

> **Ces identifiants sont uniquement destinés au développement local. Ils ne sont pas des secrets de production.** Toutes les valeurs sont surchargeables dans `infrastructure/.env`. Lors du premier démarrage sur un volume Keycloak vide, l’entrypoint rend le realm avec ces valeurs. Pour réimporter après changement, supprimez explicitement le volume local ou modifiez le realm via l’administration Keycloak.

| Utilisateur | Rôle | Mot de passe par défaut |
|---|---|---|
| `rm.demo` | `RELATIONSHIP_MANAGER` | `DevOnly-Rm1-ChangeMe!` |
| `branch.demo` | `BRANCH_MANAGER` | `DevOnly-Branch1-ChangeMe!` |
| `admin.demo` | `ADMIN` | `DevOnly-Admin1-ChangeMe!` |
| `analyst.demo` | `DATA_ANALYST` | `DevOnly-Analyst1-ChangeMe!` |

Le realm fournit le client public `boa-sme-spa` en Authorization Code + PKCE, l’audience `boa-sme-api`, un client confidentiel pour chaque service et `pipeline-runner` pour les scripts. Les secrets de développement de ces clients sont listés et surchargeables dans `.env.example`.

## Commandes opératoires

Depuis la racine du dépôt :

```bash
./scripts/validate.sh
./scripts/migrate.sh
./scripts/seed.sh
./scripts/run-pipeline.sh
```

`migrate.sh` exécute une seule fois la migration Alembic versionnée actuellement fournie, qui crée les schémas de contexte. `seed.sh` lance le job `tools.demo_data_generator`. `run-pipeline.sh` obtient un token `client_credentials`, lance les imports puis Analytics → Signal → Opportunity. Ces scripts échouent franchement si le code applicatif attendu n’est pas encore présent; ils ne simulent pas un succès.

Pour changer les mots de passe après initialisation de PostgreSQL/Keycloak, une simple modification du `.env` ne modifie pas les rôles déjà persistés. Utilisez un volume neuf en développement ou une procédure de rotation administrée.

## Budget local

Les limites Compose plafonnent la stack à environ **6,5 Go** dans le pire cas, avec des réservations nettement plus basses, ce qui laisse de la marge sur une machine de 8 Go. Compose reste un environnement local de référence, sans haute disponibilité, TLS interservice ni gestionnaire de secrets. En production, injecter les secrets depuis le gestionnaire BOA, terminer TLS à l’edge et séparer les bases selon les standards d’exploitation.
