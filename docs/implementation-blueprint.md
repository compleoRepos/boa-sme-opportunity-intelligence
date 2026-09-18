# Blueprint d’implémentation exécutable — BOA SME Opportunity Intelligence

**Statut :** décision finale avant construction du MVP  
**Auteur :** Manus AI  
**Périmètre :** architecture, ordre de construction, critères de passage et contrôles d’implémentation.  
**Interdiction :** ce document ne fournit aucun code applicatif. Les arborescences, contrats et commandes mentionnés sont des cibles de conception, pas une implémentation.

## 1. Synthèse de décision

Ce blueprint consolide le cahier source et les cinq documents existants du projet : architecture, contrat API, modèle de données, règles métier et plan de test [1] [2] [3] [4] [5] [6]. La couverture fonctionnelle est complète : les **65 sections** du cahier source sont reprises dans la matrice d’exigence et rattachées à un composant et à un test. Les documents existants couvrent déjà la plupart des domaines attendus, mais ils contiennent plusieurs contradictions qui empêcheraient une construction rapide et réellement exécutable. La décision d’environnement imposée tranche ces contradictions : le backend sera en **Python 3.12 avec FastAPI**, la persistance applicative utilisera **SQLAlchemy et Alembic**, le frontend sera en **React et TypeScript**, la base sera **PostgreSQL**, l’identité sera portée par **Keycloak**, et les services seront réellement séparés en conteneurs Docker Compose avec des appels HTTP entre services.

Le MVP doit rester un système de microservices pragmatique. Il ne doit pas devenir un monolithe parce qu’une bibliothèque commune existe. La bibliothèque partagée est acceptée uniquement pour les contrats, les utilitaires techniques et les primitives de calcul pures qui ne possèdent ni base, ni route FastAPI, ni workflow interservices. Chaque service reste propriétaire de son modèle, de ses migrations Alembic, de ses routes, de ses règles et de son schéma PostgreSQL.

La trajectoire retenue privilégie l’exécution vérifiable. Le flux cible est : **données synthétiques → Mock Banking APIs HTTP → Banking Integration Service → services propriétaires → analytics → signaux → opportunités → explication → action RM → outcome → audit**. Les opportunités ne sont jamais chargées comme données de démonstration. Elles sont calculées après import, à partir des transactions et des soldes réellement présents dans PostgreSQL.

## 2. Décisions finales et arbitrages normatifs

| Sujet | Décision finale pour l’implémentation | Contradiction tranchée | Critère vérifiable |
|---|---|---|---|
| Runtime backend | Tous les services backend sont des applications **Python 3.12 + FastAPI**. | Les documents historiques sont harmonisés avec la décision finale. | Aucun projet d’une stack historique n’est créé ; chaque service expose `/health`, `/ready`, `/metrics`, `/openapi.json` et `/swagger` via FastAPI. |
| Persistance | Chaque service utilise **SQLAlchemy 2.x** et **Alembic** pour son schéma. | Les documents parlent de migrations sans imposer l’outillage ; l’outillage est maintenant unique. | Une migration Alembic par service ne modifie que le schéma de son service. |
| Séparation des services | Un conteneur Docker Compose par service métier, plus frontend, PostgreSQL, Keycloak, Mock Banking API et jobs. | L’exigence interdit le monolithe ; le partage de code ne doit pas recréer un backend unique. | Les services ont des ports internes distincts et communiquent par HTTP via DNS Compose. |
| Base de données | Une instance PostgreSQL physique pour le MVP, avec **schéma et utilisateur SQL dédiés par service**. | `architecture.md` évoque bases logiques séparées ; `data-model.md` autorise des clés étrangères inter-schémas. | Aucun service n’a de permission sur un schéma tiers ; pas de clé étrangère inter-schémas dans les migrations métier. |
| Keycloak | Keycloak local porte l’OIDC, les rôles et les clients de service. | Certains passages laissent penser que le Gateway suffit ; chaque service doit aussi valider son accès. | Les tests refusent token absent, audience invalide, rôle insuffisant et accès hors périmètre. |
| API Gateway | Gateway FastAPI léger : validation, routage, RBAC de premier niveau, rate limiting, corrélation, erreurs. | Le Gateway ne doit pas devenir l’orchestrateur métier. | Aucun calcul de signal, confiance, priorité ou opportunité dans le Gateway. |
| Appels interservices | HTTP interne avec `httpx`, timeouts, retries bornés, correlation ID et tokens de service. | L’architecture existante introduit broker futur comme choix ferme ; l’environnement impose des appels HTTP réels. | Les tests interservices observent le chemin HTTP complet ; aucune lecture directe de base tierce. |
| Événementiel MVP | Événements métier persistés dans des outbox locales et exposés par contrat ; broker non obligatoire au MVP. | broker futur est utile mais alourdit l’exécution ; le cahier autorise un mécanisme simple. | Les événements sont auditables et idempotents ; un broker pourra être ajouté sans changer les règles métier. |
| Bibliothèque partagée | Deux bibliothèques internes : `boa_platform` pour le transversal technique et `boa_domain_kernel` pour primitives pures. | Risque de transformer la mutualisation en monolithe. | Les bibliothèques ne contiennent ni ORM, ni routes FastAPI, ni clients HTTP de service, ni workflows métier complets. |
| Pagination | Pagination par **curseur opaque + pageSize** pour toutes les listes significatives. | Les documents mélangent `page/pageSize` et `cursor`. | Les réponses de liste utilisent `data`, `meta.pageSize`, `meta.nextCursor`, `meta.hasMore` et éventuellement `meta.totalCount`. |
| Scores | `confidence` est sur **0..1** ; `priorityScore` est sur **0..100** ; `priorityLevel` est `P1..P4`. | Les documents alternent `priorityScore` 0..1 et 0..100. | Les tests de contrat rejettent une priorité hors 0..100 et une confiance hors 0..1. |
| Actions | Enum canonique : `ACCEPT_OPPORTUNITY`, `DISMISS_OPPORTUNITY`, `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP`, `SCHEDULE_MEETING`, `MARK_CONVERTED`. | Les documents utilisent aussi `ACCEPT` et `DISMISS`. | L’OpenAPI et les tests E2E n’acceptent que l’enum canonique. |
| Horizon du stress | `FINANCIAL_STRESS_SIGNAL` porte `horizon = 0-1_MONTH` et le libellé « signal relationnel à examiner ». | `architecture.md` mentionne `0-1_MONTH`, l’API et les règles indiquent `0-1_MONTH`. | Aucun champ, libellé ou test ne parle de score de risque, score de crédit, probabilité de défaut ou décision de crédit. |
| Produits | Product Service possède catalogue et détention de produits. Customer Service ne duplique pas le catalogue. | Certains endpoints client suggèrent une ownership ambiguë. | `customer_products` appartient au schéma `product`; le Customer 360 compose via API. |
| Données de démonstration | Le générateur crée clients, comptes, transactions, soldes, produits détenus et règles, mais **zéro opportunité** avant moteur. | Le besoin interdit les opportunités hardcodées. | Un contrôle de seed échoue si `opportunity.opportunities` n’est pas vide avant calcul. |
| GenAI et ML | Aucun LLM, aucun modèle ML et aucun scoring opaque dans le moteur du MVP. | La roadmap future peut prêter à confusion. | Les quatre opportunités sont produites par règles déterministes et statistiques descriptives auditables. |

## 3. Bounded contexts et responsabilités exécutables

Un bounded context est ici une frontière de langage, de données et de déploiement. Chaque contexte ci-dessous correspond à un service FastAPI séparé, sauf Keycloak, PostgreSQL et le frontend. Les contrats partagés ne remplacent pas les APIs HTTP.

| Bounded context | Conteneur cible | Données possédées | Responsabilités | Exclusions obligatoires |
|---|---|---|---|---|
| Présentation RM | `frontend` | Aucune donnée métier persistée | Dashboard, listes, filtres, Customer 360, explications, actions, administration visible selon rôle. | Aucun JSON local comme backend ; aucun calcul de règle, score ou opportunité. |
| Entrée API et sécurité | `api-gateway` | Aucun domaine métier | Validation OIDC/JWT, RBAC de premier niveau, routage, corrélation, erreurs, limites de débit, versioning. | Pas de SQL métier ; pas de calcul d’analytics, signal, opportunité ou priorité. |
| Référentiel client | `customer-service` | `customer.*` | PME, secteurs, segments, affectations RM, recherche client et périmètre. | Pas de solde, transaction, produit maître ou opportunité. |
| Comptes et soldes | `account-service` | `account.*` | Comptes, types, devises, lignes de crédit, snapshots de solde. | Pas de règle d’opportunité ni de détection commerciale. |
| Transactions | `transaction-service` | `transaction.*` | Transactions normalisées, contreparties, catégories, filtres, import idempotent. | Pas d’opportunité ; pas de classification à partir de texte libre au moment de décision. |
| Intégration bancaire | `banking-integration-service` | `integration.*` | Anti-corruption layer, appels aux Mock Banking APIs, normalisation, batches, provenance, reprise. | Aucun `if mock` dans les services métier ; aucun accès direct du moteur aux mocks. |
| APIs bancaires simulées | `mock-banking-api` | Fixtures synthétiques ou stockage propre | Endpoints HTTP simulant Core Banking, Payments, Trade Finance, CRM et Product. | Pas de réponse injectée dans React ou dans l’Opportunity Service. |
| Analytics transactionnel | `analytics-service` | `analytics.*` | Métriques 7D/30D/90D/180D/365D, baselines, qualité, saisonnalité simple. | Pas de recommandation produit ; pas d’action commerciale. |
| Détection de signaux | `signal-service` | `signal.*` | Règles de signaux, seuils, sévérité, preuve, statut `OBSERVED` ou `CONFIRMED`. | Un signal ne contient jamais une recommandation commerciale. |
| Catalogue produit | `product-service` | `product.*` | Catalogue, versions, règles d’éligibilité publiables, produits détenus, gaps produit. | Les règles d’opportunité ne codent pas les noms de produits. |
| Opportunités | `opportunity-service` | `opportunity.*` | Stratégies déterministes, confidence, priorité, horizon, explanation, audit décisionnel. | Ne possède ni transactions, ni clients, ni produits, ni actions. |
| Actions et feedback | `action-service` | `action.*` | Acceptation, rejet, contact, suivi, rendez-vous, conversion, outcomes. | Ne réécrit pas l’évidence de la décision moteur. |
| Identité | `keycloak` | Base Keycloak dédiée | Realm, clients OIDC, rôles, tokens utilisateur et service. | Aucun mot de passe applicatif dans les services métier. |
| Audit et observabilité | Transversal, tables locales ou `audit.*` | `audit.*` et logs | Logs structurés, audit append-only, métriques, traces, health checks. | Pas de secret, token ou donnée sensible dans les sorties. |

## 4. Architecture exécutable retenue dans Docker Compose

Le déploiement local doit démarrer comme une plateforme complète mais raisonnable. Le profil par défaut contient les services nécessaires à la démonstration fonctionnelle. Les profils supplémentaires ajoutent l’observabilité avancée ou des outils d’administration sans changer le comportement métier.

Le chemin utilisateur est le suivant : le chargé d’affaires ouvre le frontend React, s’authentifie avec Keycloak, puis appelle uniquement l’API Gateway. Le Gateway route ensuite vers les services propriétaires. Le navigateur ne voit ni PostgreSQL, ni les APIs internes, ni les Mock Banking APIs.

Le chemin de données est le suivant : le générateur synthétique prépare des faits bancaires et les expose ou les charge via les Mock Banking APIs. Banking Integration Service consomme ces APIs par HTTP, transforme les données en contrats canoniques, puis pousse les imports vers Customer, Account, Transaction et Product Service. Analytics lit les lots nécessaires par endpoints internes paginés et calcule les métriques. Signal Service évalue les règles de signaux. Opportunity Service combine signaux, métriques, profil client et gaps produit. Action Service enregistre ensuite les décisions du RM et les outcomes.

Le MVP n’a pas besoin d’un broker par défaut. Les événements comme `TransactionImported`, `MetricsCalculated`, `SignalDetected`, `OpportunityCreated`, `OpportunityAccepted`, `OpportunityDismissed`, `CustomerContacted`, `MeetingScheduled`, `OfferCreated`, `OpportunityConverted`, `OpportunityRejected` et `OpportunityNotRelevant` sont persistés dans les outbox des services émetteurs avec `eventId`, `eventType`, `eventVersion`, `occurredAt`, `aggregateId`, `customerId`, `correlationId`, `causationId`, `idempotencyKey` et `payload`. Une phase ultérieure pourra publier ces mêmes événements dans Kafka, broker futur ou Azure Service Bus sans modifier les règles.

## 5. Modèle de données final

La base du MVP est une instance PostgreSQL unique dans Docker Compose. Cette décision simplifie le démarrage, mais elle ne donne pas le droit de partager une base comme un monolithe. Chaque service possède son schéma et son utilisateur SQL. Un service n’a accès qu’à son schéma, sauf éventuelles vues de diagnostic explicitement administrées. Les références interservices sont des identifiants opaques et stables ; il n’y a pas de clé étrangère inter-schémas dans les migrations métier.

| Schéma | Service propriétaire | Tables minimales de départ | Règles de propriété |
|---|---|---|---|
| `customer` | `customer-service` | `customers`, `sectors`, `customer_segments`, `relationship_managers`, `customer_relationships` | Source de vérité des PME et des affectations RM. |
| `account` | `account-service` | `accounts`, `credit_lines`, `account_balances` | Source des comptes, lignes et soldes. |
| `transaction` | `transaction-service` | `transactions`, `counterparties`, `transaction_tags`, `transaction_import_batches` | Source des mouvements normalisés et de leur idempotence. |
| `product` | `product-service` | `products`, `product_versions`, `customer_products`, `product_gap_snapshots` | Source du catalogue et des produits détenus. |
| `analytics` | `analytics-service` | `metric_definitions`, `metric_snapshots`, `metric_values`, `calculation_runs`, `seasonality_baselines` | Source des indicateurs calculés et de la qualité des données. |
| `signal` | `signal-service` | `signal_rules`, `signals`, `signal_evidence`, `signal_runs` | Source des signaux atomiques et de leurs preuves. |
| `opportunity` | `opportunity-service` | `opportunity_rules`, `engine_runs`, `opportunities`, `opportunity_evidence`, `opportunity_recommendations`, `decision_audit` | Source des décisions commerciales calculées. |
| `action` | `action-service` | `opportunity_actions`, `action_outcomes`, `customer_responses` | Source des actions RM et de la boucle de feedback. |
| `integration` | `banking-integration-service` | `source_systems`, `import_batches`, `source_records`, `outbox_events`, `processed_events` | Source de la provenance et de l’anti-corruption layer. |
| `audit` | Transversal gouverné | `audit_logs` | Journal append-only des accès, décisions et changements administratifs. |
| `keycloak` | `keycloak` | Tables internes Keycloak | Identité technique ; aucun service métier ne lit directement ces tables. |

Les migrations Alembic doivent être rangées avec chaque service. Un bootstrap SQL limité crée les rôles, bases ou schémas et permissions. Les migrations applicatives ne créent pas d’objet dans le schéma d’un autre service. Les index initiaux doivent couvrir les filtres de liste, la pagination par curseur, les dates, le client, le type de transaction, les signaux, les opportunités et les actions. Les transactions et audits peuvent être partitionnés plus tard ; le MVP doit d’abord démontrer la justesse et la pagination.

Les codes de métriques sont normalisés en `UPPER_SNAKE_CASE` côté stockage et contrat : `MONTHLY_INFLOW`, `MONTHLY_OUTFLOW`, `AVERAGE_BALANCE`, `MINIMUM_BALANCE`, `MAXIMUM_BALANCE`, `TRANSACTION_COUNT`, `SUPPLIER_PAYMENT_AMOUNT`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_AMOUNT`, `INTERNATIONAL_FLOW_GROWTH`, `INTERNATIONAL_TRANSACTION_COUNT`, `CREDIT_LINE_UTILIZATION`, `CREDIT_UTILIZATION_CHANGE`, `CASH_SURPLUS_AMOUNT` et `SURPLUS_DAY_RATIO`. Les propriétés JSON restent en `camelCase`.

## 6. Contrats API et conventions finales

Toutes les routes publiques passent par `/api/v1` sur l’API Gateway. Les routes internes passent par `/internal/v1` et ne sont disponibles que sur le réseau Compose applicatif. Chaque service publie son propre OpenAPI ; le Gateway publie un OpenAPI agrégé pour le frontend. Les routes de santé sont `/health`, `/ready` et `/metrics`.

La réponse de liste canonique est : `data`, `meta.pageSize`, `meta.nextCursor`, `meta.hasMore`, `meta.totalCount` facultatif, `links.self`, `links.next` facultatif et `correlationId`. `pageSize` est borné par défaut à 25 et plafonné à 100. Les tris sont en liste blanche. Les filtres inconnus retournent `400 UNKNOWN_FILTER`. Les erreurs utilisent un format unique avec `code`, `message`, `correlationId`, `timestamp` et `details` non sensibles. Une stack trace ne sort jamais du backend.

Les endpoints publics minimaux à préserver sont :

| Domaine | Routes publiques minimales |
|---|---|
| Opportunités | `GET /api/v1/opportunities`, `GET /api/v1/opportunities/{id}`, `GET /api/v1/opportunities/{id}/explanation` |
| Actions | `POST /api/v1/opportunities/{id}/actions`, `GET /api/v1/opportunities/{id}/actions`, `GET /api/v1/actions`, `PATCH /api/v1/actions/{id}` |
| Clients | `GET /api/v1/customers`, `GET /api/v1/customers/{id}`, `GET /api/v1/customers/{id}/accounts`, `GET /api/v1/customers/{id}/products`, `GET /api/v1/customers/{id}/transactions` |
| Comptes | `GET /api/v1/accounts`, `GET /api/v1/accounts/{id}`, `GET /api/v1/accounts/{id}/balances` |
| Transactions | `GET /api/v1/transactions`, `GET /api/v1/transactions/{id}` |
| Analytics et signaux | `GET /api/v1/analytics/metrics`, `GET /api/v1/customers/{id}/metrics`, `GET /api/v1/signals`, `GET /api/v1/signals/{id}` |
| Produits et admin | `GET /api/v1/products`, `GET /api/v1/products/{id}`, `GET /api/v1/admin/rules`, `PATCH /api/v1/admin/rules/{id}`, `GET /api/v1/admin/engine`, `POST /api/v1/admin/recompute` |

Les endpoints internes nécessaires au pipeline sont notamment `POST /internal/v1/imports/*`, `POST /internal/v1/analytics/recompute`, `POST /internal/v1/signals/evaluate`, `POST /internal/v1/opportunities/generate` et les exports paginés nécessaires aux calculs. Ces endpoints exigent des tokens de service et des clés d’idempotence lorsqu’ils créent un job ou un fait.

## 7. Matrice exigence → composant → test

Les familles de tests sont abrégées ainsi : **UT** pour unitaires, **CT** pour contrats, **IT** pour intégration, **BR** pour règles métier déterministes, **FP** pour faux positifs, **E2E** pour Playwright, **SEC** pour sécurité, **PERF** pour performance, **OPS** pour observabilité et exploitation, et **CI** pour pipeline. La matrice ci-dessous couvre explicitement les **65 sections** du cahier source.

| Section | Exigence couverte | Composant responsable | Test de passage minimal |
|---:|---|---|---|
| 1 | Objectif métier : savoir quels clients contacter, pourquoi, pour quel besoin et avec quelle confiance. | Opportunity Service, Signal Service, Analytics Service, Frontend. | BR-001 à BR-004 et E2E dashboard avec preuves visibles. |
| 2 | Architecture microservices, API-first, domain-driven, sécurisée, observable et testable. | Tous services, API Gateway, Docker Compose. | CT interservices, test statique anti-monolithe, OPS health et metrics. |
| 3 | Architecture cible avec Web App, Gateway, services domaine, moteur, analytics et intégration. | Frontend, Gateway, tous services métier, Banking Integration. | IT Compose vérifiant que chaque route passe par HTTP et non par base partagée. |
| 4 | BIAN-inspired sans prétendre à une certification. | Architecture, `architecture/bian-mapping.md`, services domaine. | Revue documentaire et CT tags OpenAPI par domaine. |
| 5 | API Gateway : auth, routing, correlation, rate limit, versioning. | `api-gateway`. | SEC JWT/RBAC, CT `/api/v1`, test rate limit et correlation ID. |
| 6 | Customer Service : PME, profil, secteur, segment, RM, comptes et produits exposés par contrat. | `customer-service`, Gateway pour composition. | CT clients, IT périmètre RM, E2E Customer 360. |
| 7 | Account Service : comptes, soldes, devises, statuts, types. | `account-service`. | IT migrations comptes/soldes et CT balances. |
| 8 | Transaction Service : transactions filtrables par dates, type, direction, devise, catégorie, international et montants. | `transaction-service`. | CT filtres, PERF pagination, IT idempotence d’import. |
| 9 | Banking Integration Service comme anti-corruption layer avec adapters remplaçables. | `banking-integration-service`, `mock-banking-api`. | IT appel HTTP mock via adapter, test statique absence de `if mock` métier. |
| 10 | Transaction Analytics : métriques 7D, 30D, 90D, 180D, 365D et comparaisons historiques. | `analytics-service`. | UT fenêtres et baselines, BR pipeline complet. |
| 11 | Signal Detection : moteur réel de signaux avec sévérité, seuils et preuves. | `signal-service`. | UT par type de signal, CT signal, IT evidence persistée. |
| 12 | Opportunity Engine : stratégies RuleBased et Statistical, ML futur. | `opportunity-service`, `boa_domain_kernel` limité. | UT stratégies, BR-001 à BR-012, test absence GenAI. |
| 13 | Quatre opportunités MVP obligatoires. | Opportunity Service, Product Service, Signal Service. | BR-001 à BR-004 avec type, horizon, preuves et recommandations. |
| 14 | Confidence score explicable, configurable et non codé dans le frontend. | Opportunity Service, Admin Rules. | UT composants de score, CT explanation, E2E détails de confiance. |
| 15 | Explainability : WHY, WHAT, WHEN, CONFIDENCE, EVIDENCE. | Opportunity Service, Frontend. | CT `/explanation` et E2E inspection d’une opportunité. |
| 16 | Product Catalog Service et absence de hardcoding des produits. | `product-service`, Opportunity Service. | CT catalogue, UT sélection produit, test statique chaînes interdites dans règles. |
| 17 | Prioritization Engine avec facteurs de priorité. | Opportunity Service. | UT priorité bornée 0..100, tri stable, E2E top opportunities. |
| 18 | Dashboard RM professionnel. | Frontend, Gateway, Opportunity Service. | E2E login → dashboard, vérification données backend. |
| 19 | Customer 360 avec comptes, balances, transactions, produits, tendances, signaux, opportunités, actions et graphiques. | Frontend, Gateway, services propriétaires. | E2E Customer 360 et CT composition partielle sans valeurs inventées. |
| 20 | Action Management : accept, dismiss, contact, follow-up, meeting, converted. | `action-service`, Frontend. | E2E action workflow, IT idempotence et transitions. |
| 21 | Feedback loop recommendation → action RM → response → outcome. | Action Service, Opportunity projections, audit. | IT outcomes et KPI, E2E contacted puis converted. |
| 22 | PostgreSQL avec tables minimales et audit. | Tous services propriétaires, Alembic. | IT migrations sur base vide, contraintes, permissions par schéma. |
| 23 | Données réalistes : 500 PME, 12 mois, scénarios positifs et faux positifs. | `demo-data-generator`, Mock Banking API, Integration. | IT seed volume, BR/FP sur clients oracle, contrôle zéro opportunité avant moteur. |
| 24 | Générateur de données recréable. | `demo-data-generator`. | CI seed déterministe, hash de manifeste, idempotence. |
| 25 | Contrats OpenAPI 3.0 avec request, response, errors, auth et exemples. | Chaque service et Gateway. | CT OpenAPI, validation schémas, génération client frontend. |
| 26 | Authentification réelle OAuth2/OIDC avec Keycloak et rôles. | Keycloak, Gateway, services. | SEC login, tokens invalides, rôles RM/Branch/Admin/Data Analyst. |
| 27 | Sécurité : JWT, RBAC, validation, rate limit, audit, secrets env. | Gateway, services, CI. | SEC SAST, gitleaks, tests authz horizontale et verticale. |
| 28 | API versioning `/api/v1`. | Gateway et services. | CT routes sans version refusées ou non exposées ; OpenAPI versionné. |
| 29 | Event-driven ready avec événements métier. | Outbox locale dans services, contrats events. | CT schémas d’événements, IT idempotence `eventId`. |
| 30 | Observabilité : logs structurés, correlation ID, health, metrics, OpenTelemetry-ready. | `boa_platform`, tous services. | OPS `/health`, `/ready`, `/metrics`, traces/correlation de bout en bout. |
| 31 | Error handling standardisé sans stack trace. | `boa_platform`, Gateway, services. | CT erreurs et SEC non-divulgation. |
| 32 | Frontend React/TypeScript réel avec routing, auth, client API, états, pagination, filtres. | `frontend`. | E2E états loading/error/empty, test absence fixtures locales. |
| 33 | Design enterprise banking sobre orienté données, actions, confiance et explication. | Frontend. | Revue UX et E2E parcours critiques. |
| 34 | Filtres par type, confiance, priorité, secteur, segment, RM, horizon, date. | Gateway, services, Frontend. | CT filtres et E2E combinaison de filtres. |
| 35 | Recherche par nom, client ID, compte, industrie. | Customer, Account, Transaction, Gateway, Frontend. | IT recherche et permissions ; PERF index utilisés. |
| 36 | Pagination backend pour listes importantes. | Tous services de liste, Frontend. | CT curseur, PERF pas de chargement complet. |
| 37 | Performance : index, pagination, caching pertinent, analytics séparé. | PostgreSQL, Analytics, Gateway. | PERF 500 PME et volume transactionnel, plan de requête. |
| 38 | Docker Compose avec services minimaux. | `infrastructure/docker-compose.yml`. | CI `docker compose up --build`, readiness globale. |
| 39 | CI/CD : lint, tests, build, security scan, docker build. | `.github/workflows/ci.yml`. | CI verte avec Ruff/mypy/pytest/Playwright/scans. |
| 40 | Tests unitaires, intégration et E2E obligatoires. | Tous services et frontend. | Couverture UT/IT/E2E selon plan de test. |
| 41 | Tests métier déterministes des quatre cas. | Analytics, Signal, Opportunity. | BR-001 à BR-004 et tests de frontières. |
| 42 | Tests faux positifs : saisonnalité, one-off, virement international isolé. | Analytics, Signal, Opportunity. | FP-001 à FP-007. |
| 43 | Saisonnalité : période courante, précédente, baseline historique. | Analytics Service, Signal Service. | UT baseline médiane/MAD, FP saisonnalité. |
| 44 | Explainability API `/opportunities/{id}/explanation`. | Opportunity Service, Gateway. | CT schéma explanation et E2E preuves complètes. |
| 45 | Audit des décisions moteur. | Opportunity Service, audit logs. | IT decision audit et hash/version/références. |
| 46 | Configuration des seuils. | Signal Service, Opportunity Service, Admin API. | UT injection config, IT changement de version, audit config. |
| 47 | Administration règles, seuils, produits, activation, version moteur. | Frontend admin, Product, Signal, Opportunity. | SEC Admin only, E2E lecture/modification contrôlée. |
| 48 | Privacy by Design, données synthétiques, pas d’API LLM externe avec données client. | Generator, CI, tous services. | SEC scan données/logs et test absence LLM. |
| 49 | Pas de GenAI dans le core decision engine. | Opportunity Service, CI. | Test statique dépendances interdites et BR déterministes offline. |
| 50 | Future AI architecture préparée sans ML inutile. | Interfaces Strategy, docs roadmap. | CT interface future non activée ; tests champion deterministic. |
| 51 | Mapping BIAN futur. | `architecture/bian-mapping.md`. | Revue documentaire et cohérence avec services. |
| 52 | Mock Bank API HTTP réellement consommée par adapters. | `mock-banking-api`, Integration. | IT prouve appel HTTP mock et non injection directe. |
| 53 | Contrats entre microservices et dépendances documentées. | `contracts/openapi`, services. | CT provider/consumer et test timeout/retry. |
| 54 | No static development rule. | Frontend, CI, revues. | E2E compare API/backend ; test statique interdit fixtures métier en UI. |
| 55 | Definition of Done complète. | Tous composants. | Auto-validation globale sans étape obligatoire ignorée. |
| 56 | Livrables obligatoires. | Arborescence cible du dépôt. | Revue de présence des fichiers et docs. |
| 57 | Diagramme d’architecture et data flow. | `architecture/architecture-diagram.png`, `architecture/data-flow.md`. | Revue documentaire et cohérence avec Compose. |
| 58 | Scénario de démo 5 minutes. | Frontend, seed, moteur, actions. | E2E smoke horodaté et script de démonstration. |
| 59 | Business KPI dashboard optionnel sans revenu inventé. | Action Service, Opportunity Service, Frontend management. | CT KPI calculés ; valeurs simulées marquées `SIMULATED`. |
| 60 | Roadmap future phases 2 à 4. | Documentation architecture. | Revue roadmap sans impact MVP. |
| 61 | Technologie enterprise-ready. | Python 3.12, FastAPI, React TS, PostgreSQL, Keycloak, Docker. | CI vérifie versions runtime et builds d’images. |
| 62 | Real Functional MVP : fonctionnalité avant démo visuelle. | Tous composants. | E2E aucun bouton sans action, aucun mock frontend. |
| 63 | Auto-validation avant livraison. | Script CI/OPS. | Script démarre, migre, seed, teste APIs, E2E, audit et health. |
| 64 | Final acceptance : 500 PME → transactions → analytics → signaux → opportunités → priorisation → RM → action → outcome. | Pipeline complet. | Test d’acceptation final sur PostgreSQL réel. |
| 65 | Comportement d’ingénierie : analyser, documenter, puis implémenter sans masquer les limites. | Blueprint, revues, CI. | Checklist PR et rapport final `IMPLEMENTED / PARTIAL / NOT IMPLEMENTED`. |

## 8. Ordre de construction recommandé

La construction doit suivre un ordre strict, car plusieurs risques proviennent d’une inversion entre frontend, données et moteur. Un écran ne doit être construit que si le contrat backend qui l’alimente existe ou si l’écran affiche explicitement un état `TODO` non trompeur.

| Phase | Objectif | Travaux autorisés | Critère de passage |
|---:|---|---|---|
| 0 | Figer les décisions | Valider ce blueprint, corriger les documents qui contredisent Python/FastAPI, nommer les enums canoniques. | Revue architecture terminée ; matrice 65/65 acceptée. |
| 1 | Socle repo et plateforme | Créer l’arborescence, images Python de base, `boa_platform`, `boa_domain_kernel`, Compose minimal, Keycloak realm, bootstrap Postgres. | `docker compose up` démarre Keycloak, Postgres, Gateway vide et health checks. |
| 2 | Contrats et migrations | Écrire OpenAPI par service, migrations Alembic initiales, permissions par schéma, enveloppes d’erreur. | CT OpenAPI et IT migrations sur base vide. |
| 3 | Services de référence | Implémenter Customer, Account, Product, Transaction et Mock Banking API. | CRUD/lecture contrôlée, import idempotent, filtres et pagination. |
| 4 | Intégration et seed | Implémenter Banking Integration et Demo Data Generator via HTTP. | 500 PME, 12 mois, secteurs et scénarios présents ; zéro opportunité préchargée. |
| 5 | Analytics | Calculer métriques, fenêtres, baselines, qualité et saisonnalité simple. | UT métriques et IT recompute sur seed. |
| 6 | Signaux | Évaluer signaux atomiques avec règles versionnées et preuves. | UT par signal, FP de base, CT signal. |
| 7 | Opportunités | Générer les quatre opportunités, confidence, priorité, explication et audit. | BR-001 à BR-012 et CT `/explanation`. |
| 8 | Actions et feedback | Créer Action Service, outcomes, idempotence, projections de statut. | E2E action → contact → conversion et audit. |
| 9 | Frontend complet | Dashboard, opportunités, Customer 360, signaux, actions, produits, admin. | E2E principal et tests de filtres/recherche/pagination. |
| 10 | Observabilité, sécurité et CI | Logs, métriques, traces, scans, rate limiting, tests de charge raisonnables. | CI verte, aucune vulnérabilité critique, OPS visible. |
| 11 | Auto-validation et démo | Script d’orchestration, rapport, données de démo et scénario 5 minutes. | Acceptation section 64 réussie de bout en bout. |

La phase 1 peut créer des squelettes vides de tous les services afin de tester le réseau et les checks de santé. Elle ne doit pas anticiper les règles métier. À partir de la phase 3, chaque phase livre un incrément testable, persistant et joignable par HTTP.

## 9. Critères de passage entre phases

Les critères de passage sont des portes de qualité. Une phase ne passe pas au vert avec un test ignoré, une fixture qui contourne le service réel ou une fonctionnalité frontend non reliée. Un échec bloquant doit être corrigé ou documenté comme sortie explicite du périmètre avant la suite.

### 9.1 Passage du socle aux services métier

Le socle est accepté lorsque Docker Compose crée les réseaux `edge`, `app` et `data`, que PostgreSQL et Keycloak deviennent prêts, que le Gateway résout les noms DNS internes et que tous les conteneurs backend utilisent Python 3.12. Les secrets de développement viennent d’un fichier local non versionné ou de variables d’environnement. Le realm Keycloak est importable de façon déterministe. Les utilisateurs synthétiques et les clients de service existent, mais aucun token ou mot de passe réel n’est committé.

### 9.2 Passage des services de référence au calcul

Customer, Account, Product et Transaction Service doivent avoir appliqué leurs propres migrations Alembic et exposer leurs contrats OpenAPI. Banking Integration doit appeler la Mock Banking API par HTTP. Un import répété avec la même clé ne doit pas dupliquer de données. Le dataset doit contenir au moins 500 PME, les huit secteurs demandés, douze mois complets, des comptes, des soldes, des transactions et des produits détenus. Les tables d’opportunités, d’évidence et d’actions doivent être vides avant le premier run moteur.

### 9.3 Passage d’Analytics à Signal

Les cinq fenêtres obligatoires sont calculées avec une `asOfDate` fixe. Chaque métrique porte une version de calcul, une couverture, une qualité et une référence au lot d’entrée. Les transferts internes, transactions annulées et doublons sont exclus selon les règles documentées. Les tests vérifient le plancher de dénominateur, les valeurs précédentes nulles, les devises incomplètes et la saisonnalité. Une métrique `INSUFFICIENT_HISTORY` ne peut pas déclencher seule une opportunité.

### 9.4 Passage de Signal à Opportunity

Les huit types de signaux sont évalués avec des règles actives et versionnées. Chaque signal possède au moins une preuve persistée. Un signal observé une seule fois reste `OBSERVED` sauf marge forte explicitement configurée ; une règle d’opportunité qui exige la persistance ne l’accepte pas comme confirmation. Les cas saisonniers et ponctuels ne doivent pas devenir des signaux confirmés à tort.

### 9.5 Passage du moteur au frontend

Les quatre cas positifs, leurs frontières et les faux positifs doivent être verts. Chaque opportunité contient une explication persistée, et non recalculée différemment lors de la lecture. Les produits recommandés sont résolus depuis Product Service. La confiance est bornée entre 0 et 1. La priorité est bornée entre 0 et 100 et ordonnée de façon stable. Le vocabulaire de crédit interdit n’apparaît nulle part dans les réponses, l’interface ou les logs.

### 9.6 Passage à l’acceptation finale

Le smoke E2E doit accomplir : login Keycloak, dashboard, ouverture d’une opportunité, lecture des preuves, acceptation, création d’un suivi, contact et conversion. La décision et les actions doivent être auditables par `correlationId`. Les tests d’accès hors portefeuille, de rôle insuffisant et de token invalide doivent être verts. Les cibles de performance initiales du plan de test doivent être mesurées. La stack doit pouvoir être supprimée puis recréée avec le même seed et produire des sorties métier équivalentes.

## 10. Workflow d’état sans double ownership

Les documents existants font porter `ACCEPTED`, `DISMISSED` et `CONVERTED` tantôt par Opportunity Service, tantôt par Action Service. L’implémentation doit séparer deux concepts :

- `opportunityStatus`, possédé par Opportunity Service, vaut `OPEN`, `EXPIRED` ou `SUPERSEDED`. Il décrit la validité de la décision moteur.
- `engagementStatus`, possédé par Action Service, est dérivé de l’historique des actions et outcomes : `UNTOUCHED`, `ACCEPTED`, `DISMISSED`, `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED` ou `NOT_RELEVANT`.

Le Gateway peut composer les deux statuts dans la réponse du dashboard, mais ne les persiste pas. Une action n’altère jamais l’évidence ni la version de la décision. Cette séparation évite une transaction distribuée et une double source de vérité. Une future projection événementielle pourra rapprocher les deux vues sans changer les API métier.

## 11. Sécurité et autorisation opérationnelles

Le frontend utilise Authorization Code avec PKCE auprès de Keycloak. Le Gateway valide la signature, l’issuer, l’audience, l’expiration et les rôles. Chaque service valide aussi le token de service ou le contexte utilisateur signé qui lui est destiné ; il ne fait pas confiance à un header libre envoyé par le navigateur. Pour le MVP Compose, le service-to-service utilise le flux `client_credentials` Keycloak. Le mTLS interne est différé, mais les ports de service restent non publiés vers l’hôte.

L’autorisation croise le rôle et le périmètre. Un Relationship Manager ne lit que son portefeuille. Un Branch Manager lit sa branche. Un Data Analyst lit les métriques et signaux autorisés, mais ne mène pas d’action commerciale. Un Admin gère les règles et le catalogue. Lorsque révéler l’existence d’une ressource hors périmètre constitue une fuite, le service renvoie `404` plutôt que `403`.

Les notes d’action sont bornées, validées et traitées comme potentiellement sensibles. Les logs masquent les tokens, cookies, secrets, chaînes de connexion, payloads complets de transaction et notes libres. Les images Docker fonctionnent avec un utilisateur non root lorsque possible. Les dépendances, images et secrets sont scannés dans la CI.

## 12. Règles métier finales à ne pas réinterpréter

Les comparaisons principales utilisent une fenêtre 90D, la période précédente et la baseline historique. Les fenêtres 7D, 30D, 180D et 365D servent à la récence, à la confirmation, à la persistance et à la saisonnalité. Les seuils sont strictement supérieurs dans les règles initiales, conformément aux formulations `> 25 %`, `> 20 %`, `> 15 %` et `> 30 %`. Une valeur exactement égale au seuil ne déclenche donc pas la condition tant qu’une configuration versionnée ne déclare pas explicitement une comparaison inclusive.

`INVESTMENT_FINANCING` exige croissance des encaissements, des paiements fournisseurs et du volume, ainsi que l’absence de financement récent. `TRADE_FINANCE` exige croissance des flux internationaux, fréquence croissante et produit absent ou sous-utilisé. `CASH_INVESTMENT` exige un solde moyen élevé, un excédent persistant et une faible utilisation de ligne. `FINANCIAL_STRESS_SIGNAL` exige une baisse des encaissements ou du solde, combinée à une utilisation de ligne en hausse.

Les valeurs encore marquées « à valider par BOA » dans les règles existantes doivent recevoir des **valeurs de démonstration explicitement étiquetées `DEMO_DEFAULT`** pour que le MVP soit exécutable. Elles ne peuvent pas rester nulles dans la configuration active. Elles ne sont pas présentées comme des paramètres bancaires validés. Chaque valeur porte une version, un auteur technique, une justification et une date d’effet.

La confidence mesure la qualité de l’évidence d’une règle déjà satisfaite. Elle n’est ni une probabilité de conversion ni une probabilité de défaut. Les seuils de niveau initiaux sont `LOW < 0,50`, `MEDIUM de 0,50 à < 0,75` et `HIGH >= 0,75`. La priorité suit la formule sur 100 décrite dans les règles métier, avec `P1 >= 80`, `P2 >= 60`, `P3 >= 40` et `P4 < 40`. Une confidence `LOW` plafonne la priorité à `P3`.

## 13. Risques d’implémentation et traitements

| Risque | Probabilité / impact | Traitement MVP | Signal d’alerte |
|---|---|---|---|
| Reconstruction d’un monolithe via la librairie partagée | Moyenne / critique | Règles de dépendance en CI ; bibliothèque sans ORM, routes, repositories ni workflows interservices. | Un service importe le package `domain` d’un autre ou une entité SQLAlchemy tierce. |
| Démarrage Compose fragile avec de nombreux services | Élevée / élevée | Health checks, retries applicatifs, migrations one-shot, profils limités, ordre de build stable. | Conteneurs en restart loop ou démarrage dépendant d’un timing arbitraire. |
| Latence excessive due aux appels HTTP en chaîne | Moyenne / élevée | Endpoints batch, lectures parallèles, timeouts, projection de lecture ciblée, pas de N+1. | Customer 360 ou dashboard dépasse le p95 cible. |
| Incohérence de données interservices | Moyenne / élevée | Ownership strict, idempotence, watermarks, versions, état de job observable, pas de FK inter-schémas. | Opportunité sans client, produit ou snapshot résolvable. |
| Seed trop volumineux pour un poste développeur | Élevée / moyenne | Génération en batches, COPY côté services d’import si contractuellement encapsulé, profil `smoke` plus petit réservé aux tests rapides. | OOM, timeout ou seed de plusieurs dizaines de minutes. |
| Analytics lit trop de transactions par HTTP | Élevée / élevée | Export batch paginé/compressé, endpoint interne par lot et watermark, calcul incrémental futur. | Des millions de requêtes unitaires ou N+1. |
| Paramètres BOA non validés | Élevée / élevée | Valeurs `DEMO_DEFAULT`, clairement marquées, versionnées et non promues en production. | Configuration active incomplète ou présentée comme validée. |
| Saisonnalité limitée à 12 mois | Élevée / moyenne | Médiane de fenêtres comparables, MAD si assez d’observations, plafond de confiance. | Le moteur prétend comparer deux années complètes avec seulement 12 mois. |
| Double ownership de l’état d’opportunité | Moyenne / élevée | Séparer décision moteur et engagement RM comme en section 10. | Les deux services écrivent un champ `status` concurrent. |
| Divergence des contrats OpenAPI | Moyenne / élevée | Contract-first, clients générés, tests consumer/provider, blocage sur rupture. | Frontend ou service utilise un champ absent du contrat publié. |
| RBAC appliqué seulement au Gateway | Moyenne / critique | Validation et scope dans chaque service, tokens de service, tests d’accès direct interne. | Un service accepte une requête sans audience ou périmètre valide. |
| Faux positifs commerciaux | Moyenne / critique | Persistance, baseline, qualité, tests FP, explication des non-déclenchements. | Une transaction unique crée Trade Finance ou Investment Financing. |
| Mélange score commercial / score de risque | Faible / critique | Vocabulaire contrôlé, tests de non-régression, revue UX et API. | Présence de `riskScore`, `creditScore`, `PD` ou `defaultProbability`. |
| Observabilité trop lourde pour le MVP | Moyenne / moyenne | Logs JSON et métriques obligatoires ; collector/tracing complet sous profil optionnel. | Le profil par défaut ne tient pas sur une machine de développement. |
| Audit incomplet lors d’un échec partiel | Moyenne / élevée | Audit transactionnel local, correlation ID, jobs avec état et outbox. | Une action réussit sans audit ou une décision n’a pas de version. |
| Valeur potentielle ou KPI inventé | Moyenne / élevée | Champ absent par défaut ; toute valeur simulée porte `valueOrigin=SIMULATED`. | Le dashboard affiche un revenu ou ROI sans provenance. |

## 14. Limites acceptables et documentées du MVP

| Limite acceptée | Justification | Garde-fou obligatoire | Évolution prévue |
|---|---|---|---|
| Une seule instance PostgreSQL | Réduit le coût local et la mémoire. | Schémas et utilisateurs séparés, permissions strictes, aucune lecture SQL interservice. | Instance ou base par service en environnement BOA. |
| Pas de broker dans le profil par défaut | Le cahier autorise un mécanisme simple et les appels HTTP sont une contrainte de l’environnement. | Outbox et contrats d’événement versionnés, consommateurs idempotents. | Kafka, broker futur ou Azure Service Bus. |
| Données entièrement synthétiques | Privacy by Design et démonstration reproductible. | Manifeste de seed, scan anti-donnée réelle, aucun import bancaire réel. | Connexion aux systèmes BOA après validation sécurité. |
| Saisonnalité simple | Douze mois limitent l’inférence saisonnière. | Baseline robuste, drapeau qualité et confidence plafonnée. | Historique pluriannuel et modèles saisonniers avancés. |
| Stratégie statistique descriptive seulement | Auditabilité et rapidité du MVP. | Médiane, MAD, planchers et règles déterministes documentés. | Modèle de propension gouverné en challenger. |
| Pas de mTLS interne en local | Complexité de certificats disproportionnée pour Compose. | Réseaux internes non exposés, tokens de service et secrets hors dépôt. | Service mesh ou PKI privée BOA. |
| Pas de haute disponibilité | Docker Compose n’est pas une plateforme de production. | Redémarrage idempotent, volumes nommés, backups de développement non sensibles. | Orchestrateur et services managés BOA. |
| Administration fonctionnelle limitée | L’objectif principal est le chemin transaction → opportunité → action. | Lecture complète et modification contrôlée des seuils/activations les plus importants. | Workflow d’approbation et séparation des tâches. |
| KPI management limité | Les outcomes disponibles au début sont synthétiques ou peu nombreux. | Aucune valeur commerciale inventée ; origine des valeurs visible. | Mesure sur outcomes CRM réels. |
| Notification externe absente | Aucun canal email/SMS/CRM n’est choisi. | Les actions sont persistées et consultables ; aucun bouton de notification factice. | Notification Service séparé après choix de canal. |
| Volumes de démonstration, non capacité production | 500 PME et jusqu’à environ 1,5 million de transactions valident le POC, pas la banque entière. | Cibles de charge consignées avec CPU/mémoire et plans de requête. | Tests de capacité et partitionnement en plateforme cible. |

Une limite acceptable ne doit jamais être masquée par l’interface. Si une fonction n’est pas disponible, elle est absente ou affichée comme `TODO` non interactive. Aucun bouton visible ne doit simuler une réussite.
## 15. Arborescence cible précise

L’arborescence suivante est normative. Chaque service listé sous `backend/services` est une application FastAPI indépendante avec son propre `pyproject.toml`, son image, son package Python, ses tests et, lorsqu’il persiste, ses migrations Alembic. Le gabarit `<service>` décrit la structure répétée ; il ne constitue pas un dossier littéral à créer.

```text
boa-sme-opportunity-intelligence/
├── README.md
├── Makefile
├── .env.example
├── .gitignore
├── pyproject.toml                         # outillage racine, pas application monolithique
├── pnpm-workspace.yaml
├── architecture/
│   ├── architecture.md                   # à aligner sur Python/FastAPI
│   ├── architecture-diagram.png
│   ├── bian-mapping.md
│   ├── data-flow.md
│   └── decisions/
│       ├── ADR-001-python-fastapi.md
│       ├── ADR-002-service-data-ownership.md
│       ├── ADR-003-http-and-outbox.md
│       └── ADR-004-shared-libraries-boundary.md
├── contracts/
│   ├── openapi/
│   │   ├── gateway-v1.yaml
│   │   ├── customer-v1.yaml
│   │   ├── account-v1.yaml
│   │   ├── transaction-v1.yaml
│   │   ├── banking-integration-v1.yaml
│   │   ├── analytics-v1.yaml
│   │   ├── signal-v1.yaml
│   │   ├── opportunity-v1.yaml
│   │   ├── product-v1.yaml
│   │   └── action-v1.yaml
│   └── events/
│       ├── event-envelope-v1.json
│       ├── transaction-imported-v1.json
│       ├── metrics-calculated-v1.json
│       ├── signal-detected-v1.json
│       ├── opportunity-created-v1.json
│       └── opportunity-action-v1.json
├── backend/
│   ├── libs/
│   │   ├── boa-platform/
│   │   │   ├── pyproject.toml
│   │   │   ├── src/boa_platform/{auth,correlation,errors,logging,metrics,http}/
│   │   │   └── tests/
│   │   └── boa-domain-kernel/
│   │       ├── pyproject.toml
│   │       ├── src/boa_domain_kernel/{money,periods,scoring,identifiers}.py
│   │       └── tests/
│   └── services/
│       ├── api-gateway/
│       ├── customer-service/
│       ├── account-service/
│       ├── transaction-service/
│       ├── banking-integration-service/
│       ├── mock-banking-api/
│       ├── analytics-service/
│       ├── signal-service/
│       ├── opportunity-service/
│       ├── product-service/
│       └── action-service/
├── backend/services/<service>/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini                        # sauf service sans persistance
│   ├── migrations/{env.py,versions/}
│   ├── src/<service_package>/
│   │   ├── main.py
│   │   ├── settings.py
│   │   ├── api/{public_v1,internal_v1,health}.py
│   │   ├── application/{commands,queries,ports}/
│   │   ├── domain/{entities,value_objects,rules,events}.py
│   │   └── infrastructure/{db,http_clients,repositories,outbox}/
│   └── tests/{unit,contract,integration}/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── src/
│   │   ├── app/
│   │   ├── auth/
│   │   ├── api/generated/
│   │   ├── components/
│   │   ├── features/{dashboard,opportunities,customers,signals,actions,products,administration}/
│   │   ├── routes/
│   │   └── styles/
│   └── tests/{unit,component}/
├── database/
│   ├── bootstrap/{001-create-schemas.sql,002-grant-service-roles.sql}
│   ├── migrations/README.md               # index vers migrations locales
│   └── seed/{README.md,reference-data/,manifests/}
├── tools/
│   ├── demo-data-generator/{pyproject.toml,Dockerfile,src/,tests/}
│   └── auto-validation/{README.md,scenarios/}
├── infrastructure/
│   ├── docker-compose.yml
│   ├── docker-compose.test.yml
│   ├── keycloak/{realm-export.json,README.md}
│   ├── prometheus/prometheus.yml
│   ├── otel/collector-config.yaml
│   └── grafana/provisioning/
├── tests/
│   ├── business/{fixtures,expected-results}/
│   ├── contracts/
│   ├── integration/
│   ├── architecture/
│   ├── security/
│   ├── performance/
│   └── e2e/{playwright.config.ts,specs/}
├── docs/
│   ├── api.md
│   ├── data-model.md
│   ├── business-rules.md
│   ├── test-plan.md
│   ├── implementation-blueprint.md
│   ├── security.md
│   ├── deployment.md
│   ├── demo-scenario.md
│   └── known-limitations.md
└── .github/workflows/{ci,contract-tests,compose-e2e,security}.yml
```

Le Gateway peut ne pas avoir Alembic puisqu’il ne possède aucune donnée métier. La Mock Banking API peut utiliser des fixtures synthétiques propres ou une persistance isolée, mais elle ne doit jamais écrire dans les schémas métier. Le dossier racine `database/migrations` ne contient pas de migration métier centralisée ; il documente seulement où trouver les migrations propriétaires.

## 16. Dépendances autorisées

Le graphe de dépendance doit rester acyclique au niveau des packages Python. Un service peut dépendre de `boa_platform` et de `boa_domain_kernel`. Il ne peut pas dépendre du package Python d’un autre service. Les échanges utilisent un client généré depuis OpenAPI ou un contrat HTTP explicitement versionné. Les événements utilisent les schémas JSON de `contracts/events`.

La bibliothèque `boa_domain_kernel` peut fournir les primitives génériques de période, montant, normalisation et score borné. Elle ne doit pas contenir `InvestmentFinancingRule`, `TradeFinanceRule`, `SignalRepository`, `OpportunityService` ou un modèle SQLAlchemy. Les règles de signaux restent dans Signal Service. Les règles d’opportunité, de confidence et de priorité restent dans Opportunity Service. Cette discipline permet de mutualiser ce qui est réellement commun sans fusionner les bounded contexts.

## 17. Auto-validation et Definition of Done exécutable

Le rapport d’auto-validation doit exécuter et consigner les prérequis, le démarrage Compose, la readiness, les migrations Alembic, l’import du realm Keycloak, le seed déterministe, les contrôles de volumes, l’authentification des quatre rôles, les tests unitaires, les contrats, les intégrations, les règles métier, les faux positifs, la sécurité, le smoke E2E, l’audit, la santé, les métriques et l’arrêt propre. Chaque étape porte un statut `PASS`, `FAIL`, `SKIPPED_OPTIONAL` ou `NOT_APPLICABLE`. Une étape obligatoire ne peut jamais être `SKIPPED` dans une release acceptée.

La release MVP est déclarée terminée uniquement si le rapport prouve :

1. le démarrage complet en Docker Compose sans manipulation cachée ;
2. la présence d’au moins 500 PME et de douze mois de données cohérentes ;
3. l’absence d’opportunité avant exécution du moteur ;
4. la production des quatre cas positifs depuis les faits PostgreSQL ;
5. l’absence de résultats sur les faux positifs obligatoires ;
6. une explication persistée et cohérente pour chaque opportunité ;
7. un parcours RM complet jusqu’à l’outcome ;
8. la sécurité Keycloak/RBAC et l’isolation par portefeuille ;
9. l’audit et la corrélation de bout en bout ;
10. l’absence de secret, stack trace publique, donnée réelle et vocabulaire de décision de crédit ;
11. les builds d’images, scans et tests verts ;
12. un rapport final séparant `IMPLEMENTED`, `PARTIALLY_IMPLEMENTED`, `NOT_IMPLEMENTED`, `KNOWN_LIMITATIONS`, `TECHNICAL_DEBT` et `NEXT_STEPS`.

## 18. Incohérences que l’implémentation doit impérativement éviter

Cette liste est le dernier contrôle contradictoire avant toute pull request d’implémentation.

1. **La stack backend est unique.** Elle est Python 3.12, FastAPI, SQLAlchemy et Alembic.
2. **Ne pas transformer les schémas PostgreSQL partagés en base monolithique.** Les clés étrangères, jointures et permissions inter-schémas sont interdites aux services métier.
3. **Ne pas confondre appels HTTP et imports de packages.** Un service n’importe jamais le code applicatif d’un autre service.
4. **Ne pas inverser le flux d’intégration.** Le sens correct est Banking Integration → Customer/Account/Transaction/Product après lecture des Mock Banking APIs.
5. **Ne pas imposer broker futur comme prérequis caché.** Le profil MVP utilise HTTP et outbox ; un broker reste une extension.
6. **Ne pas mélanger pagination par page et pagination par curseur.** Le contrat public canonique utilise `cursor` et `pageSize`.
7. **Ne pas mélanger les échelles de score.** Confidence vaut 0..1 ; priorité vaut 0..100.
8. **Ne pas utiliser deux enums d’action.** Les noms canoniques portent les suffixes explicites `*_OPPORTUNITY` pour acceptation et rejet.
9. **Ne pas laisser deux services posséder le statut d’engagement.** Opportunity possède la validité moteur ; Action possède l’interaction RM et l’outcome.
10. **Ne pas utiliser `0-1_MONTH` et `0-1_MONTH` comme horizons concurrents.** Le contrat MVP expose `0-1_MONTH` et un libellé relationnel séparé.
11. **Ne pas appeler `OUTFLOW_GROWTH` une baisse d’encaissement.** Les métriques et sens de variation restent distincts.
12. **Ne pas calculer une saisonnalité annuelle complète avec un historique insuffisant.** La qualité et le plafond de confidence doivent le signaler.
13. **Ne pas maintenir `ruleVersion` et `ruleSetVersion` sans convention.** L’API expose `ruleVersion` ; l’audit peut conserver un ensemble `ruleSetVersion` défini explicitement.
14. **Ne pas recalculer l’explication à la lecture.** L’endpoint restitue le snapshot ayant produit la décision.
15. **Ne pas semer de signaux ou d’opportunités comme oracle.** Seuls les faits bancaires et labels de test non visibles par le moteur sont générés.
16. **Ne pas coder les noms de produits dans les règles.** Les règles utilisent des codes ou catégories fournis par Product Service.
17. **Ne pas faire confiance au Gateway comme unique contrôle d’autorisation.** Chaque service protège ses routes et son périmètre.
18. **Ne pas exposer les endpoints internes, PostgreSQL ou les mocks au navigateur.** Le frontend appelle seulement le Gateway.
19. **Ne pas afficher une valeur commerciale simulée sans origine.** Toute valeur simulée est explicitement marquée `SIMULATED`.
20. **Ne pas promettre une fonctionnalité non branchée.** Aucun bouton factice, fallback JSON local ou page « fonctionnelle » sans API réelle.
21. **Ne jamais présenter `FINANCIAL_STRESS_SIGNAL` comme risque, crédit ou défaut.** C’est un signal relationnel à examiner par le chargé d’affaires.
22. **Ne pas déclarer le MVP terminé sur la seule base de tests unitaires.** L’acceptation exige le chemin complet Docker Compose, PostgreSQL, Keycloak, APIs HTTP et navigateur.

## Références

[1]: file:///home/ubuntu/upload/Pasted_content_100.txt "Cahier d’exigences — BOA SME Opportunity Intelligence"

[2]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/architecture/architecture.md "Architecture exécutable existante"

[3]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/api.md "Contrats API-first existants"

[4]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/data-model.md "Modèle relationnel et pipeline synthétique existants"

[5]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/business-rules.md "Spécification existante du moteur déterministe"

[6]: file:///home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/test-plan.md "Plan de tests existant"

## Contrôle de cohérence documentaire

La décision finale est **Python 3.12/FastAPI avec SQLAlchemy et Alembic**, et **HTTP + outbox** pour le MVP. Aucun broker n’est un prérequis. Les mentions historiques d’une autre stack ou d’un broker doivent être considérées comme annulées et ne sont pas normatives.
