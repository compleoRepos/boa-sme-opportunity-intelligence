# Plan de tests — BOA SME Opportunity Intelligence

**Version :** 1.0  
**Statut :** référentiel de validation du MVP  
**Périmètre :** frontend Relationship Manager, API Gateway, microservices métier, PostgreSQL, Keycloak/OIDC, adapters bancaires simulés, moteur analytique, moteur de signaux, moteur d’opportunités, actions et audit.

## 1. Objectif et décision de qualité

Ce plan définit la stratégie de tests nécessaire pour démontrer que le MVP transforme des transactions synthétiques réellement persistées dans PostgreSQL en signaux puis en opportunités commerciales **déterministes, explicables, auditables et actionnables**. Il couvre les frontières de domaine et les contrats entre les services suivants : API Gateway, Customer, Account, Transaction, Banking Integration, Analytics, Signal, Opportunity, Product et Action.

Le moteur ne prend aucune décision de crédit et ne produit ni score de risque, ni probabilité de défaut, ni décision de crédit. Toute validation doit préserver cette distinction. Une régression qui présente `FINANCIAL_STRESS_SIGNAL` comme un score de risque est bloquante, même si les calculs sous-jacents sont corrects.

Le plan vise quatre propriétés de confiance :

1. **Exactitude métier :** les règles, seuils, horizons, scores de confiance et priorités produisent le résultat attendu sur des cas connus et sur leurs frontières.
2. **Intégrité technique :** les données, APIs, migrations, événements, authentification et appels interservices respectent leurs contrats.
3. **Sécurité et traçabilité :** l’accès est contrôlé par Keycloak et RBAC, les secrets ne sont pas exposés, et chaque décision est reconstituable.
4. **Utilisabilité opérationnelle :** le parcours du chargé d’affaires reste fonctionnel, observable et suffisamment performant avec au moins 500 PME et un volume de transactions significatif.

Le plan ne remplace pas les tests de pénétration formels, la certification de sécurité bancaire ou la validation réglementaire. Il fournit les seuils minimaux de sortie du MVP et identifie les contrôles à renforcer avant une connexion aux systèmes réels de BOA.

## 2. Principes de test

### 2.1 Règles non négociables

- Les données de test sont synthétiques. Aucune donnée bancaire réelle ne doit être importée dans l’environnement de test.
- Les opportunités sont calculées par le backend et le moteur. Elles ne sont jamais injectées comme fixtures frontend ou comme valeurs pré-calculées dans le dataset de démonstration.
- Les tests du moteur de décision n’utilisent pas de LLM. Ils doivent être déterministes, reproductibles et exécutables hors ligne.
- Chaque test distribué porte un `correlationId`. Chaque décision du moteur comporte au minimum `engineVersion`, `ruleVersion`, date de génération, références d’entrée, signaux, confiance et opportunité.
- Les seuils et règles sont lus depuis une configuration versionnée. Un test vérifie qu’une variation contrôlée de configuration change le résultat attendu sans modifier le code.
- Les tests contrôlent autant les résultats positifs que l’absence de résultat lorsqu’une opportunité ne doit pas être créée.
- Les tests frontend vérifient la donnée rendue depuis une API. Ils ne valident pas des tableaux codés en dur dans les composants.
- Les tests d’intégration utilisent PostgreSQL et Keycloak réels dans des conteneurs de test, ou des instances dédiées équivalentes. Un simple mock de repository ou de JWT ne suffit pas pour les scénarios de persistance et d’authentification.

### 2.2 Testabilité attendue

Chaque service doit exposer ou fournir un moyen de test contrôlé pour :

- démarrer et arrêter le service isolément ;
- vérifier `/health`, `/ready` et, lorsque pertinent, `/metrics` ;
- injecter un `correlationId` et le retrouver dans les logs ;
- sélectionner une version de règles et une horloge de test ;
- charger un jeu de données déterministe par seed ;
- réinitialiser la base et les données entre deux scénarios ;
- désactiver les appels réseau non nécessaires au test unitaire ;
- publier ou observer les événements métier sans dépendre d’un broker réel pour la suite rapide.

Les horloges, identifiants aléatoires et générateurs de données doivent être contrôlables. Un test métier ne doit pas dépendre de la date réelle, de l’ordre d’exécution ou de la disponibilité d’une API externe.

## 3. Pyramide de tests et répartition

La suite suit une pyramide : beaucoup de tests rapides au bas de la pyramide, moins de tests coûteux et distribués au sommet. Les pourcentages sont des repères de maintenance, pas une permission de réduire la couverture d’un risque critique.

| Niveau | Objet | Répartition indicative | Environnement | Blocage de livraison |
|---|---|---:|---|---|
| Unitaires | Fonctions pures, règles, transformations, validations | 55–65 % | Processus isolé, horloge et configuration contrôlées | Oui |
| Contrats | OpenAPI, schémas d’événements, compatibilité producteur/consommateur | 10–15 % | Services ou artefacts de contrat | Oui |
| Intégration technique | PostgreSQL, migrations, repositories, Keycloak, adapters | 10–15 % | Conteneurs réels | Oui |
| Interservices | Parcours Gateway → services → données, erreurs et résilience | 5–10 % | Docker Compose de test | Oui |
| E2E Playwright | Parcours RM dans le navigateur | 3–5 % | Stack complète, navigateur supporté | Oui pour le smoke ; non bloquant pour exploratoire |
| Sécurité | SAST, dépendances, secrets, DAST et tests d’autorisation | À chaque niveau | CI et environnement isolé | Oui pour les seuils critiques |
| Charge et endurance raisonnables | Latence, débit, erreurs, consommation | Suite planifiée | Environnement représentatif | Oui si seuils dépassés |

La suite rapide doit terminer avant les tests lourds. Les tests unitaires et contrats sont exécutés sur chaque commit. Les tests PostgreSQL, Keycloak, interservices et E2E sont exécutés sur chaque pull request. La charge, les scans DAST plus lourds et l’endurance sont exécutés au minimum avant une release et selon une cadence planifiée.

## 4. Environnements et données de test

### 4.1 Environnements

Trois profils sont nécessaires :

- **Rapide :** bibliothèques et services isolés pour les tests unitaires, avec doubles contrôlés et fixtures minimales.
- **Intégration :** Docker Compose avec PostgreSQL, Keycloak, services backend et adapters mockés exposés par API. Les migrations sont appliquées sur une base vide.
- **Acceptation :** stack complète incluant frontend, Gateway, tous les services, observabilité et dataset de démonstration. Les données sont supprimées à la fin ou dans un projet de test dédié.

Les URLs, clients Keycloak, secrets et limites de charge sont configurés par variables d’environnement. Les valeurs par défaut de développement ne doivent pas être réutilisées comme secrets de production.

### 4.2 Dataset de référence

Le générateur de démonstration doit produire, avec un seed fixe, au moins 500 PME, 12 mois de transactions et les secteurs prévus : industrie, import/export, distribution, services, BTP, agriculture, commerce et technologie. Il doit inclure des sociétés de croissance, stables, internationales, en excédent de trésorerie, en tension financière, normales et des cas faux positifs.

Le dataset de référence est versionné par un identifiant de seed et une version de schéma. Un contrôle de cohérence vérifie notamment :

- les clés étrangères entre clients, comptes, transactions, produits et actions ;
- la concordance entre mouvements et balances lorsque la règle de génération le prévoit ;
- des dates comprises dans la fenêtre de 12 mois ;
- des devises et catégories valides ;
- l’absence de doublons d’identifiants ;
- la présence de chaque scénario attendu et de son étiquette de référence hors production ;
- l’absence d’opportunités pré-insérées avant exécution du moteur.

Les labels de scénario ne doivent pas être exposés à l’interface ni utilisés directement par le moteur. Ils servent uniquement à vérifier qu’une détection est reconstruite à partir des transactions.

### 4.3 Isolation, reproductibilité et nettoyage

Chaque scénario doit pouvoir être rejoué à partir d’une base vide, d’un snapshot immuable ou d’un namespace isolé. Le nettoyage doit supprimer les opportunités, signaux, actions et audits générés par le scénario sans supprimer les migrations. Un test est considéré comme non fiable s’il réussit uniquement après l’exécution d’un autre test.

Les dates de référence sont fixes. Les identifiants peuvent être déterministes dans les fixtures ; lorsqu’ils ne le sont pas, les assertions comparent leur forme et leurs relations plutôt qu’une valeur aléatoire exacte.

## 5. Tests unitaires

Les tests unitaires sont rapides, isolés et sans réseau ni base de données. Ils couvrent les fonctions pures et les composants remplaçables des services.

### 5.1 Analytics et transformations

Tester les fenêtres 7, 30, 90, 180 et 365 jours ainsi que la comparaison à la période précédente et à la baseline historique. Les cas doivent couvrir les bornes de dates, l’absence de données, les transactions annulées, les devises, les crédits et débits, les montants nuls, les arrondis et les périodes incomplètes.

Vérifier que :

- `MONTHLY_INFLOW`, `MONTHLY_OUTFLOW`, `AVERAGE_BALANCE`, `MINIMUM_BALANCE`, `MAXIMUM_BALANCE` et `TRANSACTION_COUNT` sont calculés sur le bon périmètre ;
- les taux de croissance ont une convention documentée lorsque la valeur précédente est nulle ou négative ;
- le signe d’une variation est conservé ;
- une transaction hors fenêtre ne modifie pas la métrique ;
- les métriques sont reproductibles pour les mêmes entrées ;
- les agrégations ne mélangent pas des clients ou des comptes.

### 5.2 Détection de signaux

Chaque signal doit être testé sur : seuil non atteint, seuil exactement atteint, seuil dépassé, valeur manquante, données contradictoires, période trop courte et évolution persistante. Vérifier la structure de sortie : identifiant, client, type, sévérité, valeur, seuil, date et preuves lisibles.

Les types minimaux sont `INFLOW_GROWTH`, `OUTFLOW_GROWTH`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_GROWTH`, `BALANCE_SURPLUS`, `BALANCE_DECLINE`, `CREDIT_UTILIZATION_INCREASE` et `TRANSACTION_VOLUME_GROWTH`. La sévérité doit être dérivée de la configuration, pas de constantes dispersées dans le code.

### 5.3 Règles d’opportunité

Tester séparément chaque stratégie et les combinaisons de stratégies. Les noms de produits sont fournis par le catalogue de produits ou par une interface de sélection ; ils ne sont pas codés dans la règle.

Les règles minimales sont :

- **Investment Financing :** encaissements supérieurs à 25 %, paiements fournisseurs supérieurs à 20 %, volume transactionnel supérieur à 15 % et absence de financement d’investissement récent.
- **Trade Finance :** flux internationaux supérieurs à 30 %, fréquence internationale en hausse et produit Trade Finance absent ou sous-utilisé.
- **Cash Investment :** solde moyen durablement élevé, excédent persistant et faible utilisation du crédit.
- **Financial Stress Signal :** baisse des encaissements supérieure à 25 % ou baisse du solde supérieure à 20 %, avec utilisation du crédit en hausse.

Chaque condition doit avoir un test positif et un test négatif. Les tests de frontière utilisent exactement 25 %, 20 %, 15 %, 30 %, -25 %, -20 % et la limite de crédit définie. Le comportement attendu à la frontière doit être explicite : seuil inclusif ou exclusif selon la configuration publiée.

### 5.4 Confiance, priorité et explicabilité

Tester le calcul par composants, les pondérations, les bornes [0, 1], les niveaux `HIGH`, `MEDIUM`, `LOW`, la récence, la cohérence historique, le manque produit et la force du signal. Vérifier qu’une composante absente est traitée selon une règle documentée et ne produit pas `NaN`.

Tester la priorité avec des opportunités identiques, des scores ex æquo, des valeurs manquantes et des urgences différentes. Le tri doit être stable et déterministe. L’explication doit contenir `WHY`, `WHAT`, `WHEN`, `CONFIDENCE`, `EVIDENCE`, les métriques, les seuils, la comparaison historique et le produit recommandé.

### 5.5 Validations communes

Tester les schémas d’entrée et de sortie, les filtres, la pagination, le tri, la recherche, les enums, les limites de montants, les dates invalides, les UUID ou identifiants invalides et les erreurs standardisées. Aucun test unitaire ne doit accepter une stack trace, un token ou un secret dans une réponse publique.

## 6. Tests métier déterministes

Les cas ci-dessous sont des tests d’acceptation du moteur. Ils doivent exécuter le même pipeline que la production de test : transactions → analytics → signaux → opportunités → priorité → explication. Il ne suffit pas d’appeler directement une fonction de règle pour considérer le pipeline validé.

| ID | Données synthétiques contrôlées | Résultat attendu |
|---|---|---|
| BR-001 | Encaissements +40 %, paiements fournisseurs +30 %, volume +20 %, aucun financement d’investissement récent | Une opportunité `INVESTMENT_FINANCING`, horizon `1-3_MONTHS`, avec les trois preuves et une confiance calculée |
| BR-002 | Flux internationaux +50 %, fréquence en hausse, Trade Finance absent | Une opportunité `TRADE_FINANCE`, horizon `0-3_MONTHS`, avec preuve de l’absence ou sous-utilisation du produit |
| BR-003 | Solde moyen élevé sur plusieurs périodes, excédent persistant, faible utilisation du crédit | Une opportunité `CASH_INVESTMENT`, horizon `0-1_MONTH`, avec preuves de persistance |
| BR-004 | Encaissements -35 %, solde -25 %, utilisation du crédit +40 % | Un `FINANCIAL_STRESS_SIGNAL`, sans vocabulaire de score ou de décision de crédit |
| BR-005 | Chaque condition d’Investment Financing juste sous son seuil | Aucune opportunité Investment Financing |
| BR-006 | Produit d’investissement récent présent malgré les métriques de croissance | Aucune opportunité Investment Financing si l’exclusion est applicable |
| BR-007 | Flux internationaux +50 % mais fréquence stable et aucun autre signal | Aucune opportunité Trade Finance |
| BR-008 | Excédent ponctuel sur une seule période et utilisation du crédit élevée | Aucune opportunité Cash Investment |
| BR-009 | Encaissements en baisse mais utilisation du crédit stable ou en baisse | Aucun Financial Stress Signal selon la règle minimale |
| BR-010 | Deux règles satisfaites par le même client | Les deux opportunités sont produites seulement si la configuration les autorise ; elles restent distinctes, explicables et auditables |
| BR-011 | Même input, même version de règles et même date de référence, exécuté deux fois | Sorties métier équivalentes ; aucune variation liée à l’aléatoire |
| BR-012 | Modification d’un seuil configuré | La décision et l’explication reflètent la nouvelle version de règle, avec audit de la configuration utilisée |

Les assertions doivent vérifier les valeurs métier, la présence des preuves, la version de moteur, la version de règles, les recommandations issues du catalogue et la persistance des résultats. Elles doivent aussi vérifier l’absence de résultats parasites pour les autres types d’opportunités.

## 7. Faux positifs, saisonnalité et robustesse métier

Le moteur doit éviter de transformer un événement isolé en tendance. Les cas suivants sont obligatoires :

- **FP-001 — activité saisonnière :** décembre est supérieur à novembre, mais comparable aux décembres historiques. Aucune opportunité de croissance ne doit être créée sur le seul différentiel mensuel.
- **FP-002 — transaction ponctuelle :** un paiement exceptionnel augmente temporairement les flux, sans persistance ni hausse du volume structurel. Aucune tendance ne doit être déclarée.
- **FP-003 — virement international isolé :** un seul transfert important ne suffit pas à déclencher Trade Finance.
- **FP-004 — seuil instable :** la métrique franchit le seuil une fois puis repasse immédiatement sous le seuil. Le moteur applique la règle de persistance ou produit une preuve signalant l’insuffisance de répétition.
- **FP-005 — client déjà équipé :** les métriques sont fortes, mais le produit concerné est déjà utilisé à un niveau suffisant. L’opportunité correspondante n’est pas générée.
- **FP-006 — données incomplètes :** une période historique manque. Le résultat est absent, dégradé avec confiance plafonnée, ou explicitement marqué selon la politique de qualité des données ; il ne doit pas être présenté comme une certitude.
- **FP-007 — doublons d’import :** rejouer la même transaction ne doit pas doubler les métriques ni créer deux fois le même signal.

Les tests de saisonnalité comparent, lorsque les données le permettent, la période courante à la période précédente et à la baseline historique. Chaque détection doit indiquer dans son explication les périodes comparées. Une correction anti-faux-positif ne doit pas supprimer les vrais cas BR-001 à BR-004.

## 8. Contrats d’API et d’événements

### 8.1 Contrats REST

Chaque service publie un contrat OpenAPI 3.0 couvrant requête, réponse, erreurs, authentification et exemples. Les tests de contrat vérifient au minimum les endpoints suivants :

- Gateway : `/api/v1/opportunities`, `/api/v1/customers`, `/api/v1/customers/{id}`, `/api/v1/signals`, `/api/v1/products` et actions d’opportunité ;
- Customer : clients, comptes associés et produits détenus ;
- Account : comptes et balances ;
- Transaction : filtres de dates, type, direction, devise, catégorie, international et montants ;
- Explanation : `/api/v1/opportunities/{id}/explanation` ;
- santé : `/health`, `/ready`, `/metrics`.

Les tests valident les codes HTTP, le content type, les champs obligatoires, les enums, la pagination, la compatibilité ascendante des champs et le format d’erreur : `code`, `message`, `correlationId`. Une erreur interne ne doit jamais contenir de stack trace.

Les changements incompatibles doivent exiger une nouvelle version, par exemple `/api/v2`. Une propriété ajoutée de manière optionnelle ne doit pas casser les consommateurs existants. Les contrats de réponse ne doivent pas exposer de secret, token, mot de passe ou donnée technique interne.

### 8.2 Contrats interservices et événements

Tester les contrats producteurs/consommateurs pour les interfaces Customer, Transaction, Financial Metrics, Signal, Opportunity, Product et Action. Vérifier les événements `TransactionImported`, `SignalDetected`, `OpportunityCreated`, `OpportunityAccepted`, `OpportunityDismissed`, `CustomerContacted` et `OpportunityConverted`.

Chaque événement doit comporter un identifiant, un type, une version, une date, un `correlationId`, une référence métier et un payload conforme. Les consommateurs doivent tolérer un champ optionnel inconnu et refuser proprement une version incompatible. Les tests de compatibilité garantissent que les adapters simulés peuvent être remplacés par un adapter réel implémentant la même interface sans modifier le moteur.

## 9. Intégration PostgreSQL

Les tests PostgreSQL exécutent les migrations sur une base vide puis vérifient le schéma, les contraintes, les index et le comportement transactionnel. Les tables minimales sont `customers`, `accounts`, `transactions`, `balances`, `products`, `customer_products`, `signals`, `opportunities`, `opportunity_evidence`, `opportunity_actions`, `relationship_managers` et `audit_logs`.

Les contrôles couvrent :

- application et réexécution sûre des migrations ;
- contraintes de clés étrangères, unicité, nullabilité et enums ;
- timestamps `created_at`, `updated_at`, `created_by` lorsque pertinents ;
- index des filtres de transactions, dates, clients, types, opportunités et actions ;
- isolation entre clients ;
- rollback lorsqu’une écriture multi-table échoue ;
- idempotence de l’import et de la génération ;
- pagination côté serveur, sans chargement de 500 clients ou de toutes les transactions dans le navigateur ;
- conservation des preuves et de l’audit après modification d’une action ;
- absence d’opportunités initiales dans le seed avant calcul du moteur ;
- suppression ou anonymisation complète des données dans un environnement de test.

Les tests de repositories comparent le résultat de requêtes à des fixtures connues. Les tests d’agrégation vérifient notamment qu’aucune transaction d’un autre compte ou client n’est incluse. Les tests de concurrence couvrent deux générations simultanées et deux actions concurrentes ; le système doit éviter les doublons et conserver une transition d’état cohérente.

## 10. Authentification Keycloak et autorisation

Keycloak est exécuté dans un environnement d’intégration avec un realm de test, un client OIDC, des utilisateurs synthétiques et les rôles `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN` et `DATA_ANALYST`.

### 10.1 Authentification

Vérifier :

- connexion avec identifiants valides et refus avec identifiants invalides ;
- expiration, signature invalide, issuer incorrect, audience incorrecte et token malformé ;
- absence de token, token révoqué ou session expirée ;
- refresh selon la politique retenue ;
- mot de passe conforme aux politiques Keycloak ;
- validation des claims sans confiance dans des champs envoyés par le navigateur ;
- propagation sûre de l’identité et du `correlationId` vers les services ;
- déconnexion et nettoyage de session côté frontend.

### 10.2 RBAC et isolation

Construire une matrice d’autorisation contractuelle et l’exécuter sur chaque route sensible.

| Capacité | RM | Branch Manager | Admin | Data Analyst |
|---|---:|---:|---:|---:|
| Consulter opportunités et explications | Oui, portefeuille | Oui, branche | Scope client explicite | Oui, lecture autorisée |
| Consulter clients et transactions autorisés | Oui, portefeuille | Oui, branche | Scope client explicite | Selon dataset/périmètre approuvé |
| Accepter, rejeter, contacter, créer un suivi | Oui, portefeuille | Seulement avec `actions:write:branch` | Non par défaut | Non |
| Visualiser les règles et seuils | Lecture | Lecture | Oui | Lecture |
| Modifier règles, seuils, activation | Non | Non | Oui | Non |
| Consulter les audits | Selon périmètre | Selon périmètre | Oui | Lecture |

Tester l’accès autorisé et le refus `401`, `403` ou `404` pour chaque combinaison. L’isolation par portefeuille et agence est obligatoire dès qu’un endpoint de périmètre est livré. Un utilisateur ne doit pas accéder à un client en devinant son identifiant ; le rôle `ADMIN` seul ne donne pas accès aux données client détaillées.

## 11. Tests interservices et adapters

Les tests interservices démarrent la Gateway et les services derrière elle. Ils vérifient le chemin transactionnel :

`Frontend/API Gateway → Opportunity Service → Signal Service → Analytics Service → Transaction Service → Banking Integration → Mock Banking APIs`.

Les scénarios couvrent :

- propagation d’un `correlationId` identique de bout en bout ;
- timeout, réponse 404, 409, 429 et 5xx d’un service dépendant ;
- retry borné et absence de duplication lors d’une répétition ;
- réponse dégradée lorsque le catalogue produit est indisponible ;
- circuit breaker ou mécanisme équivalent si prévu ;
- refus de payload incompatible ;
- séparation entre adapter et logique métier ;
- remplacement d’un MockCoreBankingAdapter par un faux adapter contractuellement équivalent ;
- absence de branchements `if mock` dans les règles métier ;
- conservation de l’erreur standardisée et du `correlationId` à la frontière Gateway.

Les Mock Banking APIs doivent être appelées par les adapters et non injectées directement dans le moteur. Un test d’architecture ou de revue statique doit détecter une dépendance interdite du frontend vers PostgreSQL ou une dépendance directe du moteur vers un client d’infrastructure.

## 12. Tests E2E Playwright

Les tests E2E utilisent un navigateur réel, une stack complète et un dataset réinitialisé. Les sélecteurs doivent privilégier des rôles et attributs stables, non le texte décoratif ou la structure CSS.

### 12.1 Smoke critique

Le scénario obligatoire est :

1. ouvrir l’application ;
2. se connecter avec un RM synthétique via Keycloak ;
3. afficher le dashboard et les opportunités du jour ;
4. ouvrir une opportunité connue du dataset ;
5. inspecter ses preuves et son explication ;
6. accepter l’opportunité ;
7. créer une action ;
8. marquer le client comme contacté ;
9. marquer l’opportunité comme convertie ;
10. vérifier le nouvel état, l’outcome et l’audit.

Le test vérifie que les valeurs visibles correspondent aux réponses backend, et non à une fixture locale. Il vérifie aussi les états de chargement, erreur, vide et pagination.

### 12.2 Parcours complémentaires

Tester la recherche par nom, identifiant, compte et secteur ; les filtres par type, confiance, priorité, secteur, segment, relationship manager, horizon et date ; le tri ; la navigation Customer 360 ; les graphiques d’encaissements, décaissements, solde, flux internationaux et utilisation des lignes ; la liste des signaux ; la page produit ; et la page d’administration selon le rôle.

Tester les refus d’accès par rôle, la persistance après rafraîchissement, le retour arrière, les réponses lentes et les erreurs API. Le parcours doit rester utilisable sur viewport desktop et sur une largeur responsive supportée. Les tests visuels peuvent détecter une régression de mise en page, mais ils ne remplacent pas les assertions de données.

## 13. Sécurité

### 13.1 Contrôles automatisés

La CI exécute lint et analyse statique, audit des dépendances, scan des images Docker, détection de secrets, validation des manifests, tests de headers et DAST sur un environnement isolé. Les seuils exacts sont configurés par l’équipe sécurité, avec au minimum zéro vulnérabilité critique et zéro secret détecté.

Les tests applicatifs couvrent :

- injection SQL, paramètres inattendus et validation de type ;
- contrôle d’accès horizontal et vertical ;
- falsification de `customerId`, `relationshipManagerId`, rôle ou score ;
- pagination extrême et limites de taille de payload ;
- rate limiting de la Gateway ;
- CORS, CSRF selon le mode d’authentification, cookies sécurisés et protection contre XSS ;
- divulgation d’erreurs, stack traces, secrets ou tokens dans les réponses et logs ;
- chiffrement en transit dans les environnements qui le prévoient ;
- rotation et absence de secrets dans le code, les images et l’historique Git ;
- redaction des données sensibles dans les logs ;
- audit des actions et des modifications de règles.

### 13.2 Confidentialité et minimisation

Un test de contrôle parcourt les fixtures, seeds, exports de logs et réponses API à la recherche de noms, comptes ou identifiants bancaires réels. Les données synthétiques doivent être plausibles sans être réutilisables comme données BOA. Aucun appel à une API LLM externe ne doit recevoir de données client.

## 14. Charge, performance et endurance raisonnables

La performance est mesurée sur un environnement connu, avec version de build, ressources CPU/mémoire et volume de données consignés. Les seuils doivent être ajustés après une première mesure, mais le MVP adopte les cibles initiales suivantes :

| Scénario | Charge de référence | Critère initial |
|---|---:|---|
| Health et readiness | 1–5 requêtes/s | 99 % sous 500 ms, aucune erreur |
| Liste paginée d’opportunités | 10 utilisateurs concurrents, page de 25 | p95 sous 1,5 s, erreur < 1 % |
| Recherche/filter clients | 10 utilisateurs concurrents | p95 sous 1,5 s, pas de requête non bornée |
| Détail Customer 360 | 5 utilisateurs concurrents | p95 sous 2 s, erreur < 1 % |
| Explication d’opportunité | 5 utilisateurs concurrents | p95 sous 2 s, erreur < 1 % |
| Génération sur dataset de démonstration | 500 PME, 12 mois | fin sans erreur ni doublon ; durée et ressources mesurées |
| Montée raisonnable | double de la charge de référence | pas de dégradation catastrophique ni perte de données |

Les tests doivent vérifier les plans de requête PostgreSQL, les index utilisés, la mémoire, les connexions, les temps des appels interservices et le nombre de transactions. Une page ne doit jamais charger la totalité des clients ou transactions. Le test de charge ne cherche pas à certifier une capacité de production finale ; il détecte les défauts évidents de pagination, N+1 queries, fuites de connexion, recalcul bloquant ou absence de cache pertinent.

Un test d’endurance de 30 à 60 minutes, planifié avant release, vérifie l’absence de croissance anormale de mémoire, de files d’attente, de connexions PostgreSQL ou d’erreurs intermittentes.

## 15. Observabilité et vérification des erreurs

Les logs sont structurés et contiennent au minimum timestamp, niveau, service, environnement, version, `correlationId`, trace ou span lorsqu’il est disponible, opération, statut et durée. Aucun secret, token ou donnée bancaire sensible ne doit apparaître en clair.

Les tests d’observabilité vérifient :

- `/health` reflète l’état du processus et `/ready` l’état des dépendances requises ;
- `/metrics` expose des compteurs et histogrammes utiles, sans labels à cardinalité incontrôlée ;
- les requêtes Gateway → Opportunity → Signal → Analytics sont corrélées ;
- les erreurs 4xx et 5xx sont différenciables ;
- les retries, timeouts et refus de rate limit sont comptés ;
- la génération d’opportunités et les actions sont mesurables ;
- une erreur utilisateur expose un `code`, un message sûr et un `correlationId` ;
- les logs permettent de retrouver une décision par `opportunityId`, `customerId` et version de règle ;
- les traces sont exportables selon l’interface OpenTelemetry prévue, même si l’exporteur final est différé.

Un test injecte une erreur à chaque dépendance principale et vérifie simultanément la réponse API, le log structuré, la métrique d’erreur et la trace. Un test de non-divulgation vérifie que la stack trace reste côté opérateur et ne revient pas au frontend.

## 16. Script d’auto-validation avant livraison

Un script d’orchestration doit exécuter automatiquement les étapes suivantes. Ce document définit son comportement ; il ne constitue pas son implémentation.

1. Vérifier les prérequis Docker, variables d’environnement, ports libres et absence de secrets en clair.
2. Démarrer l’environnement complet avec Docker Compose et attendre la readiness de PostgreSQL, Keycloak, Gateway et services.
3. Appliquer les migrations sur une base de test vide.
4. Exécuter le générateur de données avec le seed versionné.
5. Vérifier quantitativement 500 PME minimum, 12 mois d’historique, les secteurs et les scénarios attendus.
6. Authentifier un utilisateur de chaque rôle de test et conserver uniquement des tokens temporaires en mémoire.
7. Appeler les APIs principales avec le `correlationId` du run.
8. Exécuter les tests unitaires et publier le rapport de couverture.
9. Exécuter les tests de contrats OpenAPI et événements.
10. Exécuter les intégrations PostgreSQL et Keycloak.
11. Exécuter les tests interservices, erreurs, retries et adapters.
12. Exécuter le smoke E2E Playwright complet.
13. Vérifier le dashboard, la pagination, les filtres et Customer 360.
14. Recalculer les opportunités à partir des transactions et vérifier BR-001 à BR-012 ainsi que FP-001 à FP-007.
15. Appeler l’API d’explication et vérifier signaux, métriques, seuils, baseline, confiance, produit et horizon.
16. Exécuter le workflow acceptation → action → contact → conversion.
17. Vérifier les événements et les lignes d’audit, dont moteur, règle, timestamp, inputs, signaux et outcome.
18. Vérifier `/health`, `/ready`, `/metrics`, les logs structurés et la corrélation de trace.
19. Exécuter les scans sécurité bloquants et le test de rate limiting.
20. Produire un rapport horodaté regroupant versions, seed, résultats, artefacts, seuils et anomalies.
21. Détruire l’environnement de test dans un bloc de nettoyage, y compris en cas d’échec.

Le script doit s’arrêter au premier échec bloquant, retourner un code de sortie non nul et conserver les rapports, logs, traces et captures Playwright nécessaires au diagnostic. Il ne doit jamais ignorer un test en échec pour afficher artificiellement une validation réussie. Les étapes optionnelles doivent être explicitement marquées non bloquantes dans le rapport.

## 17. Critères de réussite et de sortie

La livraison est **acceptée** seulement si toutes les conditions suivantes sont vraies :

- toutes les migrations s’appliquent sur une base vide et le seed est reproductible ;
- le dataset contient au moins 500 PME, 12 mois de transactions cohérentes et les scénarios requis ;
- les tests unitaires, contrats, intégration PostgreSQL, Keycloak, interservices et smoke E2E sont verts ;
- les cas BR-001 à BR-004 produisent exactement le type, l’horizon et les preuves attendus ;
- les seuils, frontières, produits existants et combinaisons de règles sont couverts ;
- les cas FP-001 à FP-007 ne produisent pas de faux positifs non justifiés ;
- la saisonnalité et la persistance sont prises en compte et visibles dans l’explication ;
- la confiance et la priorité sont bornées, explicables, configurables et stables ;
- l’API d’explication est cohérente avec les signaux et métriques réellement persistés ;
- le parcours E2E login → dashboard → opportunité → preuves → acceptation → action → contact → conversion réussit ;
- chaque changement d’action et chaque décision du moteur sont audités ;
- les accès RBAC interdits retournent `401` ou `403` sans fuite d’information ;
- aucune vulnérabilité critique, aucun secret détecté et aucun token dans les logs ou réponses ;
- les cibles initiales de latence, d’erreur et de pagination sont respectées ;
- `/health`, `/ready` et `/metrics` fonctionnent et les appels critiques sont corrélés ;
- le rapport d’auto-validation est complet et sans étape obligatoire ignorée.

Un défaut critique inclut : décision métier incorrecte sur un cas obligatoire, faux positif compromettant l’interprétation commerciale, accès non autorisé, perte ou duplication de données, absence d’audit, fuite de secret, stack trace publique, impossibilité de démarrer la stack ou parcours E2E principal cassé. Un défaut critique bloque la release.

## 18. Gestion des résultats et traçabilité

Chaque test est identifié, possède un objectif, une donnée d’entrée, une précondition, une assertion et un niveau de blocage. Les rapports conservent le commit, la version des règles, la version du moteur, le seed, la configuration, l’environnement et le `correlationId` de l’exécution.

Les exigences sont traçables vers les familles de tests :

| Exigence | Couverture principale |
|---|---|
| Microservices et APIs | Contrats, interservices, E2E |
| PostgreSQL et données cohérentes | Intégration base, générateur, performance |
| Analytics et fenêtres historiques | Unitaires, métier, faux positifs |
| Signaux et cinq opportunités | Unitaires, BR-001 à BR-012, intégration et visibilité multibancarisée |
| Confiance, priorité, explication | Unitaires, contrats, E2E |
| Keycloak et RBAC | Intégration auth, sécurité, E2E par rôle |
| Actions, outcomes et feedback loop | Intégration, E2E, audit |
| Adapters remplaçables | Contrats, interservices, tests d’architecture |
| Observabilité | Logs, métriques, health, traces et injection d’erreur |
| Performance et pagination | Charge, intégration PostgreSQL, E2E |
| Privacy by Design | Scan de données, sécurité, revue des logs |
| Auto-validation et Definition of Done | Script d’orchestration et critères de sortie |

Toute anomalie doit indiquer la version du moteur et des règles, les données minimales pour la reproduire, les logs corrélés, la réponse API attendue et observée, ainsi que l’impact sur le métier. Les tests flaky sont isolés, diagnostiqués et corrigés ; ils ne sont pas simplement désactivés. Une nouvelle règle ou un nouveau produit exige l’ajout de tests positifs, négatifs, de frontière, de faux positifs et de contrat avant activation.

## 19. Références

Les exigences fonctionnelles et techniques de ce plan proviennent du fichier de requirements fourni pour BOA SME Opportunity Intelligence. Les pratiques d’outillage citées doivent être alignées avec les documentations officielles suivantes : [1] [2] [3] [4].

[1]: https://playwright.dev/docs/test-intro "Playwright Test documentation"
[2]: https://www.keycloak.org/documentation "Keycloak documentation"
[3]: https://www.postgresql.org/docs/ "PostgreSQL documentation"
[4]: https://opentelemetry.io/docs/ "OpenTelemetry documentation"

## 20. Décision finale

Le MVP ne peut être déclaré terminé que lorsque la démonstration finale suit le flux réel : **500 PME → 12 mois de transactions PostgreSQL → analytics → détection de signaux → moteur d’opportunités → priorisation → chargé d’affaires → explication → action → outcome**. Toute donnée affichée doit provenir des APIs et du backend, toute recommandation doit être recalculée par le moteur, et toute décision doit rester explicable et auditée.

## Contrôles de cohérence ajoutés

Les tests d’intégration doivent prouver les appels HTTP, la persistance outbox et l’idempotence sans supposer un broker. Les tests d’enums rejettent `ACCEPT` et `DISMISS` au profit de `ACCEPT_OPPORTUNITY` et `DISMISS_OPPORTUNITY`. Ils vérifient `confidence` dans `[0,1]`, `priorityScore` dans `[0,100]`, `opportunityStatus` côté moteur et `engagementStatus` côté actions.

## Références

[1]: ./implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ./api.md "Contrats API-first"
[3]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[4]: https://playwright.dev/docs/test-intro "Playwright Test documentation"
[5]: https://www.keycloak.org/documentation "Documentation Keycloak"
[6]: https://www.postgresql.org/docs/ "PostgreSQL documentation"


---

## 21. Extension du plan — Feature Store, ML et périmètres

Cette section couvre l’incrément cible sans rendre les tests ML obligatoires pour le MVP déterministe actuel. Dès qu’un composant ML est livré, la checklist dédiée devient normative [7].

### 21.1 Features et leakage

| ID | Scénario | Assertion bloquante |
|---|---|---|
| ML-FEAT-001 | même source, `asOf`, feature set et watermark | snapshot équivalent et idempotent |
| ML-FEAT-002 | événement/outcome postérieur à `asOf` | absent du snapshot et de l’export |
| ML-FEAT-003 | transformation offline et serving | valeurs normalisées identiques |
| ML-FEAT-004 | feature obligatoire absente/stale | snapshot invalide ; aucune valeur cachée |
| ML-FEAT-005 | catégorie inconnue ou hors borne | qualité et réaction conformes au registre |
| ML-FEAT-006 | changement fenêtre/unité/imputation | nouvelle version ; historique reconstructible |
| ML-FEAT-007 | feature exclusivement crédit/défaut | activation refusée |

Tout test sur outcomes réels exige finalité, manifeste, pseudonymisation, cutoff et consentement ou base approuvée. `OBSERVED`, `SIMULATED` et `NOT_REPORTED` sont testés séparément. L’absence d’outcome n’est pas un label négatif.

### 21.2 Model Registry, score et CPU

Les tests valident checksum, self-test, compatibilité, transitions de stage, séparation auteur/approbateur, unicité du champion et rollback. La performance est mesurée sur Linux amd64 sans GPU et sans Internet, pour 500 PME, avec CPU, RAM, threads, durée, débit, p50/p95, erreurs et taille d’artefact consignés.

| ID | Scénario | Résultat attendu |
|---|---|---|
| ML-SCORE-001 | même modèle, snapshot et configuration | score/explication identiques |
| ML-SCORE-002 | hors `[0,1]`, NaN ou infini | prédiction invalide |
| ML-SCORE-003 | cible, horizon ou version absents | contrat refusé |
| ML-SCORE-004 | score expiré | exclusion et fallback audités |
| ML-FUS-001 | shadow vs règles | mêmes sorties opérationnelles |
| ML-FUS-002 | rerank | seules candidates règles réordonnées |
| ML-FUS-003 | poids invalides | politique refusée |
| ML-FUS-004 | panne, drift ou incompatibilité | règles seules ou lot suspendu ; aucun score inventé |
| ML-FUS-005 | politique modifiée | historique intact, nouvelle version auditée |
| ML-FUS-006 | candidate ML au MVP initial | activation refusée |

### 21.3 Monitoring, drift et scope

Les tests injectent staleness, nulls, catégorie inconnue, déplacement de feature et de score. Ils vérifient population de référence, méthode, seuils, statut, alerte et fallback. Un drift bloquant ne déclenche jamais auto-entraînement ou auto-promotion. La performance différée attend la maturité de l’horizon ; `customerId` est interdit comme label Prometheus.

| ID | Sujet et ressource | Résultat attendu |
|---|---|---|
| SCOPE-001 | CC sur client affecté | `200`, périmètre actif uniquement |
| SCOPE-002 | CC sur autre portefeuille | `404`, aucune fuite |
| SCOPE-003 | responsable sur sa branche | agrégats et drill-down autorisés |
| SCOPE-004 | responsable sur autre branche | `404` |
| SCOPE-005 | responsable sans scope action branche | lecture oui, écriture `403` |
| SCOPE-006 | admin ML sans scope client | aucun détail PME |
| SCOPE-007 | réaffectation | droits transférés, historique inchangé |
| SCOPE-008 | projection stale | refus, jamais accès global |
| SCOPE-009 | total et liste | même périmètre serveur |

### 21.4 Explicabilité et interdictions

Chaque prédiction expose baseline, contributeurs, valeurs absentes/imputées, méthode et versions. La fusion est reconstruite depuis les références persistées. Les contributions sont associatives, non causales.

Une recherche automatisée sur OpenAPI, JSON, schémas, UI, logs et exports refuse tout champ de score/décision de crédit. Un scénario `FINANCIAL_STRESS_SIGNAL` prouve l’absence d’octroi, refus, prix, limite ou montant. Build, SBOM, variables, trafic sortant et traces doivent montrer **zéro appel ou dépendance LLM**.

`ML_SHADOW` exige tous les contrôles architecture, features, registry, score, sécurité, scope, audit, monitoring, CPU et absence LLM/crédit. `HYBRID_RERANK` exige en plus période shadow, outcomes matures, revue par segment, simulation et rollback. Sont exclus : streaming, GPU, online learning, auto-réentraînement, auto-promotion, causalité, texte libre, LLM et candidate ML opérationnelle.

## Références de l’extension

[7]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[8]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[9]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
