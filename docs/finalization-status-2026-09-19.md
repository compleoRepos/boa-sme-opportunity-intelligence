# Rapport final de finalisation technique

> **RAPPORT HISTORIQUE REMPLACÉ POUR LE ML.** Les passages `POC_ASSISTIVE`, `HYBRID_ML`, poids 65/35, récupération hybride et opportunités hybrides décrivent l’état du 19 septembre 2026. Depuis la migration `0017_ml_shadow_governance`, le mode est `POC_SHADOW`, la priorité est `RULES_ONLY`, les poids actifs sont règles `1` et ML `0`, et toute activation/promotion sans preuves BOA est bloquée. Utiliser [`final-status.md`](./final-status.md) et le lot 10 pour l’état courant.

**Produit :** BOA SME Opportunity Intelligence
**Date :** 19 septembre 2026
**Périmètre :** fusion UX premium Claude, socle ML CPU, gouvernance du scoring, résilience et préparation à l’industrialisation
**Environnement de preuve :** Docker Compose, PostgreSQL 16, Keycloak 25, FastAPI, React/TypeScript, CPU `x86_64`
**Données :** 500 PME exclusivement synthétiques ; aucune donnée BOA réelle
**Positionnement :** `POC_ASSISTIVE`, aucune décision de crédit, aucune revendication de performance ML de production

> **Décision synthétique.** Le socle technique est suffisamment gouverné, résilient, traçable et préparé pour recevoir de vraies données BOA dans un futur environnement contrôlé, sans masquer les travaux encore nécessaires avant production. Le produit n’est **pas prêt pour la production** : l’endpoint de readiness reste volontairement `BLOCKED`, faute de données et labels BOA, d’homologation DPO/Sécurité, d’infrastructure HA, de sauvegardes restaurées, de secrets de production et d’adaptateurs SI réels.

## 1. Résultat exécutif

| N° | Domaine | Statut | Conclusion vérifiée |
|---:|---|---|---|
| 1 | Fallback `RULES_ONLY` | **PASS** | Timeout, 5xx, indisponibilité, score absent ou obsolète n’empêchent plus la génération ; aucun score ancien ou inventé n’est utilisé. |
| 2 | Scoring Policy | **PASS** | Politique versionnée, simulée, soumise, approuvée séparément, activée et restaurée ; chaque opportunité conserve politique, version et poids. |
| 3 | Training / MLOps | **PASS — SOCLE** | Lignée, split temporel, run persistant, approbation, champion, retrait et rollback sont implémentés ; entraînement sur données BOA **non implémenté**. |
| 4 | Labels / outcomes | **PASS — MÉCANISME** | Outcomes structurés, maturité explicite, labels futurs versionnés, aucun entraînement automatique ; labels BOA réels insuffisants. |
| 5 | Data leakage | **PASS** | Lignée point-in-time par feature, checksum et test volontairement contaminé rejeté. |
| 6 | Évaluation ML | **PASS — FRAMEWORK** | Precision@K, Recall@K, PR-AUC, calibration, lift et uplift renvoient `N/A` si non calculables ; aucune performance synthétique n’est présentée comme réelle. |
| 7 | Monitoring / drift | **PASS — SOCLE** | Snapshots persistés, seuils configurables, états `OK/WARNING/CRITICAL`, audit et readiness ; alerting externe non branché. |
| 8 | Model Registry | **PASS** | Workflow persistant `REGISTERED → VALIDATING → SUBMITTED → APPROVED → CHAMPION → RETIRED`, promotion et rollback avec rôles séparés. |
| 9 | Isolation des données / SQL | **PASS — AUDIT CIBLÉ** | Le chemin Feature Store–ML utilise HTTP et le moindre privilège est testé ; les lectures SQL transverses restantes sont inventoriées et bloquent l’industrialisation complète. |
| 10 | Observabilité | **PASS — POC** | Corrélation de bout en bout, événements structurés, version modèle/policy et mode de fallback ; backend centralisé de logs non implémenté. |
| 11 | Résilience / performance | **PASS — 500 PME** | Batch Docker final de 500 PME sur CPU et preuve de reprise après panne ML ; 1 000/5 000 PME non exécutées et aucun SLO inventé. |
| 12 | Sécurité | **PASS — POC** | Keycloak/OIDC/RBAC, périmètres CC/agence, séparation Rule/ML/Scoring et tests de contournement ; homologation sécurité production non réalisée. |
| 13 | Audit | **PASS** | Règles, politiques, modèles, monitoring, fallback et décisions produisent des événements persistés avec acteur, trace et versions. |
| 14 | Production Readiness | **BLOCKED** | L’endpoint `/api/v1/admin/readiness` retourne explicitement `BLOCKED`, `POC_ASSISTIVE` et `productionPerformanceClaim=false`. |
| 15 | Données BOA / adapters | **PASS — CONTRATS MOCK** | Les dépendances restent synthétiques et remplaçables ; aucun raccordement CBS/CRM/Payments/Trade réel n’est simulé. |
| 16 | DPO / gouvernance data | **BLOCKED** | Documentation de finalité, minimisation, accès, traçabilité et conservation préparée ; validation juridique/DPO BOA requise. |
| 17 | Cloud / AWS | **NON IMPLÉMENTÉ** | Architecture cloud-agnostique documentée ; aucune ressource AWS créée artificiellement. |
| 18 | HA / backup / secrets | **NON IMPLÉMENTÉ** | Cible et runbook proposés sans RPO/RTO inventé ; aucune HA, restauration ni rotation de secrets de production démontrée. |
| 19 | Non-régression | **PASS** | Ruff, mypy, 119 tests backend, TypeScript, 15 tests frontend, build Vite, ShellCheck, Compose, validation ML, base vierge et 8/8 E2E passent. |

Aucun domaine exécuté n’est classé **FAIL**. Les statuts `BLOCKED` et `NON IMPLÉMENTÉ` sont des limites de production explicites, non des succès masqués.

## 2. Chaîne métier et technique validée

La chaîne réellement exécutée est :

```text
Customer / Analytics / Signals / Rule Engine
                    │
                    └── HTTP ──> Feature Store point-in-time
                                      │
                                      └── HTTP ──> ML Engine CPU
                                                       │
Rules candidates ──────────────────────────────────────┼──> Scoring Policy active
                                                       │        │
                                                       └────────┴──> Opportunity Engine
                                                                         │
                                                   HYBRID_ML ou RULES_ONLY│
                                                                         ▼
                                                           Portfolio Service
                                                               ├── Dashboard CC
                                                               ├── Dashboard agence
                                                               └── Fiche PME / actions / outcomes
```

Le Feature Store persiste `featureTimestamp`, `observationAsOf`, `sourcePeriod`, les références Rule Studio et Signals ainsi qu’un checksum. ML Engine persiste `modelVersion`, `featureVersion`, `trainingDatasetVersion`, `deploymentMode`, `traceId`, `asOf`, les contributions et la lignée. Opportunity Engine persiste `scoringPolicyId`, `scoringPolicyVersion`, `rulesWeight`, `mlWeight`, `engineVersion`, le mode `HYBRID_ML` ou `RULES_ONLY` et la cause structurée du fallback.

## 3. Détail des dix-neuf contrôles

### 3.1 Fallback `RULES_ONLY` — PASS

`ResilientMLClient` applique un timeout configurable, des retries bornés et un circuit breaker mémoire. Les cas ML nominal, timeout, HTTP 500, service indisponible, score absent, score obsolète et circuit ouvert sont couverts par tests unitaires. En échec terminal, `score=None`, les candidats Rules restent inchangés et Opportunity Engine persiste `RULES_ONLY`. Aucun score de base, ancien score, moyenne sectorielle ou valeur arbitraire n’est injecté.

La preuve Docker finale arrête complètement `ml-engine`, exécute le pipeline, redémarre le service, attend la fenêtre half-open puis rejoue le pipeline. L’audit persiste :

```text
final-rules-only|ML_FALLBACK_APPLIED|RULES_ONLY
final-hybrid-recovered|ML_SCORE_ACCEPTED|HYBRID_ML
```

**Fichiers clés :** `backend/src/boa_oi/resilience/ml_client.py`, `backend/src/boa_oi/opportunity_api.py`, `tests/unit/test_resilience.py`.

**Limite :** le circuit breaker est par processus ; une coordination distribuée et des alertes par instance seront nécessaires en déploiement multi-réplicas.

### 3.2 Opportunity Scoring Policy — PASS

Les poids métier ne proviennent plus de variables d’environnement. Une politique persistée porte `policyId`, version, poids, statut, fenêtre d’effet, auteur, approbateur, motif et audit. Le workflow implémenté est `DRAFT → SIMULATED → SUBMITTED → APPROVED → PUBLISHED → ACTIVE`, avec `DISABLED` et `ROLLED_BACK`. L’auteur ne peut pas approuver sa propre version. L’activation et le rollback retirent transactionnellement la version courante avant de restaurer la cible, afin de respecter l’unicité de l’actif.

Le test E2E réalise création, simulation, soumission, approbation par un autre rôle, activation puis rollback. Opportunity Service consomme la politique active ; Portfolio Service réutilise la priorité persistée et ne recalcule pas des poids parallèles.

**Fichiers clés :** `backend/src/boa_oi/scoring_policy/`, `backend/src/boa_oi/opportunity_api.py`, `database/migrations/versions/0006_governance_resilience.py`, `tests/unit/test_scoring_policy_domain.py`, `tests/e2e/governance.spec.ts`.

### 3.3 Training ML / MLOps — PASS pour le socle, données réelles non implémentées

Le socle conserve dataset, Feature Set, périodes d’entraînement/validation, révision code, hyperparamètres, métriques, auteur, date, statut et lignée point-in-time. Les runs et audits sont persistés. Le workflow de registre utilise des acteurs séparés pour création, validation, approbation, promotion et rollback. Un artefact non approuvé ne peut pas devenir champion ni être chargé par l’inférence.

La promotion synchronise transactionnellement le run MLOps et `model_registry`; le champion précédent devient `RETIRED`. Le rollback restaure un modèle précédemment approuvé. La suite E2E démontre ce cycle sur PostgreSQL réel.

Le modèle actif reste un **POC logistique synthétique CPU**. Il n’existe ni historique BOA réel, ni pipeline de calcul statistiquement exploitable, ni autorisation de mise en production.

**Fichiers clés :** `backend/src/boa_oi/mlops/`, `backend/src/boa_oi/ml/service.py`, `backend/src/boa_oi/mlops/routes.py`, migrations `0006` à `0008`, `tests/unit/test_mlops_domain.py`.

### 3.4 Labels / outcomes — PASS pour le mécanisme

Action Service conserve les états `À contacter`, `Contacté`, `Intéressé`, `Offre créée`, `Converti`, `Non intéressé` et `À revoir`. La matérialisation produit `customerId`, `opportunityId`, `opportunityType`, `actionId`, `outcomeLabel`, `observedAt`, `observationAsOf`, `labelAvailableFrom`, source et datasetVersion. Les états intermédiaires ne sont pas convertis en faux négatifs ; la cible binaire peut rester nulle. Une période de maturité est obligatoire.

La preuve finale lit deux événements outcomes synthétiques et écrit un label client unique pour `synthetic-commercial-outcomes-v1`. Elle renvoie `automaticTraining=false` et `trainingReady=false`. Ce faible volume n’est pas contourné.

**Fichiers clés :** `backend/src/boa_oi/action_api.py`, `backend/src/boa_oi/ml_engine_api.py`, `backend/src/boa_oi/models/entities.py`, `tests/unit/test_ml_engine.py`, `tests/e2e/rm-opportunity.spec.ts`.

### 3.5 Data leakage — PASS

Chaque feature porte `featureTimestamp`, `observationAsOf` et `sourcePeriod`; ces valeurs entrent dans le checksum. Le contrôle impose `featureTimestamp <= observationAsOf`. Un test injecte volontairement une observation postérieure à la date de référence et vérifie une erreur de contamination plutôt qu’un filtrage silencieux. Les splits temporels `TRAIN/VALIDATION/TEST` rejettent les exemples hors fenêtre.

**Fichiers clés :** `backend/src/boa_oi/features/domain.py`, `backend/src/boa_oi/mlops/domain.py`, `tests/unit/test_mlops_domain.py`.

### 3.6 Évaluation ML — PASS pour le framework, métriques réelles N/A

Le framework calcule Precision@K, Recall@K, PR-AUC, erreur de calibration, lift et uplift lorsque les entrées sont suffisantes. Toute métrique non calculable ou non statistiquement exploitable retourne `N/A`. Aucun écran ni rapport ne remplace `N/A` par une valeur flatteuse. Aucune qualité prédictive de production n’est revendiquée à partir des données synthétiques.

### 3.7 Monitoring / drift — PASS pour le socle

Les domaines `DATA`, `FEATURE`, `PREDICTION` et opérationnel disposent de seuils configurables `WARNING/CRITICAL`. Le système observe distributions, valeurs manquantes, scores, volume, latence, erreurs et taux `RULES_ONLY`. Les snapshots et audits sont persistés dans PostgreSQL ; l’E2E enregistre et relit des observations réelles. La stack contient actuellement dix snapshots de monitoring et cent dix événements d’audit de gouvernance.

**Limites :** aucun collecteur externe, dashboard d’exploitation ou canal d’alerte n’est connecté ; les seuils POC ne sont pas des seuils réglementaires ou SLO BOA.

### 3.8 Model Registry / promotion — PASS

Le registre porte version modèle, type, Feature Set, dataset, périodes, métriques, statut et mode de déploiement. Le workflow persistant est `REGISTERED → VALIDATING → SUBMITTED → APPROVED → CHAMPION → RETIRED`. Les rôles Data Analyst, reviewer et release manager sont séparés. Unicité du champion, promotion, remplacement, retrait et rollback sont testés sur PostgreSQL réel.

### 3.9 Isolation des données / SQL — PASS pour l’audit et le chemin critique

Le chemin d’inférence utilise des contrats HTTP authentifiés : Feature Store appelle Customer, Analytics, Signal et Rule Engine ; ML Engine appelle Feature Store. Le validateur confirme que Feature Store et ML Engine ne disposent plus des lectures inter-schémas supprimées. Le Gateway n’accède pas aux tables métier.

L’audit complet reste prudent : Portfolio Service, Analytics, Action et la construction des labels conservent des lectures SQL transverses ciblées. Elles sont documentées par service, schéma, table, niveau d’accès, justification et alternative API dans `docs/industrialization-governance.md`. Le passage à des projections/API et la suppression de `CREATE` pour tous les comptes runtime restent requis avant production.

### 3.10 Observabilité — PASS pour le POC

Les appels propagent `X-Correlation-ID`. Les événements structurés portent service, endpoint/action, résultat, traceId, modèle, Scoring Policy et fallback mode selon le contexte. Les logs de fallback ne contiennent ni secret ni token. Les preuves traversent Gateway, Rule Engine, Feature Store, ML Engine, Opportunity et Portfolio.

**Limite :** il n’existe pas encore de backend centralisé de logs/traces, de politique de rétention approuvée ou de corrélation inter-cluster.

### 3.11 Résilience / performance — PASS à l’échelle 500 synthétique

Le batch final exécute 500 PME par lots de 25 avec renouvellement du jeton de service. Il termine en **585 secondes** avec 500 clients distincts matérialisés dans le Feature Store, 500 clients distincts scorés et 614 opportunités courantes en mode hybride après les replays de validation. La stack reste CPU-only. Ce temps est une mesure sandbox, pas un SLO BOA. Le dataset de démonstration ne contient que 500 PME ; les runs 1 000 et 5 000 ne sont donc pas exécutés afin de ne pas dupliquer artificiellement des observations et présenter un faux test de charge.

Les pannes ML sont couvertes de bout en bout. Les pannes Feature Store, Rule Engine, Opportunity et PostgreSQL ont des contrats d’erreur mais ne constituent pas encore un plan de continuité multi-service complet.

### 3.12 Sécurité — PASS pour le POC

Keycloak/OIDC valide signature, issuer, audience et rôles. Le CC ne peut consulter que son portefeuille, le responsable d’agence seulement ses CC/agences, les auteurs et approbateurs Rule Studio sont séparés, la gouvernance ML sépare validation et release, et les fonctions administratives sont bloquées aux profils commerciaux. Les tests tentent des contournements par paramètres, chemins directs et endpoints alternatifs.

**Limites :** les mots de passe `DevOnly-*`, HTTP local, absence de coffre, absence de WAF/rate limit et absence d’homologation sont acceptables uniquement pour le développement.

### 3.13 Audit — PASS

Sont audités : cycle Rule Studio, Scoring Policy, modèle enregistré/validé/approuvé/promu/retiré/rollback, monitoring et fallback. Chaque événement porte au minimum timestamp, acteur ou service, action, ressource, corrélation/trace, résultat et métadonnées versionnées. Les décisions Opportunity conservent le hash et le contexte moteur.

**Limite :** l’immutabilité externe, l’archivage réglementaire et l’export vers un SIEM ne sont pas démontrés.

### 3.14 Production Readiness — BLOCKED

L’endpoint de readiness agrège `RULE_ENGINE`, `FEATURE_STORE`, `ML_ENGINE`, `OPPORTUNITY_ENGINE`, `SCORING_POLICY`, `MODEL_REGISTRY`, `MONITORING`, `FALLBACK`, `SECURITY`, `AUDIT`, `DATA_GOVERNANCE` et `OBSERVABILITY`. Une preuve manquante reste un échec ; le statut production ne peut pas être demandé arbitrairement. La réponse expose `POC_ASSISTIVE` et `productionPerformanceClaim=false`.

Les blocages sont : données historiques et labels BOA insuffisants, validation modèle indépendante absente, gouvernance DPO/Sécurité non approuvée, adaptateurs réels absents, HA/restauration/secrets/TLS de production non démontrés.

### 3.15 Données BOA / adapters — PASS pour les contrats mock

Aucune connexion CBS/CRM/Payments/Trade réelle n’est simulée. Les implémentations présentes sont clairement des mocks ou adaptateurs mémoire/HTTP synthétiques. `MockCBS`, `MockCRM`, `MockPayment` et `MockTrade` sont des noms de cible documentaire ; toutes les classes dédiées ne sont pas prétendues livrées. Les contrats de remplacement définissent source, date d’observation, schéma, corrélation, pagination, qualité et gestion explicite d’absence/erreur.

### 3.16 DPO / gouvernance data — BLOCKED

La documentation propose finalités, minimisation, catégories, accès, conservation, traçabilité et séparation entre données sources, dérivées et audit. Ces propositions ne valent pas validation juridique. Base légale, droits des personnes, durées, pays de traitement, transferts et classification doivent être validés par les fonctions BOA compétentes avant toute donnée réelle.

### 3.17 Cloud / AWS — NON IMPLÉMENTÉ

Aucune ressource AWS n’a été créée. La cible est cloud-agnostique : gateway, services, bus éventuel, PostgreSQL HA, stockage de sauvegarde, observabilité, secrets et certificats peuvent être déployés sur une plateforme BOA approuvée. Un futur choix AWS nécessitera comptes, IAM, réseau, KMS, secrets, observabilité, chiffrement et résidence validés.

### 3.18 HA / backup / secrets — NON IMPLÉMENTÉ

Docker Compose utilise un PostgreSQL unique et des secrets de développement. La documentation décrit une cible HA, sauvegardes complètes/incrémentales ou WAL, restauration, rotation, TLS, disaster recovery et gouvernance RPO/RTO. Aucun RPO/RTO n’est déclaré comme engagement. Aucun exercice de restauration d’un environnement de production ou équivalent n’est fourni.

### 3.19 Tests de non-régression — PASS

| Porte | Résultat final |
|---|---|
| Ruff format + lint | **PASS** |
| mypy | **PASS** |
| pytest backend | **PASS — 119 tests** |
| TypeScript | **PASS** |
| Vitest frontend | **PASS — 15 tests** |
| Build Vite | **PASS** |
| ShellCheck | **PASS** |
| Validation Compose / Keycloak | **PASS** |
| Script `validate-ml-integration.sh` | **PASS** |
| Playwright authentifié | **PASS — 8/8 en 50,1 s** |
| Migration PostgreSQL vierge | **PASS — `0001` à `0008_training_status`, 15 tables sur `ml/opportunity/audit`** |
| Services Docker | **PASS — 20/20 running et healthy** |
| Panne ML et récupération | **PASS — `RULES_ONLY` puis `HYBRID_ML`** |
| Batch 500 PME final | **PASS** |

## 4. État runtime vérifié

Après les tests finaux, PostgreSQL contient 500 matérialisations de features uniques à la date de référence, 500 clients distincts scorés lors du batch final, 614 opportunités courantes hybrides après les replays, cinq versions de Scoring Policy, des runs MLOps gouvernés, dix snapshots de monitoring, plus de cent événements d’audit de gouvernance et des labels outcomes synthétiques non training-ready. Ces compteurs reflètent les replays et tests du POC ; ils ne mesurent ni qualité métier ni performance réelle.

La migration complète sur une base PostgreSQL isolée et vide applique successivement `0001` à `0008_training_status`. La stack principale expose vingt services Compose, tous `running|healthy` après la validation.

## 5. Fichiers et modules principaux modifiés

| Zone | Fichiers clés | Objet |
|---|---|---|
| Résilience | `backend/src/boa_oi/resilience/`, `opportunity_api.py` | timeout, retry, circuit breaker, freshness, fallback sans cache |
| Scoring Policy | `backend/src/boa_oi/scoring_policy/`, `portfolio_api.py` | politique versionnée, workflow et consommation effective |
| MLOps / Registry | `backend/src/boa_oi/mlops/`, `ml/service.py`, `ml_engine_api.py` | runs, lignée, approbation, champion, rollback |
| Monitoring / Readiness | `backend/src/boa_oi/operations/` | drift, observations opérationnelles, audit et gate de production |
| Feature lineage | `features/domain.py`, `features/service.py`, `feature_store_api.py` | point-in-time et checksum |
| Persistance | `models/entities.py`, migrations `0006`, `0007`, `0008` | tables de gouvernance, lignée et statuts |
| Gateway / RBAC | `gateway_api.py`, Keycloak | proxies administratifs, rôles et frontières |
| Outcomes | `action_api.py`, `ml_engine_api.py`, `scripts/migrate.sh` | labels structurés et grants minimaux |
| Infrastructure | `docker-compose.yml`, `scripts/validate-ml-integration.sh` | paramètres techniques et validation reproductible |
| Tests | `test_resilience.py`, `test_scoring_policy_domain.py`, `test_mlops_domain.py`, `test_operations_*`, `governance.spec.ts`, E2E commerciaux/Rule Studio | régressions unitaires, intégration et RBAC |
| Documentation | `docs/industrialization-governance.md`, `docs/workstreams/`, ce rapport | limites, cible d’industrialisation et décision |

## 6. Conclusion et go/no-go

**GO pour conserver et démontrer le POC assistif gouverné sur données synthétiques.** Le cœur `Rules paramétrables + Feature Store + ML CPU + Opportunity Engine + dashboards CC/agence + actions/outcomes` fonctionne entièrement sans LLM, GPU ni appel IA externe. Une panne totale de ML n’empêche plus la production d’opportunités issues des règles.

**NO-GO pour la production BOA.** La readiness reste `BLOCKED`. Les prochaines décisions relèvent de BOA : disponibilité et qualité des données/labels, usages permis, validation modèle, DPO/juridique, sécurité, architecture cible, SI sources, HA, sauvegarde-restauration, secrets, TLS, SLO et homologation. Le signal de tension financière reste une indication commerciale à examiner humainement et ne devient jamais un score de crédit.
