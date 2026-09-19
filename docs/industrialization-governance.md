# Gouvernance d’industrialisation et audit d’accès aux données

> **Lecture recommandée.** Ce document conserve l’audit d’écarts et la cible cloud-agnostique. Depuis sa rédaction, le fallback `RULES_ONLY`, la Scoring Policy, le registre MLOps, la lignée, le monitoring persistant et Alembic `0006` à `0008` ont été intégrés. La décision actuelle et les preuves exécutées figurent dans [`finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md). Les réserves DPO, SQL transverse, HA, backup, secrets et adapters réels restent applicables.

**Périmètre audité.** Ce document décrit l’état observé dans le dépôt `boa-sme-opportunity-intelligence` au moment de l’audit. Il ne constitue ni une homologation de sécurité, ni une décision d’architecture BOA. Toute durée de conservation, tout niveau de service et toute règle d’accès proposés ici sont **À valider par les fonctions compétentes BOA** : Architecture, Sécurité, Risques, Juridique/Protection des données, Production, Data/IA, Métiers et propriétaires des systèmes sources.

Le dépôt montre une architecture de services FastAPI avec PostgreSQL, SQLAlchemy/Alembic, Keycloak et un adaptateur bancaire HTTP. Le mode local est assemblé par Docker Compose. Il ne fournit pas la preuve d’un déploiement cloud, d’une instance PostgreSQL hautement disponible, d’un plan de reprise testé ou d’un service managé particulier. Les recommandations ci-dessous sont donc **cloud-agnostiques** et ne revendiquent aucun déploiement AWS.

## 1. Conclusion de l’audit

La séparation par schéma et par rôle PostgreSQL est une bonne direction, mais elle n’est pas encore une frontière de sécurité démontrée. Le bootstrap donne à chaque rôle propriétaire de son schéma et lui accorde `CREATE`; les services peuvent donc modifier leur propre structure. Plusieurs flux applicatifs lisent des données d’un autre domaine, alors que le Compose ne montre pas les `GRANT SELECT` correspondants. Le service de portefeuille lit notamment `customer`, `ml`, `opportunity` et `action`, tandis que son URL utilise le schéma `portfolio`, qui ne contient pas de tables métier dans les migrations observées. Cette situation doit être traitée avant une mise en production.

Le dépôt contient une base SQL réelle et des écritures idempotentes pour plusieurs flux. Il contient également un mock bancaire exposant des faits synthétiques et trois adaptateurs mémoire remplaçables. En revanche, les noms `MockCBS`, `MockCRM`, `MockPayment` et `MockTrade` ne correspondent pas à quatre classes distinctes présentes dans le code : `InMemoryCoreBankingAdapter`, `InMemoryPaymentAdapter`, `InMemoryProductAdapter` et l’API `mock-banking` couvrent actuellement ces usages. Les contrats de remplacement doivent être figés avant tout raccordement aux systèmes BOA.

Les priorités de durcissement sont les suivantes :

1. publier une matrice de privilèges effective, testée avec des comptes non propriétaires ;
2. corriger la cohérence entre rôles, `search_path`, schémas et tables réellement lues ;
3. retirer `CREATE` aux comptes d’exécution et réserver les migrations à un compte de déploiement séparé ;
4. tracer chaque import, calcul, décision, action et appel inter-service avec un identifiant de corrélation ;
5. définir et faire valider les finalités, durées de conservation, droits d’accès et règles de minimisation ;
6. établir une cible PostgreSQL HA, sauvegarde-restauration, rotation des secrets, TLS et reprise après sinistre avec des RPO/RTO approuvés.

## 2. Périmètre et constatations vérifiables

L’application expose des services distincts dans `backend/src/boa_oi/api.py`. Les domaines persistés sont `customer`, `account`, `transaction`, `product`, `analytics`, `signal`, `opportunity`, `action`, `audit`, `config`, `integration`, `rule`, `feature_store` et `ml`. Les migrations `0001_initial.py` à `0005_ml_integration_trace.py` créent une partie de ces objets, tandis que `models/entities.py` constitue le catalogue ORM.

Les connexions sont construites par `technical/database.py` avec SQLAlchemy et une session transactionnelle qui valide ou annule la transaction à la fin du contexte. Les APIs utilisent des requêtes SQLAlchemy `select`, des agrégations SQL et des écritures ORM ou PostgreSQL `ON CONFLICT`. Le service transaction calcule directement les séries d’activité par `date_trunc` et `sum`; ce n’est pas un écran alimenté par des données locales. Les services d’intégration appellent aussi des endpoints HTTP avant d’écrire les reçus et données importées.

Les signaux, opportunités, règles, simulations, scores de propension et actions disposent de modèles persistants et de champs de version ou de corrélation. Il faut toutefois distinguer la **présence d’un champ d’audit** d’une garantie opérationnelle : la rétention, l’immutabilité, l’export vers un journal central, la surveillance et les tests de restauration ne sont pas démontrés par le dépôt.

## 3. Inventaire des accès SQL restants

### 3.1 Légende de la matrice

`R` signifie lecture SQL. `W` signifie insertion ou mise à jour SQL. `RW` signifie les deux. `—` signifie qu’aucun accès SQL métier n’a été observé pour ce service. « Alternative API » désigne l’interface à privilégier si le service ne doit plus accéder directement au schéma d’un autre domaine. Les durées de conservation indiquées dans la colonne de gouvernance sont des **propositions à valider** et non des exigences BOA arrêtées.

### 3.2 Accès par service, schéma et table

| Service / rôle observé | Schéma et table(s) | Accès | Raison observée dans le code | Justification de l’accès direct | Alternative API à privilégier |
|---|---|---:|---|---|---|
| `customer-service` / `customer_service` | `customer.relationship_managers`, `customer.customers`, `customer.sectors` | RW | Recherche de portefeuille, fiches PME, rattachement RM et imports clients | Propriétaire fonctionnel du référentiel client et de l’habilitation RM | Aucun pour le propre domaine ; exposer `/internal/v1/customers` et `/internal/v1/relationship-managers` aux consommateurs |
| `customer-service` / `customer_service` | `customer.import_receipts` | RW | Idempotence et preuve des imports clients | Nécessaire pour rejouer sans doublon et relier batch, hash et corrélation | Endpoint d’import client avec `Idempotency-Key`; le reçu reste interne au service |
| `account-service` / `account_service` | `account.accounts`, `account.credit_lines`, `account.account_balances` | RW | Comptes, lignes de crédit, soldes et import des données de compte | Propriétaire du domaine compte | API comptes/soldes versionnée ; agrégats anonymisés pour l’analytique |
| `account-service` / `account_service` | `account.import_receipts` | RW | Idempotence des imports de comptes | Preuve technique du batch entrant | Endpoint interne d’import compte |
| `transaction-service` / `transaction_service` | `transaction.transactions` | RW | Recherche filtrée, détail transaction et agrégation d’activité | Propriétaire du domaine transaction ; l’agrégation SQL évite de charger toutes les lignes dans l’API | `/internal/v1/transactions` et endpoint d’agrégats matérialisés ; aucun accès aux transactions brutes hors service |
| `transaction-service` / `transaction_service` | `transaction.import_receipts` | RW | Déduplication par clé d’idempotence, hash de requête et statut | Nécessaire pour les imports rejouables | Endpoint d’import transaction avec contrat de batch |
| `product-service` / `product_service` | `product.products`, `product.customer_products` | RW | Catalogue de produits, détention et gaps d’équipement | Propriétaire du catalogue et de la relation produit-client | `/internal/v1/products` et `/internal/v1/customers/{id}/products` |
| `product-service` / `product_service` | `product.import_receipts` | RW | Idempotence des imports produit | Rejeu contrôlé d’un lot | Endpoint d’import produit |
| `analytics-service` / `analytics_service` | `analytics.metric_definitions`, `analytics.metric_values`, `analytics.metric_snapshots` | RW | Définitions de métriques, valeurs et instantanés consommés par signaux/règles | Propriétaire des métriques pré-calculées ; évite la lecture de transactions par chaque règle | `/internal/v1/metrics`, snapshots versionnés et exports batch signés |
| `analytics-service` / `analytics_service` | `transaction.transactions`, `account.accounts` | R requis par les calculs observés | Construction de métriques et séries à partir des faits sources | Cet accès inter-domaine est le principal reliquat à réduire ; il ne doit pas devenir un droit SQL large | Événement d’import ou API d’agrégats du transaction/account service ; compte de réplication ou vue dédiée en transition |
| `signal-service` / `signal_service` | `signal.signal_rules`, `signal.signals` | RW | Règles de signal et production de signaux clients | Propriétaire du domaine signal | `/internal/v1/signals` et publication d’événements de signal |
| `signal-service` / `signal_service` | `analytics.metric_snapshots` | R | Évaluation des signaux sur métriques pré-calculées | Lecture ciblée de snapshots, préférable à la transaction brute | API métriques versionnée ou vue `analytics.signal_inputs` en lecture seule |
| `opportunity-service` / `opportunity_service` | `opportunity.opportunity_rules`, `opportunity.opportunities`, `opportunity.opportunity_evidence`, `opportunity.opportunity_recommendations`, `opportunity.decision_audit` | RW | Évaluation, explication, preuves, recommandations et traçabilité de décision | Propriétaire des décisions commerciales assistées et de leur justification | Aucun pour son propre domaine ; publier une API de décision et un flux d’audit |
| `opportunity-service` / `opportunity_service` | `signal.signals`, `analytics.metric_snapshots`, `customer.customers`, `product.products` | R requis par les assemblages observés | Construire le contexte d’opportunité et les explications | Accès direct temporaire pour latence et cohérence ; il contourne la propriété de domaine | APIs internes de signal, métriques, client et produit ; cache versionné avec `as_of` et `source_version` |
| `action-service` / `action_service` | `action.opportunity_actions`, `action.action_outcomes` | RW | Création d’action, mise à jour d’état, idempotence, résultat et corrélation | Propriétaire du cycle d’action | API action publique/interne ; l’opportunity-service ne doit jamais écrire la table |
| `action-service` / `action_service` | `opportunity.opportunities`, `customer.customers` | R requis par les contrôles et affichages observés | Vérifier l’opportunité et le périmètre client avant d’ouvrir ou modifier une action | Lecture nécessaire mais à limiter aux colonnes et identifiants utiles | API de lecture d’opportunité et de périmètre ; token de service à portée minimale |
| `rule-management-service` / `rule_management_service` | `rule.rules`, `rule.rule_versions`, `rule.rule_conditions`, `rule.rule_actions`, `rule.rule_confidence_configurations`, `rule.rule_approvals`, `rule.rule_simulations`, `rule.rule_audit_logs` | RW | Création, validation, soumission, approbation, publication, rollback, simulation et audit | Propriétaire du référentiel de règles et de leur cycle de vie | Aucun pour les écritures ; API Rule Studio et événements de publication pour les lecteurs |
| `rule-engine-service` / rôle actuellement partagé `rule_management_service` | `rule.rules`, `rule.rule_versions`, conditions, actions et configurations de confiance | R, avec verrouillage observé dans des chemins partagés | Charger la version active et évaluer les règles | Le moteur devrait être un lecteur de version publiée, pas un écrivain du schéma | API `/internal/v1/rules/active` ou snapshot immuable signé ; rôle dédié `rule_engine_reader` |
| `rule-simulation-service` / rôle actuellement partagé `rule_management_service` | `rule.rule_versions`, `rule.rule_conditions`, `rule.rule_actions`, `rule.rule_simulations` | R/W | Simuler une version et enregistrer le résultat | Lecture de la version, écriture de sa propre simulation | API de version publiée ; écriture via un endpoint de simulation appartenant au service simulation |
| `feature-store-service` / `feature_store_service` | `feature_store.feature_materializations` | RW | Matérialiser les features avec date d’observation, sources et checksum | Propriétaire de la représentation calculée, indispensable pour le point-in-time | API `/internal/v1/features` ou fichiers batch chiffrés avec manifeste |
| `ml-engine-service` / `ml_engine_service` | `ml.model_registry`, `ml.propensity_scores`, `ml.outcome_label_snapshots` | RW | Charger le modèle actif, calculer/écrire les scores et gérer les labels disponibles | Propriétaire du cycle de score et de la traçabilité modèle/feature | API de scoring et registre de modèles ; publication d’un score versionné vers opportunity/portfolio |
| `ml-engine-service` / `ml_engine_service` | `feature_store.feature_materializations` | R requis | Lire les features d’une date de référence pour un score reproductible | Accès direct temporaire à une entrée calculée, sans transaction brute | API `features/{customer}/{as_of}` ou partage de snapshot immuable |
| `portfolio-service` / `portfolio_service` | `customer.customers`, `customer.relationship_managers` | R requis par `_scoped_customers` | Construire les portefeuilles RM/agence et appliquer le filtrage d’habilitation | Lecture de référence nécessaire pour la réponse de portefeuille ; le rôle isolé n’en reçoit pas les droits dans le bootstrap observé | API portfolio du customer service ou projection dédiée `portfolio.customer_scope` |
| `portfolio-service` / `portfolio_service` | `ml.propensity_scores`, `opportunity.opportunities`, `action.opportunity_actions` | R requis par les fonctions de scores, opportunités et actions | Agréger la vue portefeuille | Lecture multi-domaine ; elle doit devenir une projection ou des API internes | `portfolio.customer360` alimenté par événements versionnés, ou APIs batch par domaine |
| `banking-integration-service` / `integration_service` | `integration.import_batches`, `integration.outbox_messages` | RW prévu par les modèles ; `import_batches` écrit dans le flux observé | Suivre l’import externe, sa taille, son hash, son statut et les messages à publier | Propriétaire de l’orchestration et de l’outbox | API d’import idempotent ; les services cibles reçoivent les lots, jamais les tables d’un autre service |
| `api-gateway` | Aucun accès SQL métier observé | — | Routage, auth, corrélation, agrégation HTTP | Le gateway ne doit pas devenir un compte de données | APIs internes des services, sans URL SQL ni `DATABASE_URL` |
| `mock-banking-api` | Aucun accès SQL métier ; données synthétiques calculées en mémoire | — | Fournir des faits de test sans décision ni opportunité | Permettre les tests et démos sans prétendre simuler un système BOA réel | Remplacer l’URL par un connecteur CBS/CRM/paiement/trade homologué |

Cette matrice est une **cible d’industrialisation**, pas une preuve que tous les privilèges ci-dessus existent ou sont correctement accordés aujourd’hui. La preuve attendue est une batterie de tests SQL exécutée avec chaque rôle : lecture autorisée, lecture refusée, écriture autorisée, écriture refusée, accès à une colonne sensible refusé et migration refusée avec le compte d’exécution.

### 3.3 Écarts de configuration à corriger

Le script `infrastructure/postgres/00-init-service-schemas.sh` crée `rule_management_service` avec le schéma `rule_management`, alors que Compose fournit `search_path=rule` et que les modèles utilisent `rule`. Il accorde en outre `USAGE, CREATE` au rôle propriétaire de chaque schéma. Le compte d’exécution ne devrait pas être propriétaire en production.

Le service de portefeuille utilise `search_path=portfolio`, mais les modèles `portfolio_api.py` interrogent principalement les tables de `customer`, `ml`, `opportunity` et `action`; aucune table métier `portfolio` n’est créée par les migrations lues. La cible doit choisir explicitement entre une projection `portfolio` et des API inter-services. Elle ne doit pas dépendre d’un privilège implicite du superutilisateur.

Les services Rule Studio, Rule Engine et Rule Simulation partagent actuellement le rôle `rule_management_service`. Cette pratique empêche la séparation des tâches : un moteur de lecture pourrait écrire ou supprimer une règle si son code ou sa connexion était compromis. Créer des rôles distincts `rule_management_rw`, `rule_engine_ro` et `rule_simulation_rw` est recommandé.

Les migrations créent les schémas métier initiaux, mais l’initialisation Docker et les migrations ne portent pas exactement la même liste. Les schémas `rule`, `feature_store`, `ml` et `portfolio` doivent être créés par une migration versionnée ou par un bootstrap explicitement cohérent avec les URLs de connexion. Toute correction doit être testée sur une base vide et une base existante.

## 4. Adapters et contrats de remplacement

### 4.1 État actuel et nomenclature cible

Le dépôt définit dans `backend/src/boa_oi/adapters/ports.py` trois ports synchrones : `CoreBankingPort`, `PaymentPort` et `ProductPort`. Les implémentations de test sont `InMemoryCoreBankingAdapter`, `InMemoryPaymentAdapter` et `InMemoryProductAdapter`. `HttpBankingAdapter` consomme aujourd’hui l’API `mock-banking` et convertit les réponses vers les types canoniques client, compte et transaction.

Pour l’industrialisation, les noms fonctionnels suivants sont retenus afin de rendre la substitution explicite :

| Adapter logique | Implémentation actuelle | Système cible à raccorder | Finalité autorisée |
|---|---|---|---|
| `MockCBS` | `InMemoryCoreBankingAdapter` et endpoints clients/comptes/soldes du `mock-banking-api` | CBS ou service comptes/client BOA | Référentiel client, compte, solde et rattachement ; jamais de score ou d’opportunité |
| `MockCRM` | Pas de classe dédiée dans le dépôt ; données client/RM synthétiques et API customer | CRM BOA ou référentiel relationnel | Identité PME, RM, agence, statut de relation et événements de contact |
| `MockPayment` | `InMemoryPaymentAdapter` et endpoint transactions du mock | Service paiements/transactions BOA | Mouvements normalisés sur une période, avec devise, sens, catégorie et indicateur international |
| `MockTrade` | Pas de classe dédiée ; `InMemoryProductAdapter` couvre le statut produit, tandis que l’API mock expose trade-finance ownership | Service trade finance/produits BOA | Statut de détention, utilisation ou éligibilité produit ; jamais une décision de crédit |

L’absence de classes dédiées `MockCRM` et `MockTrade` doit être assumée dans la documentation et les tests. Il ne faut pas présenter ces noms comme des composants déjà livrés.

### 4.2 Contrat canonique minimal

Les implémentations réelles doivent préserver les invariants des ports actuels et ajouter les métadonnées d’exploitation suivantes :

```text
CoreBankingPort
  fetch_customers(scope, as_of, correlation_id) -> Sequence[CanonicalCustomer]
  fetch_accounts(customer_refs, as_of, correlation_id) -> Sequence[CanonicalAccount]
  fetch_balances(account_refs, as_of, correlation_id) -> Sequence[CanonicalBalance]

Customer/CRMPort
  fetch_relationship(customer_refs, as_of, correlation_id) -> Sequence[CanonicalRelationship]
  fetch_rm_scope(actor_subject_id, correlation_id) -> CanonicalScope

PaymentPort
  fetch_transactions(account_refs, from_date, to_date, as_of, correlation_id)
    -> Sequence[CanonicalTransaction]

Trade/ProductPort
  fetch_product_status(customer_refs, product_codes, as_of, correlation_id)
    -> Sequence[CanonicalProductStatus]
```

Chaque réponse doit contenir ou être accompagnée de `source_system`, `source_record_id`, `observed_at`, `as_of`, `schema_version`, `correlation_id`, `request_id`, `data_quality_status` et d’un indicateur de pagination ou de complétude. Les identifiants externes doivent rester séparés des identifiants internes. Les montants doivent utiliser une représentation décimale et une devise explicite. Les dates métier ne doivent pas être remplacées par l’heure d’ingestion.

Le contrat de remplacement doit imposer : timeout borné, retries limités avec backoff, circuit breaker, idempotence des imports, pagination, filtrage par périmètre, contrôle de fraîcheur, gestion explicite de l’absence de donnée et distinction entre `UNKNOWN`, `ABSENT` et `ERROR`. Une réponse partielle ne doit pas être transformée silencieusement en absence d’opportunité.

### 4.3 Règles de substitution

Le connecteur réel doit être injectable par configuration, mais le choix d’un adaptateur ne doit pas être décidé par une requête ou un rôle utilisateur. La chaîne recommandée est : adaptateur externe, validation du contrat, normalisation canonique, journal d’import, écriture du service propriétaire, puis publication d’un événement ou snapshot versionné. Aucun adaptateur externe ne doit appeler directement les tables `opportunity`, `rule` ou `ml`.

Pour chaque système réel, BOA doit approuver la correspondance de champs, la qualité, les codes d’erreur, le chiffrement en transit, la localisation des données, le mode de support et le plan de repli. Les données synthétiques du mock ne peuvent servir qu’aux tests, démonstrations et tests de contrat ; elles ne prouvent ni la qualité ni la disponibilité du système source.

## 5. Données, finalité, conservation, accès et traçabilité

Les finalités ci-dessous sont proposées pour cadrer le produit. Elles doivent être revues par les fonctions compétentes BOA avant collecte ou mise en production.

| Catégorie | Données minimales et finalité | Conservation proposée | Accès | Traçabilité et minimisation |
|---|---|---|---|---|
| Référentiel PME | Référence client, nom légal, secteur, segment, statut, RM/agence. Finalité : servir une PME et filtrer son portefeuille. | Référentiel actif pendant la relation, puis durée légale BOA à définir ; purge ou archivage après clôture. **À valider.** | Customer service ; lecture de champs minimaux par portfolio, opportunity et action. | Ne pas recopier adresse, contacts ou documents non nécessaires dans les snapshots ; journaliser sujet, périmètre, motif et corrélation. |
| Comptes et soldes | Référence compte, type, devise, solde à une date, limite et utilisation. Finalité : calcul d’indicateurs commerciaux et de service, pas décision automatisée de crédit. | Fenêtre analytique minimale à définir, par exemple 24 mois, puis agrégats sans détail. **À valider.** | Account service ; analytics en lecture contrôlée ; autres services via agrégats. | Masquer les numéros complets ; préférer identifiants techniques et agrégats ; journaliser l’usage de champs sensibles. |
| Transactions et paiements | Référence, date de valeur, sens, montant, devise, catégorie, indicateur international. Finalité : tendances et signaux commerciaux autorisés. | Détail selon obligation légale et besoin prouvé ; agrégats conservés plus longtemps seulement si nécessaires. **À valider.** | Transaction service ; analytics pendant migration ; aucun accès direct du front. | Filtrer par client/date ; ne jamais exporter la ligne complète dans une explication ; chiffrer au repos et en transit ; corrélation d’import. |
| Produits, trade et détention | Code produit, statut, date d’observation et identifiant client. Finalité : identifier une couverture ou une sous-utilisation produit. | Historique de statut limité à la période nécessaire au suivi ; durée BOA à définir. **À valider.** | Product/trade service ; opportunity en lecture de statut normalisé. | Ne pas collecter les pièces trade ni conditions contractuelles dans l’intelligence commerciale sans finalité approuvée. |
| Métriques et signaux | Code de métrique, valeur agrégée, période, fraîcheur, source et version. Finalité : explicabilité et règles commerciales. | Versions nécessaires à la reproductibilité d’une décision, puis agrégats purgés selon la politique analytique. **À valider.** | Analytics et signal ; opportunity/rule engine via API ou vue dédiée. | Conserver `as_of`, checksum, source et version ; éviter de réintroduire les transactions brutes. |
| Opportunités et explications | Type, statut, scores de confiance/priorité, preuves, recommandations, moteur et version de règle. Finalité : assister le RM et expliquer une suggestion. | Tant que l’opportunité ou son litige est ouvert, puis durée de preuve approuvée. **À valider.** | RM sur son périmètre ; managers selon agence ; audit et risques selon besoin. | Vocabulaire relationnel, pas décision de crédit ; hash de décision ; explication limitée aux facteurs nécessaires. |
| Actions et résultats | Type d’action, acteur, statut, dates, notes expurgées, résultat, corrélation. Finalité : suivi de contact et mesure de valeur. | Durée du suivi et obligations de preuve à définir. **À valider.** | RM propriétaire, manager de périmètre, contrôle habilité. | `notes_redacted` est une intention et non une preuve de caviardage ; mettre en place détection de secrets et données sensibles. |
| Règles et approbations | Configuration versionnée, conditions, approbations, simulations, audit de changement. Finalité : gouvernance et reproductibilité. | Historique immuable aussi longtemps qu’une décision s’y réfère, puis archivage approuvé. **À valider.** | Rule authors, approvers, audit ; moteur en lecture seule. | Séparation des tâches, checksum, auteur, date, ancienne/nouvelle valeur et justification. |
| Features, modèles et scores | Features matérialisées, sources, checksum, modèle, métriques de validation, score et facteurs contributifs. Finalité : scoring assistif et contrôle de reproductibilité. | Modèle et score selon cycle de vie IA ; labels après validation de la finalité. **À valider.** | ML/data habilités ; portfolio et opportunity via score versionné ; pas de secret d’entraînement exposé au front. | Point-in-time obligatoire, version modèle/feature, minimisation des contributions et limitation des exports individuels. |
| Logs, imports et outbox | Identifiant de corrélation, sujet, service, action, statut, hash, nombre de lignes, erreurs techniques. Finalité : exploitation et audit. | Journal technique séparé, durée et immutabilité à définir avec Sécurité/Risques. **À valider.** | Exploitation, sécurité, audit sur besoin d’en connaître. | Ne jamais écrire mot de passe, token, payload complet ou montant inutile dans les logs ; hachage et pseudonymisation. |

L’accès applicatif doit être fondé sur le rôle métier, le périmètre agence/RM et la finalité. Keycloak fournit l’authentification dans la pile observée, mais la décision d’autorisation doit être vérifiée côté service. Le gateway ne doit pas être considéré comme une frontière suffisante : chaque service doit vérifier le token, l’audience, le rôle, la portée et le périmètre de la ressource.

Les données doivent être classées au minimum en : données d’identification relationnelle, données financières détaillées, données dérivées/agrégées, configuration et audit technique. La classification BOA, les pays de traitement, les transferts, la base légale et les droits des personnes restent à documenter et **À valider par les fonctions compétentes BOA**.

## 6. Architecture cible cloud-agnostique

La cible conserve une séparation claire entre l’interface, le gateway, les services de domaine, les adaptateurs externes, PostgreSQL HA, le stockage de sauvegarde et l’observabilité. Elle peut être déployée sur un cloud, un datacenter ou une plateforme hybride conforme aux contrôles BOA ; aucun fournisseur n’est imposé par ce document.

Le gateway est le seul point d’exposition externe. Les services communiquent par API internes authentifiées et, pour les flux asynchrones, par un bus ou une file managée par la plateforme retenue. Les données restent dans le service propriétaire. Les projections nécessaires au portefeuille et au dashboard sont alimentées par événements versionnés ou par des snapshots batch ; elles ne sont pas obtenues par des droits SQL croisés illimités.

PostgreSQL doit être une cible **HA** composée d’au moins deux instances selon la capacité et le mécanisme de consensus retenus par la plateforme. La connexion applicative doit utiliser un endpoint de lecture/écriture stable ou un proxy compatible avec les bascules. Les services doivent gérer les erreurs de failover, les transactions rejouables et les imports idempotents. La haute disponibilité n’est pas acquise par la seule présence d’un conteneur PostgreSQL local.

Les migrations doivent être exécutées par un compte de déploiement séparé, dans une étape contrôlée. Les comptes de runtime doivent recevoir uniquement `CONNECT`, `USAGE` et les privilèges `SELECT/INSERT/UPDATE` strictement nécessaires sur des tables ou vues ciblées. `CREATE`, `ALTER`, `DROP`, `TRUNCATE` et la propriété des schémas doivent être retirés aux comptes de runtime. Les vues de lecture inter-domaines doivent exposer uniquement les colonnes minimales et être versionnées.

## 7. Sauvegarde, restauration et reprise après sinistre

La cible doit combiner sauvegardes complètes périodiques, sauvegardes incrémentales ou journaux de transactions, réplication vers un site ou domaine de panne distinct et stockage chiffré avec verrouillage contre l’effacement anticipé. Les sauvegardes doivent être testées par restauration, pas seulement déclarées comme réussies.

La séquence minimale de restauration est : déclarer l’incident, isoler l’écriture, sélectionner le dernier point cohérent, restaurer PostgreSQL, appliquer les migrations compatibles, restaurer les secrets et certificats depuis leurs sources contrôlées, redémarrer les services dans l’ordre des dépendances, rejouer les outbox/imports idempotents, contrôler les compteurs et hashes, puis autoriser le trafic. Les imports et décisions doivent porter une version de données afin de détecter une restauration partielle.

Les valeurs RPO/RTO ne sont pas fournies par le dépôt. Elles doivent être définies par les propriétaires BOA après analyse d’impact. À titre de gabarit de décision, une cible initiale peut distinguer :

| Classe de service | RPO proposé | RTO proposé | Validation requise |
|---|---:|---:|---|
| Consultation RM, opportunités et actions | 15 minutes | 60 minutes | À valider par Métiers, Production et Risques |
| Import transactionnel et calculs | 60 minutes | 4 heures | À valider par Data/IA et Production |
| Rule Studio et registre de modèles | 24 heures si les versions sont archivées | 8 heures | À valider par Sécurité, Data/IA et Métier |
| Audit et preuves de décision | Au plus 15 minutes, éventuellement inférieur selon obligation | 4 heures | À valider par Risques, Juridique et Audit |

Ces chiffres sont des options de cadrage et ne doivent pas être annoncés comme des engagements. Chaque cible doit être testée par un exercice de restauration trimestriel ou selon la politique BOA approuvée, avec mesure réelle du RPO/RTO.

## 8. Secrets, TLS et sécurité opérationnelle

Les valeurs `DevOnly-*` présentes dans `.env.example` et les secrets par défaut du Compose sont acceptables uniquement pour le développement local. Ils ne doivent pas être propagés vers un environnement partagé. Les secrets de base de données, OIDC, comptes techniques, certificats et clés de chiffrement doivent être stockés dans un coffre de secrets ou un mécanisme équivalent approuvé par BOA.

La rotation doit couvrir les mots de passe PostgreSQL, secrets de clients OIDC, clés de signature et certificats. Elle doit être sans interruption lorsque possible : créer un nouveau secret, le distribuer, basculer les consommateurs, vérifier les métriques, révoquer l’ancien puis conserver une preuve de rotation. La fréquence et la procédure d’urgence sont **À valider par Sécurité BOA**. Aucun secret ne doit apparaître dans le code, les logs, les images ou les sauvegardes non chiffrées.

TLS doit protéger le trafic navigateur-gateway, gateway-services et services-PostgreSQL dans les environnements non locaux. La validation doit imposer une autorité approuvée, la vérification de nom, des versions et suites cryptographiques conformes à la politique BOA, ainsi que la rotation des certificats. Le HTTP local visible dans Compose n’est pas une preuve de la configuration de production.

Les contrôles complémentaires attendus sont : limitation de débit au gateway, validation des tailles de payload, timeouts sortants, journalisation sans données sensibles, analyse de dépendances, scan d’image, gestion des vulnérabilités, tests d’autorisation par rôle et par périmètre, tests de régression de migration et tests de confidentialité des explications.

## 9. Limites connues de l’audit et du produit

Cet audit est statique et limité au contenu du dépôt accessible. Il ne prouve pas les privilèges effectivement présents dans une base, la configuration effective de Keycloak, la sécurité du réseau, la qualité des données BOA, la performance à grande échelle, la résilience d’une infrastructure réelle ou le respect d’une obligation réglementaire.

Le Compose fournit un PostgreSQL unique et local, des secrets de développement et des dépendances simulées. Il ne constitue pas une architecture HA. Aucun runbook de restauration réellement exécuté, rapport de test DR, certificat de production, coffre de secrets ou matrice de privilèges effective n’a été trouvé dans le périmètre audité.

Les accès inter-domaines sont encore nombreux. Les endpoints internes existent pour plusieurs services, mais leur adoption complète ne peut pas être déduite du seul découpage de code. Les adapters mémoire ne vérifient pas la disponibilité, les doublons, la fraîcheur, le périmètre ou les erreurs d’un système externe. Les réponses synthétiques ne doivent donc pas être utilisées pour valider une capacité métier réelle.

Le moteur de règles et le scoring ML sont présentés comme assistifs dans les modèles et documents existants. Cela ne remplace pas une analyse de risques, une validation de modèle, une surveillance de dérive, une revue d’équité ou une décision BOA sur les usages interdits. Aucune sortie ne doit être interprétée comme une décision automatique de crédit ou une promesse commerciale.

## 10. Migration progressive réaliste

### Étape 0 — Geler le périmètre et obtenir les validations

Nommer les propriétaires BOA par domaine, approuver la classification et les finalités, recenser les champs sensibles, arrêter les durées de conservation provisoires et définir les RPO/RTO. Produire une matrice d’accès signée et une liste des systèmes sources. Aucun raccordement réel ne doit précéder ces validations.

### Étape 1 — Stabiliser les frontières SQL sans changer le parcours utilisateur

Corriger la divergence `rule_management`/`rule`, créer les schémas par migration contrôlée, séparer les comptes de migration et de runtime, puis retirer `CREATE` des comptes d’exécution. Créer des rôles de lecture et d’écriture distincts pour Rule Engine, Rule Management et Simulation. Tester les privilèges sur une base vide et une copie anonymisée.

Pendant cette étape, conserver les accès inter-domaines nécessaires, mais les réduire à des vues ou colonnes minimales. Mesurer chaque requête inter-domaine et documenter son propriétaire, son volume, son motif et son plan de retrait. Cette étape est réaliste parce qu’elle ne dépend pas encore de la disponibilité des systèmes BOA.

### Étape 2 — Faire des APIs et snapshots les contrats officiels

Versionner les endpoints internes de customer, account, transaction, product, analytics, opportunity, action, feature et ML. Ajouter `as_of`, `source_version`, `schema_version`, `correlation_id`, fraîcheur et qualité. Introduire une projection `portfolio` explicitement alimentée, au lieu de laisser le service portefeuille lire plusieurs schémas sans garantie de privilège.

Mettre en place une double lecture contrôlée : l’ancienne requête SQL et la nouvelle API produisent un écart mesurable sur un échantillon, sans modifier le résultat présenté. Après stabilité, supprimer le droit SQL direct et garder un test de non-régression de contrat.

### Étape 3 — Remplacer les mocks par des adaptateurs homologués

Implémenter successivement les contrats `MockCBS` vers CBS, `MockCRM` vers CRM, `MockPayment` vers paiements et `MockTrade` vers trade/produits. Commencer par un environnement de test avec données synthétiques, puis un pilote limité et pseudonymisé. Comparer volumes, totaux, fraîcheur, codes produit et cas d’absence de donnée. Activer un drapeau de bascule réversible et conserver le mock pour les tests déterministes.

La bascule doit être faite domaine par domaine. Un échec d’un système source doit produire un état explicitement dégradé et observable, pas un faux `ABSENT`. Les imports doivent rester idempotents et rejouables après restauration.

### Étape 4 — Industrialiser PostgreSQL et la reprise

Déployer la topologie PostgreSQL HA retenue par BOA dans un environnement non productif équivalent, configurer sauvegardes, réplication, monitoring, rotation, TLS et restauration. Mesurer les RPO/RTO sur une panne primaire, une perte de nœud, une restauration à un point dans le temps et une perte de site logique. Rejouer les outbox et imports pour vérifier l’absence de doublons.

### Étape 5 — Réduire les accès résiduels et passer en exploitation contrôlée

Retirer progressivement les droits de lecture croisée après validation des projections/API. Conserver uniquement les exceptions documentées, temporaires et expirables. Ajouter des alertes sur requêtes hors périmètre, comptes privilégiés, échecs de TLS, secrets proches de l’expiration, retards d’import, dérive des scores et dépassement des durées de conservation. Le go/no-go doit être prononcé par les fonctions compétentes BOA sur preuves de tests, et non sur la seule réussite des tests unitaires.

## 11. Critères de sortie recommandés

La cible ne devrait pas être déclarée industrialisée tant que les points suivants ne sont pas démontrés :

- chaque service possède un rôle runtime minimal, un propriétaire de schéma clairement identifié et aucun droit de migration ;
- les lectures inter-domaines restantes sont listées avec une date de fin, une raison et une alternative API ou projection ;
- les quatre contrats d’adapter sont testés avec données valides, absentes, dupliquées, périmètre non autorisé et erreurs externes ;
- les finalités, accès, conservations, transferts et règles de minimisation sont validés par les fonctions compétentes BOA ;
- la restauration PostgreSQL et le rejeu idempotent des imports sont exécutés avec des mesures RPO/RTO ;
- TLS, rotation des secrets, logs sans données sensibles, alertes et runbooks sont vérifiés dans un environnement équivalent ;
- les opportunités, scores et règles restent explicables, versionnés et assistifs, sans confusion avec une décision de crédit ;
- toute limite non résolue est acceptée explicitement par le propriétaire de risque concerné.

## Références du dépôt

[1]: ../backend/src/boa_oi/models/entities.py "Modèles SQLAlchemy et schémas de données"
[2]: ../database/migrations/versions/0001_initial.py "Migration initiale des schémas et tables"
[3]: ../database/migrations/versions/0002_service_api_persistence.py "Persistance des APIs de service"
[4]: ../database/migrations/versions/0003_rule_studio.py "Tables Rule Studio et audit des règles"
[5]: ../database/migrations/versions/0004_ml_and_portfolio.py "Tables feature store, modèles, scores et labels"
[6]: ../backend/src/boa_oi/adapters/ports.py "Ports et types canoniques des adapters"
[7]: ../backend/src/boa_oi/adapters/mock.py "Implémentations mémoire des adapters"
[8]: ../backend/src/boa_oi/http_clients.py "Adaptateur bancaire HTTP et normalisation"
[9]: ../backend/src/boa_oi/mock_banking_api.py "API bancaire synthétique"
[10]: ../backend/src/boa_oi/technical/database.py "Création d’engine et cycle transactionnel"
[11]: ../infrastructure/postgres/00-init-service-schemas.sh "Bootstrap des rôles et schémas PostgreSQL"
[12]: ../infrastructure/docker-compose.yml "Topologie locale et URLs de connexion des services"
[13]: ../tests/unit/test_config_audit_adapters.py "Tests unitaires des adapters et de l’audit"
[14]: ../backend/src/boa_oi/portfolio_api.py "Lecture multi-domaine du portefeuille"
[15]: ../backend/src/boa_oi/transaction_api.py "Accès et agrégations SQL des transactions"

Cette version est une base de revue technique. Les décisions de conformité, de conservation, de criticité, de RPO/RTO et de raccordement aux systèmes BOA restent **À valider par les fonctions compétentes BOA**.
