# Audit lecture seule — sécurité et opérations

**Périmètre :** dépôt `boa-sme-opportunity-intelligence` audité localement en lecture seule le 19 septembre 2026. Le présent document ne modifie aucun code applicatif, configuration d’exécution ou test. Les constats portent sur les fichiers effectivement présents et sur les commandes exécutées dans ce dépôt.

## Conclusion exécutive

Le dépôt fournit un **socle POC sérieux** : authentification OIDC/JWT avec validation de signature, issuer et audience ; rôles Keycloak explicites ; contrôles RBAC sur les routes ; comptes de service séparés ; réseaux Docker internes ; conteneurs non root ; permissions SQL par schéma ; endpoints `/health`, `/ready` et `/metrics` ; journaux JSON avec `X-Correlation-ID` ; CI avec lint, typage, tests, scans de secrets, audits de dépendances, Trivy et smoke Compose. Les tests E2E présents couvrent notamment des refus RBAC et des restaurations de modèles/politiques.

Le résultat **ne constitue toutefois pas une readiness de production bancaire**. Les principaux bloqueurs sont la présence de secrets de développement par défaut dans les templates, les secrets en clair dans le realm Keycloak versionné, le mode local qui désactive l’authentification, l’absence de sauvegarde/restauration opérable et testée, l’absence de test de charge, l’absence de stack Prometheus/Grafana/OTel réellement présente, et l’absence de rollback d’infrastructure. L’audit applicatif est traçable et certains objets sont hashés, mais l’immutabilité est une convention documentaire et applicative : aucune garantie append-only, chaîne de hash, signature, stockage WORM, rétention ou contrôle d’accès DBA n’est démontrée.

**Verdict : POC validable en développement ; déploiement de production bloqué** tant que les secrets, la sauvegarde/restauration, l’observabilité opérable, la performance et la gouvernance d’exploitation ne sont pas traités.

## 1. Méthode et niveau de preuve

L’audit a porté sur `infrastructure/`, `backend/src/`, `database/`, `scripts/`, `.github/workflows/`, `tests/` et la documentation associée. Les recherches ont été effectuées avec `find`, `rg`, `git ls-files` et la lecture des fichiers avec numéros de ligne. Les commandes de qualité suivantes ont également été exécutées :

| Commande exécutée | Résultat observé | Portée réelle |
|---|---|---|
| `ruff check backend/src tests/unit` | **PASS**, `All checks passed!` | Lint du backend et des tests unitaires |
| `mypy backend/src` | **PASS**, aucun problème sur 75 fichiers | Typage du code backend |
| `pytest -q --disable-warnings` depuis la racine | **ÉCHEC de collecte**, `ModuleNotFoundError: No module named 'database'` dans `tests/unit/test_models_seed_api.py` | La commande directe depuis la racine n’est pas reproductible sans préparer le chemin d’import |
| Workflow CI : `ruff check backend tests`, `mypy backend`, `pytest -m 'not integration and not e2e' --cov=backend` | Présent dans le YAML | Chemin CI différent de la commande locale ; son succès complet n’a pas été exécuté dans cet audit |
| Workflow CI : `npm run typecheck`, `npm test`, `npm run build` | Présent dans le YAML | Frontend |
| Workflow CI : Gitleaks, `pip-audit`, `npm audit --audit-level=high`, Trivy HIGH/CRITICAL | Présent dans le YAML | Scans de secrets, dépendances et images |

Cette différence doit être corrigée ou explicitée : un développeur qui lance `pytest` à la racine obtient un échec avant exécution des tests, alors que la CI installe le paquet backend puis utilise des marqueurs. Aucun résultat CI distant n’a été utilisé comme preuve de succès.

## 2. Authentification Keycloak et RBAC

### Ce qui fonctionne

Le backend refuse l’absence de bearer token lorsque `BOA_AUTH_DISABLED` n’est pas actif. La fonction `current_principal` renvoie une erreur `401 AUTHENTICATION_REQUIRED` si le credential est absent ou n’est pas de type Bearer [1]. Le décodage JWT récupère la clé de signature via le JWKS interne, vérifie l’audience, puis limite l’issuer aux URLs OIDC publique et interne configurées [1]. Les erreurs d’autorisation sont distinguées : un principal authentifié sans rôle autorisé reçoit `403 FORBIDDEN` [1].

Les rôles fonctionnels sont centralisés dans `READ_ROLES`, `COMMERCIAL_ROLES`, `ADMIN_ROLES` et `ANALYTICS_ROLES`. La lecture inclut `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `DATA_ANALYST`, `BUSINESS_ANALYST`, `RULE_APPROVER`, `ADMIN` et `SERVICE`, tandis que les écritures commerciales sont limitées aux rôles commerciaux et les routes d’administration à `ADMIN` et `SERVICE` [1]. Le realm déclare un client SPA public et des clients de service non publics, avec `standardFlowEnabled=false`, `directAccessGrantsEnabled=false`, `serviceAccountsEnabled=true` et `fullScopeAllowed=false` pour les comptes de service [2]. Cette configuration va dans le sens du moindre privilège, sous réserve d’une revue effective des rôles de chaque service.

Le code implémente également des scopes de portefeuille, agence et chargé de relation dans le principal, et les tests E2E vérifient au moins un accès interdit `403` ainsi que des opérations administratives où l’auto-approbation est refusée [3]. Les tests E2E de gouvernance vérifient aussi un rollback de modèle et une restauration de Scoring Policy [3].

### Risques et limites

Le mode de développement `BOA_AUTH_DISABLED=true` crée un principal local possédant simultanément `ADMIN`, `DATA_ANALYST`, `BRANCH_MANAGER`, `RELATIONSHIP_MANAGER` et `SERVICE`, avec scope global et branche `ALL` [1]. Le header `X-Dev-Principal` permet en outre de rejouer une persona locale. La documentation le limite au développement, mais aucune garde-fou de démarrage ne démontre qu’il est impossible de l’activer dans un environnement exposé. Une erreur de variable d’environnement transformerait le contrôle RBAC en accès global.

Le realm Keycloak embarque des utilisateurs de démonstration et les secrets sont injectés par remplacement de littéraux [2]. Les secrets sont donc connus dans le dépôt sous forme de valeurs `DevOnly-*`, même si le fichier `infrastructure/.env` local n’est pas suivi par Git. Cette pratique est acceptable uniquement pour un environnement synthétique isolé ; elle est dangereuse si le realm ou les valeurs par défaut sont réutilisés.

La matrice de périmètre est documentée, mais l’audit n’a pas trouvé de test systématique et automatisé couvrant chaque combinaison route × rôle × portefeuille/agence × objet deviné. Il manque notamment une preuve exhaustive des cas `401`, `403` et `404`, des tokens expirés, signature invalide, issuer incorrect, audience incorrecte, token malformé et session révoquée. Le plan de test les demande, mais un plan n’est pas une exécution [4].

**Risque principal : élevé.** Un mauvais paramétrage de `BOA_AUTH_DISABLED`, une attribution Keycloak trop large ou une route non protégée pourrait exposer des données clients. La séparation des rôles est prometteuse mais doit être prouvée par une matrice de tests générée et exécutée en CI.

## 3. Secrets, certificats et chaîne de livraison

### Preuves positives

Le fichier `.gitignore` exclut le fichier local `infrastructure/.env` dans l’usage attendu, tandis que `.env.example` indique explicitement que les valeurs sont synthétiques et doivent être remplacées hors développement [5]. La CI lance Gitleaks avec un historique Git complet, `pip-audit`, `npm audit` et Trivy sur les images backend et frontend, avec échec sur les vulnérabilités HIGH/CRITICAL corrigibles [6]. Les images backend et frontend tournent avec des utilisateurs non privilégiés ou des images nginx non root ; Compose ajoute `no-new-privileges`, `cap_drop: ALL` et des limites de ressources sur les services [7].

### Manques et risques

Le realm Keycloak versionné contient les secrets de clients de service sous forme de littéraux `DevOnly-...` [2]. Le Compose et les scripts ont aussi des valeurs par défaut de mot de passe, par exemple `DevOnly-Postgres-ChangeMe!`, lorsqu’une variable n’est pas fournie [7]. Le secret n’est donc pas seulement un paramètre local : il est présent dans le code de déploiement et réapparaît dans les commandes et l’environnement des conteneurs. Aucun gestionnaire de secrets, KMS, rotation, expiration, révocation, contrôle de force ou procédure de renouvellement n’est présent.

Le TLS n’est pas configuré dans le Compose fourni : les URLs OIDC et les appels locaux utilisent HTTP, et la configuration nginx autorise explicitement `http://localhost:8081` dans CSP [7]. Cela convient au poste de développement mais ne constitue pas une terminaison TLS ou une politique de certificats de production. Les scans présents ne remplacent ni la gestion de secrets ni la validation de configuration contre un environnement cible.

**Priorité : bloqueur de production.** Remplacer les littéraux par des références à un gestionnaire de secrets, interdire les valeurs de repli en dehors d’un profil explicitement local, faire tourner tous les secrets et comptes de démonstration, puis ajouter une vérification CI qui échoue si une valeur `DevOnly-*` est activée avec `APP_ENV` non local.

## 4. Audit applicatif et immutabilité

### Ce qui fonctionne

Les modèles conservent l’acteur, l’action, la ressource, le résultat, le `correlation_id`, l’horodatage et des métadonnées. `DecisionAudit` conserve les versions du moteur, de la règle, de la policy, les signaux, les snapshots, le mode de fallback et un `decision_hash` unique de 64 caractères [8]. Le service d’audit construit un hash canonique SHA-256 du payload, interdit certains vocabulaires de décision de crédit et enregistre la décision avec sa version et son contexte [9]. Les imports et actions ont également un `request_hash` ou `input_hash`, ce qui soutient l’idempotence et la reconstitution.

Les permissions SQL donnent à `opportunity_service` l’accès `SELECT, INSERT` sur `audit.audit_logs`, ce qui limite les opérations applicatives sur le journal central [10]. Les opérations de gouvernance documentent un rollback versionné qui ne réécrit pas l’historique métier [11].

### Ce qui n’est pas démontré

La documentation qualifie `audit.audit_logs` et `decision_audit` d’append-only, mais le modèle ne fournit pas de contrainte SQL équivalente, de trigger refusant `UPDATE`/`DELETE`, de chaîne de hash entre événements, de signature indépendante, de stockage WORM, de réplication vers un SIEM ou de preuve d’export hors de portée d’un DBA [8] [12]. La permission `SELECT, INSERT` accordée à un service est meilleure qu’un accès d’écriture général, mais un rôle propriétaire ou un compte administrateur PostgreSQL peut toujours modifier ou supprimer les données si aucune politique de base complémentaire n’est installée.

Le `decision_hash` est unique, mais l’audit n’établit pas à lui seul l’identité de l’auteur de la clé de hash, la conservation de la version de canonisation ou la détection d’une suppression d’une ligne. Il faut donc parler de **détectabilité partielle d’altération du payload**, et non d’audit immuable au sens fort.

**Risque : élevé pour une exigence réglementaire.** Mettre en place une table d’audit append-only protégée par trigger et rôle propriétaire séparé, une chaîne ou un manifeste de hash signé, une exportation vers stockage immuable/SIEM, une rétention documentée et un test de tentative d’UPDATE/DELETE par chaque compte de service.

## 5. Pseudonymisation et données sensibles

Les identifiants métier sont convertis en UUID déterministes par domaine (`customer`, `transaction`, `account`, etc.), et les appels utilisent ces identifiants stables dans les jointures et filtres [13]. Les données du seed et les identités de démonstration sont annoncées comme synthétiques dans le README [14]. Les notes d’action portent le nom `notes_redacted`, ce qui indique une intention de réduction de données, et la documentation précise que les tokens et secrets ne doivent pas figurer dans l’audit [12].

Cela **ne suffit pas à établir une pseudonymisation robuste**. Un UUID déterministe est un identifiant pseudonyme, pas une anonymisation : il reste corrélable, et sa protection dépend du secret ou de l’espace d’entrée. Le code retourne encore des `customerId`, noms de produits et autres données métier ; aucune stratégie générale de minimisation, classification, chiffrement au repos, chiffrement champ par champ, gestion de clé, durée de rétention, droit d’effacement ou test de ré-identification n’a été trouvée. Aucun service de DLP ou détecteur de données personnelles dans les logs n’est présent.

**Manque :** formaliser le registre des données, les finalités, la base légale et les propriétaires ; séparer identifiant technique et table de correspondance protégée ; ajouter des tests qui garantissent l’absence de PII dans logs, métriques, traces et audit ; définir chiffrement, rétention et purge contrôlée.

## 6. Health, métriques et observabilité

Chaque application FastAPI expose `/health`, `/ready` et `/metrics`. `/ready` vérifie `SELECT 1` lorsqu’une base est configurée ; `/metrics` expose actuellement un compteur de requêtes, un compteur d’erreurs et une information de version sous format Prometheus minimal [15]. Le middleware écrit des journaux JSON comprenant service, méthode, chemin, statut, durée et `correlationId`, et propage `X-Correlation-ID` dans les réponses et appels interservices [15]. Les healthchecks Docker et les smoke tests CI vérifient les ports frontend, gateway et la découverte OIDC Keycloak [6] [7].

La limite importante est l’écart entre l’architecture documentée et le runtime. La documentation décrit Prometheus, Grafana et un collecteur OpenTelemetry comme des composants attendus ou optionnels [16], mais le Compose réellement présent ne déclare pas de services Prometheus, Grafana ou `otel-collector` ; la variable `OTEL_EXPORTER_OTLP_ENDPOINT` est vide par défaut [7]. Aucun dashboard, alerte, SLO, trace distribuée, exporteur, règle d’alerte ou runbook d’incident n’est livré. Les métriques applicatives sont globales et sans histogramme de latence, statut par route, saturation, DB pool, retries, dépendances, taux de refus RBAC ou corrélation avec une trace. Les labels ne montrent pas de fuite de `customerId`, ce qui est positif, mais l’absence de labels métier rend le diagnostic opérationnel limité.

**Risque : moyen à élevé.** Le service peut être déclaré vivant alors qu’une dépendance critique n’est pas disponible, car `/health` est volontairement superficiel et `/ready` ne teste que la base locale. Il manque une définition documentée de liveness/readiness, des checks de dépendances bornés, des métriques de latence et erreurs, des traces, des alertes et un test de perte du collecteur.

## 7. Tests de charge, résilience et sécurité dynamique

Les tests unitaires et E2E présents couvrent de nombreux domaines fonctionnels. La configuration Playwright impose un seul worker, conserve les traces en échec et peut utiliser le mode Keycloak réel ou un mode persona de développement [3] [17]. La CI couvre les tests unitaires non intégration/non E2E, un job nommé `integration-tests`, des builds d’images et un smoke Compose [6].

Aucun fichier ou outil de charge n’a été trouvé : ni k6, Locust, JMeter, Gatling, scénario de montée en charge, budget de latence, seuil de taux d’erreur, test de saturation, test de reprise sous charge ou rapport de capacité. Le plan de test demande des cibles de performance, mais aucune mesure n’est livrée [4]. Le job `integration-tests` exécute seulement `pytest -m integration` et aucun test marqué `integration` n’a été confirmé comme présent dans l’inventaire exécuté.

Les tests de résilience présents sont principalement des tests de domaine et de gouvernance. Ils ne démontrent pas la perte de PostgreSQL, Keycloak, un service aval, le renouvellement de JWKS, la saturation d’un pool, la reprise après redémarrage, le double démarrage de migration ou la cohérence des audits pendant une panne partielle.

**Manque :** ajouter des scénarios reproductibles de charge nominale, pic et endurance avec dataset dimensionné ; fixer p50/p95/p99, taux d’erreur et saturation ; exécuter les tests dans un environnement isolé ; tester les dépendances et la reprise ; publier les résultats comme artefacts CI.

## 8. Docker Compose et `local-stack`

Compose est structuré en réseaux `edge`, `app` interne et `data` interne ; les volumes PostgreSQL et Keycloak sont nommés ; plusieurs services disposent d’un healthcheck, de limites CPU/mémoire, de `no-new-privileges` et de capacités supprimées [7]. Les scripts `migrate.sh` et `seed.sh` démarrent PostgreSQL, attendent sa santé, appliquent Alembic puis créent les données de démonstration. Le script de migration accorde les droits par schéma et retire explicitement à Feature Store et ML Engine certains accès croisés [10]. Le script `local-stack.sh` est destiné au développement sans Docker et démarre les services avec `BOA_AUTH_DISABLED=true` ; le README le réserve à des données synthétiques [14].

La séparation des schémas est utile mais le script accorde `SELECT, INSERT, UPDATE, DELETE` sur toutes les tables et les privilèges par défaut du schéma à chaque rôle propriétaire [10]. Il manque une preuve de contrôle continu des dérives de privilèges, une migration atomique testée en concurrence et une séparation stricte entre compte de migration, propriétaire et compte runtime. Le secret de base de données est passé dans une URL et dans des arguments de commande de conteneur [7] [10], ce qui augmente le risque d’exposition via inspect/logs/processus.

Le Compose ne fournit ni TLS, ni reverse proxy de production, ni réplication PostgreSQL, ni sauvegarde, ni outil de restauration, ni stratégie de versionnement des images, ni rollback de stack. `docker compose down --volumes` dans la CI détruit volontairement les volumes après le smoke test [6] ; c’est correct pour l’isolation CI mais ce n’est pas une stratégie de récupération de données.

## 9. CI et contrôles de qualité réellement présents

Le workflow déclenche les contrôles sur `main`, pull requests et manuellement. Il limite les permissions GitHub à `contents: read`, annule les exécutions obsolètes et sépare validation infrastructure, tests/lint backend, build frontend, intégration, scans de sécurité, build/scan d’images et smoke Compose [6]. Les images sont construites sans push et analysées par Trivy. Les logs Compose sont sauvegardés en artefact même en cas d’échec.

Les manques sont substantiels pour un cycle d’exploitation : pas de test E2E Playwright dans le workflow CI, pas de test de charge, pas de test de backup/restore, pas de contrôle de migration downgrade/rollback, pas de vérification de matrice RBAC exhaustive, pas de scan IaC ou Dockerfile spécialisé, pas de SBOM/artifact signé, pas de provenance SLSA, pas de déploiement canary/blue-green, pas de validation d’un environnement de staging ni approbation de promotion. Le job `integration-tests` suppose que des tests portent le marqueur `integration`; il n’y a pas de preuve dans le workflow que la stack complète est démarrée pour ce job.

La commande locale `pytest -q` échoue pendant la collecte sur `database`, alors que le workflow appelle `pytest` depuis la racine après installation du paquet backend [6]. Ce point doit être rendu déterministe : soit installer le paquet racine/database, soit imposer `PYTHONPATH`, soit déplacer/configurer les tests de seed, puis ajouter un smoke identique à celui de CI.

## 10. Sauvegarde, restauration, rollback et exploitation

### Éléments présents

Le rollback de versions ML et de Scoring Policy est implémenté comme opération métier gouvernée et testé dans `tests/e2e/governance.spec.ts` [3]. Les versions précédentes restent représentées, et les audits de gouvernance enregistrent les actions. La readiness métier expose un état bloquant plutôt que de prétendre à une performance de production, ce qui est prudent [18].

### Éléments absents

Aucun script `pg_dump`, `pg_restore`, sauvegarde WAL, réplication, snapshot chiffré, rotation de backup, test de restauration ou procédure RPO/RTO n’a été trouvé. Le document de finalisation reconnaît explicitement `HA / backup / secrets — NON IMPLÉMENTÉ` et précise qu’aucun exercice de restauration équivalent production n’est fourni [19]. Aucun runbook n’explique qui déclenche une restauration, comment vérifier l’intégrité, comment remonter Keycloak avec sa base, comment rejouer les migrations, comment réconcilier l’outbox ou comment basculer DNS/traffic.

Le rollback testé concerne le modèle, la policy ou la règle, **pas l’image applicative, le schéma de base, la configuration Keycloak, les secrets, le frontend ou la version de Compose**. Il n’y a pas de stratégie de migration réversible ni de compatibilité N/N-1 démontrée. Un rollback métier ne protège donc pas contre une release défectueuse ou une migration destructive.

**Bloqueur : critique.** Définir RPO/RTO, sauvegardes chiffrées et testées, restauration complète sur environnement isolé, conservation et rétention, procédure de perte de région/volume, rollback de release et de migration, et preuve d’un exercice périodique.

## 11. Registre synthétique des risques et actions attendues

| ID | Constat | Niveau | Preuve | Condition de clôture |
|---|---|---:|---|---|
| R-01 | Secrets `DevOnly-*` dans realm, Compose et defaults | Critique | [2] [5] [7] | Gestionnaire de secrets, rotation, refus hors local, scan CI dédié |
| R-02 | Authentification désactivable avec principal global | Critique | [1] [14] | Garde-fou d’environnement, profil local séparé, test de non-démarrage hors local |
| R-03 | Audit non immuable au sens fort | Élevé | [8] [9] [12] | Append-only SQL, rôle propriétaire séparé, hash chain/signature, WORM/SIEM et tests d’altération |
| R-04 | Pseudonymisation limitée à des identifiants déterministes | Élevé | [13] [14] | Classification PII, minimisation, chiffrement, rétention/purge et tests anti-fuite |
| R-05 | Observabilité avancée documentée mais non déployée | Élevé | [7] [16] | Prometheus/Grafana/OTel ou équivalent, alertes, traces, dashboards et runbooks |
| R-06 | Aucun test de charge reproductible | Élevé | Inventaire `tests/`, `scripts/`, [4] | Scénarios k6/Locust, seuils p95/p99, endurance et artefacts CI |
| R-07 | Aucun backup/restore et RPO/RTO | Critique | [19] | Backup chiffré, restore testé, RPO/RTO, exercice périodique |
| R-08 | Rollback limité aux artefacts métier | Élevé | [3] [11] | Rollback de release, schéma, configuration et secrets avec compatibilité N/N-1 |
| R-09 | CI sans E2E, charge, restore et matrice RBAC exhaustive | Moyen/élevé | [6] | Jobs CI dédiés et critères de promotion |
| R-10 | `pytest` racine non reproductible localement | Moyen | Résultat d’exécution §1 | Commande documentée qui passe depuis checkout propre |

## Références

[1]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/platform.py "Authentification OIDC, principal, rôles, corrélation et endpoints opérationnels"
[2]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/infrastructure/keycloak/realm.json "Realm Keycloak, clients, comptes de service et rôles"
[3]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/tests/e2e/governance.spec.ts "Tests E2E de gouvernance, RBAC, rollback et Scoring Policy"
[4]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/test-plan.md "Plan de tests sécurité, RBAC, intégration, E2E et performance"
[5]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/infrastructure/.env.example "Variables d’environnement locales et secrets de développement"
[6]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/.github/workflows/ci.yml "Workflow CI réellement présent"
[7]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/infrastructure/docker-compose.yml "Composition Docker, réseaux, variables, profils et healthchecks"
[8]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/models/entities.py "Modèles SQL d’audit, décision, actions et hashes"
[9]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/audit/service.py "Construction de l’audit et hash canonique SHA-256"
[10]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/scripts/migrate.sh "Migrations et privilèges PostgreSQL par schéma"
[11]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/rule-studio.md "Règles de rollback versionné et conservation de l’historique"
[12]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/data-model.md "Modèle de données et intention append-only de l’audit"
[13]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/technical/ids.py "Identifiants déterministes par domaine"
[14]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/README.md "Démarrage, mode local sans auth et données synthétiques"
[15]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/platform.py "Middleware de logs, corrélation, health, readiness et métriques"
[16]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/architecture/architecture.md "Architecture cible observabilité, Prometheus, Grafana et OpenTelemetry"
[17]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/tests/e2e/playwright.config.ts "Configuration Playwright réellement présente"
[18]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/backend/src/boa_oi/operations/api.py "Readiness et gouvernance opérationnelle"
[19]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/finalization-status-2026-09-19.md "État final et non-implémentation de HA, backup et secrets"

> **Note de chemin :** la référence [16] doit être lue dans le dépôt local à `file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/architecture/architecture.md`; le chemin abrégé dans l’URL de référence est conservé uniquement comme libellé documentaire et ne constitue pas une preuve distincte.

## Recommandation de passage en exploitation

Ne pas promouvoir ce dépôt directement vers une plateforme bancaire. Autoriser seulement un environnement de développement avec données synthétiques et secrets dédiés. Pour une étape de staging, traiter d’abord R-01, R-02, R-05, R-06 et R-07, puis exécuter une campagne de tests RBAC complète, un restore observé, un test de charge et une revue indépendante de l’audit immuable. La promotion devra être conditionnée par des artefacts CI conservés et par un runbook validé, et non par la seule réussite du smoke Compose.

---

*Rapport produit par audit statique et exécution locale en lecture seule ; aucune modification du code source n’a été effectuée.*
