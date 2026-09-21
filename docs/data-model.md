# Modèle relationnel PostgreSQL et pipeline de données synthétiques

**Produit :** BOA SME Opportunity Intelligence  
**Statut :** modèle implémenté du pilote ; extensions de production explicitement signalées
**Source fonctionnelle :** exigences du projet [1]

## 1. Décisions structurantes

Le modèle sépare les données bancaires observées, les résultats analytiques, les signaux détectés, les recommandations commerciales et les actions du chargé d’affaires. Une recommandation n’est jamais une donnée de seed : elle est produite par le moteur à partir d’un instantané déterministe des faits et reste traçable jusqu’aux transactions et aux métriques qui l’ont justifiée.

Le MVP utilise un **cluster PostgreSQL unique** pour simplifier l’exécution locale, mais chaque bounded context possède un schéma propriétaire. Les services accèdent aux données d’un autre domaine uniquement par API interne ou par événements ; aucun service ne lit directement les tables d’un schéma qui ne lui appartient. Cette séparation permet de migrer ensuite vers une base par service sans réécrire le domaine.

Les identifiants sont des UUID générés côté application. Les identifiants fonctionnels externes, tels que `SME-00125` ou une référence de transaction de l’adapter, sont conservés séparément et rendus uniques dans leur périmètre. Les montants sont stockés en `numeric(19,4)` avec une devise ISO 4217 ; aucune conversion implicite ne doit être effectuée dans les tables transactionnelles.

> Le résultat `FINANCIAL_STRESS_SIGNAL` est un signal commercial et relationnel. Il ne doit pas être nommé, exposé ou interprété comme score de crédit, score de risque, probabilité de défaut ou décision de crédit.

## 2. Cartographie des schémas et ownership

| Schéma propriétaire | Service propriétaire | Responsabilité | Tables principales |
|---|---|---|---|
| `iam` | API Gateway / Identity integration | Référence des sujets OIDC et rôles applicatifs ; les mots de passe restent dans Keycloak | `subjects`, `roles`, `subject_roles` |
| `customer` | Customer Service | PME, secteurs, segmentation et affectation RM | `customers`, `sectors`, `customer_segments`, `customer_relationships` |
| `account` | Account Service | Comptes, lignes, soldes et états de compte | `accounts`, `credit_lines`, `account_balances` |
| `transaction` | Transaction Service | Transactions normalisées et contreparties | `counterparties`, `transactions`, `transaction_tags` |
| `product` | Product Catalog Service | Catalogue, versions, règles d’éligibilité et détention | `products`, `product_versions`, `customer_products` |
| `analytics` | Transaction Analytics Service | Fenêtres, métriques et comparaisons historiques | `metric_definitions`, `metric_snapshots`, `metric_values` |
| `signal` | Signal Detection Service | Signaux, preuves et versions de règles | `signal_rules`, `signals`, `signal_evidence` |
| `opportunity` | Opportunity Service / Opportunity Engine | Recommandations calculées, explications et priorisation | `opportunity_rules`, `opportunities`, `opportunity_evidence`, `opportunity_recommendations`, `engine_runs` |
| `action` | Action / Notification Service | Actions RM, rendez-vous, résultats et boucle de feedback | `opportunity_actions`, `action_outcomes`, `customer_responses` |
| `integration` | Banking Integration Service et manifestes d'ingestion partagés | Import, idempotence, quarantaine et outbox | `import_batches`, `import_rejections`, `outbox_messages`; `source_systems` et `source_records` restent des cibles non implémentées |
| `audit` | API Gateway et services métier | Audit immuable des accès et décisions | `audit_logs`, `decision_audit` |

Les références interservices sont des identifiants opaques et stables. Les lectures SQL
directes des faits métier d'un autre service restent interdites. L'exception livrée par
`0016` est le manifeste technique partagé : `transaction.transactions.import_batch_id`
référence `integration.import_batches`, avec des droits SQL minimaux et explicites pour
le Transaction Service. Les contrats d'API demeurent la frontière des données métier.

## 3. Modèle relationnel détaillé

Les colonnes `created_at`, `updated_at`, `created_by` et, lorsque le contexte l’exige, `updated_by` suivent le type `timestamptz` en UTC. Les lignes métier ne sont pas supprimées physiquement dans le MVP ; une désactivation ou un statut terminal est privilégié afin de conserver la preuve de décision.

### 3.1 Référentiel client et relation

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `customer.customers` | `id`, `customer_ref`, `legal_name`, `trade_name`, `tax_identifier_hash`, `sector_id`, `segment_id`, `country_code`, `incorporated_on`, `status`, `annual_turnover_band`, timestamps | PK `id`; unique `customer_ref`; unique conditionnelle sur `tax_identifier_hash`; `status` dans `ACTIVE`, `SUSPENDED`, `CLOSED`; `country_code` ISO; aucun nom réel bancaire dans le seed |
| `customer.sectors` | `id`, `code`, `label`, `active` | PK; unique `code`; valeurs de seed : industrie, import/export, distribution, services, BTP, agriculture, commerce, technologie |
| `customer.customer_segments` | `id`, `code`, `label`, `active` | PK; unique `code`; valeurs configurables, par exemple `MICRO`, `SMALL`, `MEDIUM` |
| `customer.customer_relationships` | `id`, `customer_id`, `rm_subject_id`, `branch_code`, `valid_from`, `valid_to`, `is_primary` | PK; FK logique vers `iam.subjects` et `customer.customers`; une seule relation primaire active par client; `valid_from < valid_to` |
| `iam.subjects` | `subject_id` OIDC, `display_name`, `email_hash`, `status` | PK sur le sujet OIDC; les secrets ne sont jamais stockés dans PostgreSQL |
| `iam.roles` / `iam.subject_roles` | rôle, sujet, dates de validité | PK composite; rôle limité à `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN`, `DATA_ANALYST`; dates cohérentes |

Le modèle ne stocke pas de données personnelles inutiles. Le générateur utilise des noms synthétiques explicitement marqués comme tels, et les identifiants de démonstration ne doivent pas ressembler à des identifiants bancaires réels.

### 3.2 Comptes, lignes et soldes

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `account.accounts` | `id`, `account_ref`, `customer_id`, `account_type`, `currency`, `opened_on`, `status`, `source_system_id` | PK; unique `account_ref`; FK client; `account_type` dans `CURRENT`, `SAVINGS`, `CREDIT`; devise ISO; un compte appartient à un seul client |
| `account.credit_lines` | `id`, `account_id`, `facility_type`, `approved_limit`, `currency`, `valid_from`, `valid_to`, `status` | PK; FK compte; limite positive; pas de chevauchement de lignes actives de même type; absence de ligne signifie absence de capacité connue, pas décision de crédit |
| `account.account_balances` | `id`, `account_id`, `as_of_date`, `closing_balance`, `available_balance`, `currency` | PK; unique `(account_id, as_of_date)`; la provenance gouvernée par ligne reste **NON IMPLÉMENTÉE** pour Account |

Les balances servent à l’analyse quotidienne et à la reconstitution des fenêtres. Les métriques agrégées ne remplacent pas cette source : elles doivent toujours pouvoir être recalculées.

### 3.3 Transactions et provenance bancaire

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `transaction.counterparties` | `id`, `counterparty_ref_hash`, `display_name_synthetic`, `country_code`, `counterparty_type`, `is_supplier` | PK; unicité sur le hash de référence; contrepartie synthétique; `counterparty_type` dans `SUPPLIER`, `CUSTOMER`, `BANK`, `OTHER` |
| `transaction.transactions` | `id`, `transaction_ref`, `customer_id`, `account_id`, `booked_at`, `value_date`, `direction`, `amount`, `currency`, `transaction_type`, `category`, `is_international`, `country_code`, `status`, `source_system`, `import_batch_id`, `source_record_hash`, `category_version` | PK; unique `(source_system, transaction_ref)`; FK du lot vers `integration.import_batches`; `amount > 0`; `direction` dans `CREDIT`, `DEBIT`; les lignes gouvernées conservent lot, hash source et version de catégorie; les lignes historiques peuvent laisser ces trois champs à `null` |
| `config.transaction_categories` | `category_code`, `version`, `label`, `active`, `provenance`, `checksum`, `reason`, `created_at`, `created_by` | unique `(category_code, version)`; une seule version active par code; provenance limitée à `SYNTHETIC_POC`, `BOA_APPROVED`, `EXTERNAL_CONTRACT`; les trois entrées initiales sont explicitement synthétiques et non approuvées BOA |
| `integration.import_batches` | identité source/lot, version de contrat, hash, watermark, timestamps, compteurs, statuts qualité/fraîcheur, `quality_json` | claim atomique unique `(source_system, batch_ref)`; compteurs non négatifs; états terminaux `COMPLETED`, `QUARANTINED`, `REJECTED` et états d'orchestration partielle documentés |
| `integration.import_rejections` | `batch_id`, domaine, numéro/référence/hash de ligne, code motif, champ, détail minimisé, statut, corrélation | unique `(batch_id, domain, row_number)`; aucun payload brut; une ligne quarantainée n'est pas écrite dans `transaction.transactions` |
| `transaction.transaction_tags` | cible future : `transaction_id`, `tag_code`, `confidence` | **NON IMPLÉMENTÉ**; ne pas confondre ce modèle cible avec le catalogue de catégories livré en `0016` |

Les paiements fournisseurs sont identifiés par catégorie et direction; les flux
internationaux reposent sur `is_international` et le pays, non sur un texte libre. Le
contrat Transaction `1.0` applique une acceptation partielle explicite : ligne valide
écrite, doublon compté, catégorie inconnue/inactive mise en quarantaine. La fraîcheur
est `UNKNOWN` sans horodatage source; lorsqu'un horodatage existe, le délai est mesuré
sans seuil inventé. Les imports Customer, Account et Product n'utilisent pas encore ce
manifeste commun : leur généralisation reste **NON IMPLÉMENTÉE**.

### 3.4 Catalogue et produits détenus

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `product.products` | `id`, `product_code`, `name`, `category`, `family`, `description`, `source_url`, `eligibility_rules_json`, `target_segments_json`, `currencies_json`, `active` | PK; unique `product_code`; `family`, `description` et `source_url` ajoutés par `0018`; les règles ne référencent jamais un nom en dur |
| `product.product_versions` | `id`, `product_id`, `version`, `eligibility_rules_json`, `target_segments_json`, `currencies_json`, `valid_from`, `valid_to` | PK; unique `(product_id, version)`; une seule version active à une date; JSON validé par schéma applicatif |
| `product.customer_products` | `id`, `customer_id`, `product_id`, `status`, `opened_on`, `utilization_ratio` | PK; FK produit; la provenance gouvernée par ligne et les contraintes métier supplémentaires restent **NON IMPLÉMENTÉES** pour Product |

Le seed synthétique comprend 28 produits publics regroupés dans les familles `INVESTMENT_FINANCING`, `WORKING_CAPITAL_FACILITY`, `OVERDRAFT`, `TRADE_FINANCE`, `CASH_MANAGEMENT`, `TERM_DEPOSIT` et `LIQUIDITY_INVESTMENT`. La lacune est calculée par famille et la recommandation porte sur des codes produit précis. Les nouvelles versions Rule Studio sont refusées lorsqu’elles référencent un code absent de cette source exécutable ; une ancienne règle publiée obsolète ou un produit connu devenu absent/inactif fait échouer explicitement la génération Opportunity au lieu de produire une recommandation vide. La migration `0018` ne réécrit que les configurations synthétiques connues, jamais une règle utilisateur ou BOA. Elle n’insère pas le catalogue : la matérialisation par seed est obligatoire et `/ready` bloque si les 28 entrées actives ne correspondent pas au référentiel exécuté. Les routes client Product Service réappliquent le scope objet côté service. Les pages publiques attestent l’existence et la nature générale des produits, mais les ciblages et critères demeurent **HYPOTHÈSE À VALIDER AVEC BOA**.

### 3.5 Analytique, signaux et règles

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `analytics.metric_definitions` | `id`, `metric_code`, `unit`, `aggregation`, `description`, `active` | PK; unique `metric_code`; valeurs : `MONTHLY_INFLOW`, `MONTHLY_OUTFLOW`, `AVERAGE_BALANCE`, `MINIMUM_BALANCE`, `MAXIMUM_BALANCE`, `TRANSACTION_COUNT`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_GROWTH`, `CASH_BALANCE_GROWTH`, `CREDIT_LINE_UTILIZATION` |
| `analytics.metric_snapshots` | `id`, `customer_id`, `as_of_date`, `window_days`, `baseline_kind`, `calculation_version`, `input_watermark`, timestamps | PK; unique `(customer_id, as_of_date, window_days, calculation_version)`; fenêtre limitée à 7, 30, 90, 180 ou 365 jours; `baseline_kind` dans `PREVIOUS_PERIOD`, `HISTORICAL_MEDIAN`, `SEASONAL_BASELINE` |
| `analytics.metric_values` | `snapshot_id`, `metric_definition_id`, `current_value`, `previous_value`, `growth_rate`, `sample_size`, `quality_status` | PK composite; croissance nulle si le dénominateur est insuffisant doit être distinguée de l’absence de valeur; `quality_status` dans `VALID`, `INSUFFICIENT_HISTORY`, `PARTIAL` |
| `signal.signal_rules` | `id`, `rule_code`, `version`, `configuration_json`, `active`, `valid_from`, `valid_to` | PK; unique `(rule_code, version)`; seuils versionnés, jamais codés dans le frontend; changement d’une règle crée une nouvelle version |
| `signal.signals` | `id`, `signal_ref`, `customer_id`, `signal_type`, `severity`, `value`, `threshold`, `detected_at`, `rule_id`, `analytics_snapshot_id`, `status` | PK; unique `signal_ref`; FK vers règle et snapshot; types contrôlés (`INFLOW_GROWTH`, `OUTFLOW_GROWTH`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_GROWTH`, `BALANCE_SURPLUS`, `BALANCE_DECLINE`, `CREDIT_UTILIZATION_INCREASE`, `TRANSACTION_VOLUME_GROWTH`); `severity` dans `LOW`, `MEDIUM`, `HIGH` |
| `signal.signal_evidence` | `id`, `signal_id`, `evidence_type`, `metric_code`, `source_transaction_id`, `statement`, `observed_value`, `comparison_value`, `position` | PK; FK signal; au moins une preuve par signal; une preuve peut pointer vers une métrique ou une transaction source; `position` unique dans un signal |

Un signal est idempotent pour une même combinaison client, type, fenêtre, date de détection et version de règle. Une nouvelle valeur observée donne un nouvel enregistrement, plutôt qu’une modification destructive.

### 3.6 Opportunités et explication

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `opportunity.opportunity_rules` | `id`, `opportunity_type`, `version`, `configuration_json`, `active`, `valid_from`, `valid_to` | PK; unique `(opportunity_type, version)`; contient conditions, poids de confiance, horizon et produits candidats par code |
| `opportunity.engine_runs` | `id`, `run_ref`, `started_at`, `completed_at`, `engine_version`, `rule_set_version`, `input_watermark`, `status`, `error_summary` | PK; unique `run_ref`; statut `STARTED`, `COMPLETED`, `FAILED`; chaque calcul est rejouable à partir de son watermark |
| `opportunity.opportunities` | `id`, `opportunity_ref`, `customer_id`, `opportunity_type`, `opportunity_status`, `horizon`, `confidence_score`, `confidence_level`, `priority_score`, `priority_level`, `generated_at`, `valid_until`, `engine_run_id`, `rule_id`, `deduplication_key` | PK; unique référence; `opportunityStatus` dans `OPEN`, `EXPIRED`, `SUPERSEDED`; scores `confidence` 0..1 et `priorityScore` 0..100; unique conditionnelle sur une opportunité ouverte par `(customer_id, opportunity_type, deduplication_key)` |
| `opportunity.opportunity_evidence` | `id`, `opportunity_id`, `signal_id`, `metric_snapshot_id`, `metric_code`, `observed_value`, `threshold`, `comparison_value`, `why_text`, `position` | PK; FK opportunité, signal et snapshot; au moins une ligne; `position` unique par opportunité; les valeurs sont recopiées pour préserver l’explication historique |
| `opportunity.opportunity_recommendations` | `opportunity_id`, `product_id`, `rank`, `reason_code`, `recommended` | PK composite; FK produit; rang unique par opportunité; produit actif à la date de génération |

`WHY`, `WHAT`, `WHEN`, `CONFIDENCE` et `EVIDENCE` sont dérivés de ces colonnes et non d’un texte libre saisi dans l’interface. Le score de confiance est explicable : chaque composant est conservé dans `opportunity_evidence` ou dans un champ JSON versionné de l’exécution. Une opportunité expirée n’est pas supprimée ; elle peut être régénérée avec une nouvelle clé de déduplication temporelle.

### 3.7 Actions, résultats et feedback

| Table | Colonnes essentielles | Clés et contraintes |
|---|---|---|
| `action.opportunity_actions` | `id`, `opportunity_id`, `customer_id`, `action_type`, `actor_subject_id`, `scheduled_at`, `performed_at`, `notes_redacted`, `created_at` | PK; FK opportunité/client; types `ACCEPT_OPPORTUNITY`, `DISMISS_OPPORTUNITY`, `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP`, `SCHEDULE_MEETING`, `MARK_CONVERTED`; l’acteur doit avoir un rôle autorisé; notes sans données sensibles non nécessaires |
| `action.action_outcomes` | `id`, `action_id`, `outcome_type`, `occurred_at`, `value_origin`, `recorded_by` | PK; outcomes `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED`, `NOT_RELEVANT`; `value_origin` distingue `OBSERVED`, `SIMULATED`, `NOT_REPORTED`; aucune valeur de revenu inventée |
| `action.customer_responses` | `id`, `action_id`, `response_code`, `response_at`, `source`, `details_redacted` | PK; réponse synthétique et optionnelle; jamais de commentaire client réel dans le dataset |

La chaîne de feedback est donc `recommendation → RM action → customer response → commercial outcome`. Les tables d’action ne modifient pas l’évidence originale de l’opportunité.

### 3.8 Intégration, événements et audit

| Table | Colonnes essentielles | Contraintes et usage |
|---|---|---|
| `integration.source_systems` | cible future : `id`, `code`, `adapter_type`, `contract_version`, `active` | **NON IMPLÉMENTÉ**; les sources sont aujourd'hui des codes contrôlés dans les contrats et manifests |
| `integration.import_batches` | `id`, `source_system`, `batch_ref`, `contract_version`, `external_batch_id`, `input_hash`, watermark/timestamps, compteurs, `quality_status`, `freshness_status`, `quality_json`, `status`, `correlation_id` | Unique `(source_system, batch_ref)`; claim atomique, hash rejouable, compteurs et qualité persistés; aucune conservation de payload brut |
| `integration.import_rejections` | `batch_id`, `domain`, `row_number`, `source_record_ref`, `row_hash`, `reason_code`, `field_name`, `safe_details_json`, `status`, timestamps | Quarantaine minimisée; `safe_details_json` est allowlisté et ne contient pas le payload source complet |
| `integration.source_records` | cible future éventuelle | **NON IMPLÉMENTÉ**; aucun `payload_json` source n'est conservé par le lot `0016` |
| `integration.outbox_messages` | `id`, `event_type`, `aggregate_type`, `aggregate_id`, `payload_json`, `occurred_at`, `published_at`, `attempt_count`, statut/erreur | Outbox effectivement persistée; la livraison exactly-once n'est pas revendiquée |
| `audit.audit_logs` | `id`, `occurred_at`, `actor_subject_id`, `service_name`, `action`, `resource_type`, `resource_id`, `correlation_id`, `request_id`, `result`, `metadata_json` | Append-only; pas de token ni secret; partitionnement temporel possible |
| `audit.decision_audit` | `id`, `engine_run_id`, `opportunity_id`, `engine_version`, `rule_version`, `generated_at`, `input_reference`, `signal_ids_json`, `metric_snapshot_ids_json`, `confidence_components_json`, `decision_hash` | Append-only; `decision_hash` détecte une altération; une décision doit être reconstituable sans consulter l’interface |

## 4. Contraintes, index et performance

Les index sont créés selon les accès des APIs et du moteur, sans indexer chaque colonne. Les tables transactionnelles et d’audit sont candidates au partitionnement mensuel par `booked_at` et `occurred_at` lorsque le volume réel le justifiera.

| Table | Index principaux |
|---|---|
| `customer.customers` | `(status, sector_id, segment_id)`; recherche trigramme sur `legal_name` et `trade_name` si l’extension `pg_trgm` est autorisée; unique `customer_ref` |
| `customer.customer_relationships` | `(rm_subject_id, is_primary, valid_to)`; `(customer_id, is_primary)` |
| `account.accounts` | `(customer_id, status)`; `(account_ref)` unique |
| `account.account_balances` | `(account_id, as_of_date DESC)`; `(as_of_date)` |
| `transaction.transactions` | `(customer_id, value_date)`; `(account_id, value_date)`; `(customer_id, is_international, value_date)`; `(customer_id, category, value_date)`; `(import_batch_id)` |
| `product.customer_products` | `(customer_id, status)`; `(product_id, status)`; unique active conditionnelle |
| `analytics.metric_snapshots` | `(customer_id, as_of_date DESC, window_days)`; `(as_of_date, metric_version)` |
| `signal.signals` | `(customer_id, detected_at DESC)`; `(signal_type, detected_at DESC)`; `(severity, status)`; unique idempotence |
| `opportunity.opportunities` | `(status, priority_level, priority_score DESC, generated_at DESC)`; `(customer_id, generated_at DESC)`; `(opportunity_type, status)`; `(valid_until)` |
| `opportunity.opportunity_evidence` | `(opportunity_id, position)`; `(signal_id)`; `(metric_snapshot_id)` |
| `action.opportunity_actions` | `(opportunity_id, created_at DESC)`; `(actor_subject_id, created_at DESC)`; `(action_type, performed_at)` |
| `integration.source_records` | **NON IMPLÉMENTÉ**; aucun index ni table à ce nom |
| `audit.audit_logs` | `(resource_type, resource_id, occurred_at DESC)`; `(actor_subject_id, occurred_at DESC)`; `(correlation_id)` |

Les listes d’opportunités, clients, signaux et transactions sont paginées par curseur `(date, id)` plutôt que par `OFFSET` profond. Les agrégations sont calculées par Analytics et servies depuis `analytics`, afin de ne pas charger des millions de transactions dans le dashboard.

## 5. Stratégie de migrations

Les migrations sont versionnées, immuables et exécutées par un job dédié avant le démarrage des services. Une migration comporte un identifiant monotone, un propriétaire de schéma et une justification. Le pipeline CI exécute les migrations sur une base vide, puis sur une base contenant un jeu de régression.

La séquence initiale est :

1. créer les extensions autorisées, les schémas et les rôles PostgreSQL non privilégiés ;
2. créer les tables de référentiel et les contraintes de base ;
3. créer les tables transactionnelles, d’intégration et de provenance ;
4. créer catalogue, analytique, signaux, opportunités et actions ;
5. ajouter index et politiques de rétention ;
6. charger uniquement les référentiels et règles versionnées ;
7. exécuter le générateur synthétique et les calculs métier.

Les changements suivent **expand–migrate–contract**. Une colonne nouvelle est d’abord nullable, les services sont déployés en lecture/écriture compatible, les données sont backfillées par lots, puis la contrainte `NOT NULL` est ajoutée dans une migration ultérieure. Les index lourds sont créés de manière concurrente hors transaction lorsque PostgreSQL le permet. Une migration ne réécrit pas les opportunités existantes ; une nouvelle version de moteur crée un nouvel `engine_run` et conserve les anciennes décisions.

Un rollback applicatif est privilégié au rollback destructif : les migrations de suppression sont différées et précédées d’une période de compatibilité. Les snapshots, `decision_audit`, événements et import batches sont immuables pour permettre une comparaison entre versions de règles.

## 6. Dataset synthétique : 500 PME et 12 mois

### 6.1 Périmètre et volumes cibles

La référence déterministe est `seed = boa-sme-oi-2026-v1`. La période comporte 12 mois complets, par exemple du 1er octobre 2025 au 30 septembre 2026, avec une date d’évaluation au 30 septembre 2026. Le générateur ne dépend ni de l’heure système ni de l’ordre d’exécution ; chaque sous-générateur utilise un flux pseudo-aléatoire dérivé de `seed + customer_ref + mois + domaine`.

| Objet | Hypothèse de volume MVP |
|---|---:|
| PME | 500 |
| Secteurs | 8, répartis de façon pondérée |
| Relationship managers | 25 à 40, avec 10 à 20 PME chacun |
| Comptes | 1 250 à 1 750, soit 2 à 3 par PME |
| Jours de soldes | 456 000 à 638 000, selon comptes ouverts |
| Transactions | 750 000 à 1 500 000, moyenne cible d’environ 2 000 par PME sur 12 mois |
| Contreparties | 40 000 à 80 000 dédupliquées, dont fournisseurs récurrents |
| Produits catalogue | **28 codes actifs prouvés**, répartis en 7 familles internes |
| Détentions produits | distribution déterministe synthétique par famille ; aucun volume BOA revendiqué |
| Snapshots analytiques | 500 × 5 fenêtres × 12 dates = 30 000 par métrique de base ; stockage agrégé selon besoin |
| Signaux | non fixé dans le seed ; environ 1 à 5 par client et par date d’évaluation selon les scénarios |
| Opportunités | **0 avant exécution du moteur** ; volume produit après calcul et contrôlé par les tests |
| Actions et outcomes | zéro au chargement initial, puis générés par le scénario de démonstration ou les tests |

Le volume transactionnel est réaliste mais reste exécutable localement. La fourchette permet d’ajuster la densité par secteur sans changer les règles. Le générateur produit des distributions cohérentes : montant et fréquence dépendent du secteur, du segment, du nombre de comptes, de la saison et du scénario.

### 6.2 Génération en plusieurs passes

La première passe crée les référentiels, les 500 clients, les RM et les affectations. La seconde crée les comptes, les lignes existantes et le catalogue produit. La troisième génère les contreparties récurrentes et les transactions quotidiennes. Les soldes sont dérivés de l’ordre chronologique des transactions, avec une réserve initiale et des contrôles de non-négativité adaptés aux comptes autorisés. La quatrième crée les détentions produits. La dernière passe écrit les manifests/checkpoints `import_batches` effectivement utilisés et vérifie les invariants. `integration.source_records` reste **NON IMPLÉMENTÉ**.

Le générateur applique des profils par secteur : l’industrie et le BTP ont davantage de paiements fournisseurs et de montants unitaires élevés ; l’import/export a davantage de transactions internationales ; la distribution et le commerce ont une fréquence élevée et une saisonnalité ; les services et la technologie ont des flux plus réguliers ; l’agriculture a une saisonnalité marquée. Ces profils modifient les faits observés, jamais les résultats attendus directement.

Les transactions sont créées par séries de clients, mois et jours ouvrés. Chaque série possède une intensité de base, un bruit borné, une proportion crédit/débit, une fréquence internationale et une distribution de montants. Les séries de saisonnalité comparent le mois courant à la médiane des mois homologues ou à une baseline historique, afin qu’un pic de décembre isolé ne soit pas considéré automatiquement comme une opportunité.

## 7. Scénarios déterministes et oracle métier

Les scénarios sont des paramètres de génération, pas des lignes `opportunities`. Chaque scénario est assigné à un groupe de clients stable par hash du `customer_ref`. Certains clients peuvent cumuler un profil sectoriel et un scénario, mais les tests d’acceptation utilisent des clients isolés et des fenêtres de données dédiées.

| Scénario | Faits générés sur les 90 derniers jours | Produits détenus | Résultat attendu après Analytics → Signals → Engine |
|---|---|---|---|
| `GROWTH_COMPANY` | encaissements +40 %, paiements fournisseurs +30 %, volume +20 %, croissance cohérente sur au moins deux fenêtres | pas de financement d’investissement récent | `INVESTMENT_FINANCING`, horizon 1–3 mois |
| `STABLE_COMPANY` | variation bornée autour de la baseline, solde stable, fréquence stable | détentions ordinaires | aucun signal commercial fort et aucune opportunité obligatoire |
| `INTERNATIONAL_GROWTH` | flux internationaux +50 %, fréquence croissante sur plusieurs mois | Trade Finance absent ou sous-utilisé | `TRADE_FINANCE`, horizon 0–3 mois |
| `CASH_SURPLUS` | solde moyen élevé et excédent présent dans plusieurs fenêtres, utilisation de ligne basse | faible utilisation de crédit | `CASH_INVESTMENT`, horizon 0–1 mois |
| `FINANCIAL_STRESS` | encaissements -35 %, solde -25 %, utilisation de ligne +40 % et dégradation persistante | ligne existante si nécessaire pour observer l’utilisation | `FINANCIAL_STRESS_SIGNAL`, sans vocabulaire de risque ou de crédit |
| `NORMAL_CUSTOMER` | profil sectoriel et bruit réaliste sans combinaison de seuils | mixte | aucune opportunité attendue par défaut |
| `FALSE_POSITIVE_SEASONAL` | hausse concentrée sur décembre, retour à la baseline, comparable aux années ou mois saisonniers | variable | aucune opportunité issue d’un pic isolé |
| `FALSE_POSITIVE_ONE_OFF` | une transaction internationale exceptionnellement élevée, sans répétition ni hausse de fréquence | Trade Finance absent | aucun `TRADE_FINANCE` |

Les seuils sont stockés dans `signal_rules` et `opportunity_rules`, par exemple `0.25` pour la croissance des encaissements, `0.20` pour les paiements fournisseurs, `0.15` pour le volume, `0.30` pour les flux internationaux, `0.25` pour la baisse des encaissements et `0.20` pour la baisse du solde. Les tests ne contournent pas ces tables : ils chargent une version de règles connue, calculent les métriques, puis vérifient les résultats.

L’oracle d’acceptation vérifie aussi les négatifs : une seule transaction ne suffit pas pour une tendance ; une métrique `INSUFFICIENT_HISTORY` ne déclenche pas de recommandation ; un produit déjà détenu et correctement utilisé ne constitue pas un gap ; un signal de tension n’est jamais sérialisé sous `credit_score`, `risk_score` ou une autre décision de crédit.

## 8. Pipeline synthétique et traçabilité

Le pipeline local `demo-data-generator` suit les étapes suivantes :

1. **Initialisation.** Vérifier la version de schéma, le seed, la période et l’absence de données réelles. Émettre un manifeste avec `seed`, commit, période, paramètres et hash de configuration.
2. **Référentiels.** Insérer secteurs, segments, RM, catalogue produit, versions de règles et systèmes sources avec des opérations idempotentes.
3. **Clients et comptes.** Créer les 500 PME, affecter un RM, créer les comptes et lignes, puis enregistrer la provenance synthétique.
4. **Faits bancaires.** Générer contreparties, transactions et balances dans des batches bornés. Le seed direct ne prétend pas produire de `source_record_id`. Les transactions acceptées par le contrat gouverné `1.0` portent `import_batch_id`, `source_record_hash` et `category_version`; les lignes historiques/seed peuvent laisser ce lineage à `null`.
5. **Contrôles de qualité.** Vérifier unicité des références, continuité des dates, cohérence devise-compte, balance dérivée, bornes de montants, proportions par secteur et couverture des 12 mois.
6. **Calcul analytique.** Produire les métriques 7, 30, 90, 180 et 365 jours. Comparer période courante, période précédente et baseline historique ou saisonnière. Enregistrer le watermark d’entrée et la version de calcul.
7. **Détection des signaux.** Évaluer les règles versionnées, créer les signaux idempotents et leurs preuves, puis publier `SignalDetected` dans l’outbox.
8. **Génération des opportunités.** Combiner signaux, profil client, produits détenus et historique. Calculer confiance, niveau, priorité, horizon et produits recommandés. Écrire `engine_runs`, `opportunities`, `opportunity_evidence` et `decision_audit` dans une transaction logique. Publier `OpportunityCreated`.
9. **Scénario d’action optionnel.** Pour une démonstration, simuler séparément l’action RM et le résultat. Ces lignes sont distinguées par `value_origin = SIMULATED` et ne font pas partie du seed bancaire.
10. **Rapport de reproductibilité.** Produire les volumes par table, les hashes de batches, les résultats de contrôles et l’oracle attendu par scénario. Une seconde exécution avec le même seed ne crée aucun doublon.

La traçabilité minimale pour une opportunité est : `opportunity → engine_run → opportunity_rule → signal(s) → analytics.metric_snapshot → transactions/account_balances → source_record → import_batch → source_system`. La décision d’origine contient également les versions du moteur et des règles, le watermark, les seuils, les composants de confiance et un hash de décision. Cette chaîne permet d’expliquer une recommandation même après une évolution du catalogue ou des règles.

## 9. Politique de chargement et absence d’opportunités préchargées

Le seed autorisé charge des référentiels, clients, comptes, balances, transactions, produits détenus, batches d’intégration et éventuellement des événements d’import. Il ne charge ni `opportunity.opportunities`, ni `opportunity.opportunity_evidence`, ni `opportunity.engine_runs` terminés, ni actions. Ces tables doivent être vides avant le premier calcul métier.

Une contrainte opérationnelle du pipeline de démonstration vérifie cette condition et échoue si une opportunité existe déjà. La commande de seed ne peut donc pas donner l’illusion que le moteur fonctionne. Après le seed, le job Analytics puis le Signal Engine puis l’Opportunity Engine construisent les résultats à partir des données PostgreSQL réellement présentes. Le dashboard ne dispose d’aucun tableau JSON local ni d’aucun fallback de données.

Les opportunités produites lors d’un calcul sont conservées comme décisions historiques, mais elles ne sont pas réinjectées comme faits lors d’un recalcul. Un rerun identique est idempotent par `engine_run` et clé de déduplication ; un rerun avec une nouvelle version de règle crée une nouvelle décision auditable et permet une comparaison.

## 10. Contrôles d’acceptation du modèle

Le modèle est considéré prêt pour l’implémentation lorsqu’il satisfait les contrôles suivants :

- les 500 clients possèdent un secteur, un segment, un RM et au moins un compte ;
- chaque compte possède une devise, un statut et une série de balances couvrant la période attendue ;
- les transactions sont idempotentes par source, liées à un compte et filtrables par les critères API requis ;
- les données contiennent au moins 12 mois et les cinq fenêtres analytiques ;
- aucun secret, token, donnée bancaire réelle ou appel LLM externe n’est nécessaire au pipeline ;
- les seuils et poids sont modifiables par version de configuration ;
- les scénarios positifs et faux positifs sont reproductibles avec le seed de référence ;
- aucune opportunité n’existe avant le calcul du moteur ;
- toute opportunité créée possède au moins un signal ou une preuve métrique, un `engine_run`, une règle et une décision d’audit ;
- une action et son outcome sont séparés de la recommandation et portent l’identité de l’acteur ;
- les suppressions physiques ne peuvent pas effacer la preuve d’une décision ;
- les index et la pagination permettent de servir 500+ clients et plusieurs centaines de milliers de transactions sans lecture complète depuis le frontend.

## Références

[1]: file:///home/ubuntu/upload/Pasted_content_100.txt "Requirements — BOA SME Opportunity Intelligence"

## Décision finale — propriété des données

Chaque bounded context possède un schéma, un utilisateur SQL, des modèles SQLAlchemy et des migrations Alembic. Les identifiants interservices sont opaques ; les clés étrangères inter-schémas et lectures SQL tierces sont interdites. `customer_products` est possédé par Product Service.

`opportunityStatus` est possédé par Opportunity Service ; `engagementStatus` est dérivé par Action Service. Les scores sont `confidence` 0..1 et `priorityScore` 0..100. Les événements sont écrits dans des outboxes locales.


---

## 11. Extensions portefeuilles et ML de propension

Cette section distingue l’état implémenté des cibles encore différées. Les affectations datées, la synchronisation gouvernée, le Feature Store, le registre ML POC/shadow et la lignée d’inférence sont implémentés. Les projections de scope signées, le WORM externe et les topologies multi-agences restent des cibles de production.

### 11.1 Ownership cible

| Schéma | Service propriétaire | Tables cibles | Finalité |
|---|---|---|---|
| `customer` | Customer Service | `portfolio_assignments`, `portfolio_sync_events`, `portfolio_sync_receipts` | agence, CC, portefeuille, affectations temporelles et provenance de synchronisation |
| `feature` | Feature Service | `feature_definitions`, `feature_definition_versions`, `feature_sets`, `feature_set_members`, `feature_snapshots`, `feature_values`, `feature_lineage` | registre et snapshots point-in-time |
| `ml_registry` | ML Management Service | `models`, `model_versions`, `model_artifacts`, `model_approvals`, `training_datasets`, `dataset_consents`, `fusion_policies` | modèles, datasets et fusion gouvernés |
| `ml_inference` | ML Engine | `inference_runs`, `propensity_scores`, `prediction_explanations` | inférences CPU et scores immuables |
| `ml_monitoring` | ML Monitoring | `monitoring_windows`, `feature_drift_metrics`, `score_drift_metrics`, `model_performance_metrics`, `model_alerts` | qualité, drift et performance différée |
| `opportunity` | Opportunity Service | `opportunity_fusion_decisions` | garde-fous et résultat de fusion |

### 11.2 Agence, CC et portefeuille

`customer.portfolio_assignments` porte portefeuille, client, agence, CC, type d’affectation, caractère primaire, dates de validité, motif, acteur, système source, événement source, watermark et hash canonique. La contrainte d’exclusion PostgreSQL interdit tout chevauchement des intervalles `[validFrom, validTo)` d’un même client. Une réaffectation clôt une ligne et en crée une autre ; elle ne réécrit ni opportunité, ni score, ni action historique.

`customer.portfolio_sync_events` garantit l’idempotence de `(sourceSystem, sourceEventId)`. `customer.portfolio_sync_receipts` garantit l’idempotence du lot et conserve la réponse HTTP rejouable. Une modification d’affectation écrit aussi une outbox `PORTFOLIO_ASSIGNMENT_CHANGED` et un audit avant/après. Les événements antidatés antérieurs au dernier intervalle sont refusés et nécessitent une réconciliation explicite.

Les lectures courantes Customer, Portfolio et Opportunity interrogent l’affectation valable à l’instant de la requête. Une future projection de scope signée portera version, watermark, dates de génération/expiration et checksum ; elle n’est pas encore implémentée. Le CC est relié logiquement au sujet Keycloak ; aucun secret n’est stocké dans ce schéma.

### 11.3 Feature Registry et snapshots

Chaque version de feature conserve sens métier, propriétaire, source, type, unité, fenêtre, règle `asOf`, fraîcheur, transformation, qualité, finalité, usages interdits, sensibilité, leakage, label d’explication, auteur, approbateur et checksum. Une version active est immuable. Les usages crédit, défaut, octroi, prix et limite sont interdits.

Un `feature_snapshot` est idempotent sur `(customer_id, as_of, feature_set_version, source_watermark)`. Ses valeurs typées indiquent qualité, date d’observation et imputation. Son lineage référence Analytics, Signals et Rules par identifiants opaques. Aucune donnée observable après `asOf` n’entre dans le vecteur. Offline et serving partagent définitions et transformations.

### 11.4 Model Registry, datasets et évaluations shadow

`ml.model_registry` conserve modèle/version, cible, horizon, interprétation `RANKING_ONLY`, statut de calibration, feature set, dataset déclaré, hash de manifest, code, hyperparamètres, métriques, artefact et checksum. La migration `0017` impose `deployment_mode='POC_SHADOW'`. `ml.training_runs` conserve le même mode, le hash de manifest, le checksum d’artefact et le statut de gate. Une approbation de workflow ne contourne pas les blockers d’activation.

`ml.dataset_manifests` persiste version, source, finalité, définition de label, cible, horizon, population, exclusions, cutoff, identifiants des snapshots features/labels, nombre de lignes, hash et blockers. `ml.outcome_label_snapshots` versionne la définition, la source, la fermeture de fenêtre, le statut candidat et le lien feature point-in-time. Les outcomes locaux restent `candidate_only=true` et bloqués par `BOA_HISTORICAL_LABELS_UNAVAILABLE`. L’absence d’outcome n’est pas un label négatif.

`ml.evaluation_snapshots` persiste période, source, manifest, volumes, métriques descriptives — dont Brier et ECE —, méthode/statut de calibration, critères d’acceptation et blockers. L’entrée actuelle est déclarative et reçoit donc toujours un blocker de non-rattachement aux snapshots. Sans historique BOA gouverné, critères BOA et validation indépendante, le statut reste `BLOCKED` et la calibration `NOT_VALIDATED`. La promotion résout transactionnellement le manifest, les snapshots référencés et l’évaluation persistée ; des hashes ou métriques seulement déclarés dans un run ne suffisent pas.

### 11.5 Inférence, explication, fusion et drift

`propensity_scores` conserve client, score, `scoreBand`, modèle, feature set, feature snapshot, checksum, watermark, dataset déclaré, mode `POC_SHADOW`, interprétation `RANKING_ONLY`, statut de calibration, validité, version de contrat, trace et contributions. Le score reste dans `[0,1]` ; aucune valeur par défaut n’est autorisée. `scoreBand` n’est pas une calibration.

`opportunity.opportunities` persiste une priorité issue des règles avec `rules_weight=1`, `ml_weight=0` et `fallback_mode='RULES_ONLY'`. L’explication peut référencer le score sous `propensityShadow`, séparé de la combinaison opérationnelle. Des contraintes PostgreSQL empêchent toute opportunité ou policy `ACTIVE` hybride, refusent une fenêtre temporelle inversée et limitent le schéma à une policy active. Le tri Portfolio départage les égalités par identifiant client, jamais par propension. La migration `0017` conserve dans le schéma Opportunity une sauvegarde technique des valeurs réécrites afin que son downgrade restaure exactement priorités, composants, explications, versions, policies et poids. Les champs ou alias `credit_score`, `risk_score`, `default_probability`, `credit_decision` et équivalents sont interdits.

Le monitoring conserve fenêtres/populations de référence, méthodes, valeurs, seuils `WARNING/BLOCKING`, statuts et alertes. La performance différée utilise uniquement des outcomes matures. Aucun drift ne déclenche automatiquement entraînement ou promotion.

### 11.6 Limites du pilote

Le pilote crée les tables de synchronisation et les tables ML/Feature Store décrites par les migrations versionnées. Il reste batch, PostgreSQL et CPU-only. Il exclut affectations secondaires, délégations, streaming, GPU, apprentissage en ligne, auto-réentraînement, auto-promotion, `HYBRID_CANDIDATE`, texte libre et LLM [2] [3]. Aucune performance ML de production n’est revendiquée à partir des données synthétiques.

## Références de l’extension

[2]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[3]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[4]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
