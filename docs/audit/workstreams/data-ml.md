# Audit data et ML — BOA SME Opportunity Intelligence

> **Photographie historique antérieure aux migrations 0016/0017.** Les références à `POC_ASSISTIVE`, `HYBRID_ML`, Alembic `0008` et à l’absence d’exécution Docker ne décrivent plus l’état courant. Le lot 09 couvre l’ingestion gouvernée et le lot 10 impose `POC_SHADOW` avec priorité `RULES_ONLY`; les limites relatives aux historiques BOA et à la production restent valides.

**Périmètre.** Cet audit en lecture seule couvre les migrations Alembic, le seed, les données et leur catégorisation, le Feature Store, la lignée, la gouvernance MLOps, les labels, la qualité, le dataset d’apprentissage, le Model Registry, les métriques d’évaluation et le mode de secours « règles seules ». Le code n’a pas été modifié. Les vérifications combinent lecture du dépôt, exécution du manifeste de seed, inspection de l’historique Alembic et tests unitaires ciblés.

## Conclusion exécutive

Le dépôt fournit un **socle POC assistif cohérent et versionné**, mais pas une preuve de modèle entraîné ni de performance métier. Le seed est déterministe et couvre bien **500 PME, 25 chargés de clientèle (CC) et cinq agences**, avec huit secteurs et huit scénarios. La chaîne Alembic est linéaire de `0001` à `0008`; elle persiste les matérialisations Feature Store, les scores, les labels, les runs d’entraînement, la lignée, le registre et les événements de gouvernance. Le code de domaine protège l’intégrité temporelle, la maturité des labels et les transitions du registre.

La conclusion d’audit est toutefois **GO pour démonstration POC sur données synthétiques, NO-GO pour production BOA**. Le dépôt indique lui-même que l’entraînement BOA réel n’est pas implémenté, que les outcomes sont synthétiques et non utilisables pour entraîner le modèle, et que les compteurs runtime ne mesurent ni la qualité métier ni la performance réelle [9]. L’exécution runtime complète n’a pas pu être reconfirmée dans cet environnement : l’accès au démon Docker est refusé. Les résultats runtime décrits dans la documentation sont donc rapportés comme déclarations du dépôt, non comme observations indépendantes de cette session.

## Tableau de synthèse

| Domaine audité | Constat | Niveau de preuve |
|---|---|---|
| Migrations | Une chaîne unique `0001` → `0008`; la commande `alembic heads` renvoie `0008_training_status`. | Vérifié statiquement et par commande locale |
| Seed et périmètre | 500 PME, au moins 300 000 transactions, 25 CC, cinq agences, huit secteurs et huit scénarios. | Vérifié par code, manifeste exécuté et calcul de répartition |
| Feature Store et lignée | `as_of_date`, version de features, sources, lignée et checksum sont persistés; le score conserve les versions et un trace ID. | Vérifié dans code et migrations |
| Gouvernance / registre | Cycle contrôlé, approbation obligatoire, champion unique en base, rollback et audit prévus. | Vérifié dans code et migrations; runtime non reconfirmé |
| Labels / dataset | Les structures existent, mais les outcomes du seed sont synthétiques et explicitement non training-ready; aucun entraînement BOA réel n’est fourni. | Vérifié dans documentation et schémas |
| Qualité / données dégradées | Contrôles de temporalité, maturité, fraîcheur et fallback explicite; certaines garanties restent documentaires ou dépendantes du runtime. | Partiel |
| Métriques | Precision@K, Recall@K, PR-AUC, erreur de calibration, lift et uplift optionnel. Pas de matrice de confusion ni de comparaison modèle/règles matérialisée dans cette API. | Vérifié dans code; aucune valeur de performance indépendante constatée |
| Règles seules | `RULES_ONLY` est le seul secours opérationnel documenté, sans score ML synthétique. | Vérifié dans code/documentation; persistance runtime non reconfirmée |

## 1. Migrations Alembic et persistance

La chaîne Alembic est sans branche apparente : `0001_initial` est la base, puis `0002_service_api_persistence`, `0003_rule_studio`, `0004_ml_and_portfolio`, `0005_ml_integration_trace`, `0006_governance_resilience`, `0007_training_run_lineage` et `0008_training_status`. La commande locale `cd database && alembic heads` a renvoyé `0008_training_status`; `alembic history --verbose` a confirmé les parents successifs [1]. Les migrations `0007` et `0008` ajoutent respectivement `ml.training_runs.lineage_json` et l’état `REGISTERED` dans la contrainte de statut [2] [3].

La migration ML crée ou étend notamment les objets de matérialisation de features, registre de modèles, scores de propension, snapshots de labels, runs d’entraînement, snapshots de monitoring et journaux de gouvernance [4]. `0006` ajoute aussi une politique de scoring hybride versionnée avec poids normalisés et un audit de politique; le bootstrap est explicitement décrit comme POC et non comme approbation de production [5].

**Limite.** La migration sur une base PostgreSQL runtime n’a pas été rejouée pendant cet audit. Docker est installé mais l’accès à `/var/run/docker.sock` a échoué avec `permission denied`. La documentation finale affirme qu’une base vide a accepté `0001` à `0008`, mais cette assertion n’est pas une observation indépendante de la présente session [9].

## 2. Seed, volumes, agences, CC et catégorisation

Le manifeste exécuté depuis `database.seed.generate` retourne : `customers: 500`, `minimum_transactions: 300000`, période `2025-10-01` à `2026-09-30`, huit secteurs, huit scénarios et `opportunities: 0`. Le test de seed vérifie également au moins 365 jours de période et une génération déterministe d’au moins 300 000 transactions [6]. Le générateur refuse de terminer si le nombre de transactions produit est inférieur au seuil [7].

La fonction d’affectation utilise par défaut `manager_count=25` et documente une affectation volontairement inégale. Le calcul sur les 500 index a produit les effectifs CC suivants : CC1 `65`, CC2 `52`, CC3 `49`, CC4 `48`, CC5 `36`, CC6–CC15 `13` chacun, puis CC16–CC25 `12` chacun. Les cinq libellés d’agence sont `BR-01 Casablanca Anfa`, `BR-02 Casablanca Sidi Maârouf`, `BR-03 Rabat Agdal`, `BR-04 Tanger Zone Franche` et `BR-05 Marrakech Guéliz` [8]. La documentation du seed précise que BR-01 regroupe les CC1 à CC5 et concentre la moitié du portefeuille; cette concentration est donc un choix de démonstration, pas une distribution représentative.

La catégorisation métier comprend huit secteurs (`INDUSTRIE`, `IMPORT_EXPORT`, `DISTRIBUTION`, `SERVICES`, `BTP`, `AGRICULTURE`, `COMMERCE`, `TECHNOLOGIE`) et huit scénarios (`GROWTH_COMPANY`, `STABLE_COMPANY`, `INTERNATIONAL_GROWTH`, `CASH_SURPLUS`, `FINANCIAL_STRESS`, `NORMAL_CUSTOMER`, `FALSE_POSITIVE_SEASONAL`, `FALSE_POSITIVE_ONE_OFF`). Le calcul exécuté donne entre 62 et 63 PME par scénario. Les noms, personnes, agences et faits sont explicitement synthétiques, déterministes et non rattachés à des entités réelles [8].

**Appréciation qualité du seed.** La reproductibilité, la densité transactionnelle, la couverture des catégories et la présence de faux positifs scénarisés sont démontrées. En revanche, ce seed ne démontre ni représentativité statistique, ni qualité d’une source bancaire réelle, ni couverture de valeurs manquantes, corrections, doublons ou retards de production au niveau d’un système source réel.

## 3. Feature Store et lignée de bout en bout

Une matérialisation Feature Store est identifiée par client, date `as_of_date` et `feature_set_version`. Elle persiste `values_json`, `sources_json`, `lineage_json` et un checksum; le service conserve ces champs lors de l’écriture [10]. Les sources peuvent inclure les snapshots analytiques, le profil client, les signaux et les règles publiées. Le score ML reprend `model_version`, `feature_set_version`, `feature_checksum`, `training_dataset_version`, `deployment_mode` et `prediction_trace_id` [11]. Cette structure permet de relier une décision à une version de features, une version de dataset déclarée, un modèle et un identifiant de trace.

Le domaine MLOps impose en outre que `featureTimestamp <= observationAsOf`; une contamination temporelle est signalée par exception et non supprimée silencieusement. La politique de dataset prévoit un découpage chronologique `TRAIN`, `VALIDATION`, `TEST`, avec rejet d’une observation postérieure à la borne de test. La lignée d’entraînement porte les exemples, la version du Feature Set, les snapshots sources, la révision du code, la définition de label et la date de coupure [12].

**Limite.** La présence des colonnes et des contrôles ne prouve pas que chaque ligne runtime a été effectivement alimentée avec une lignée complète. La documentation signale des exigences de traçabilité transactionnelle de l’outbox encore à renforcer; l’audit runtime n’a pas pu lire PostgreSQL dans cette session [13].

## 4. Gouvernance MLOps et Model Registry

Le registre de domaine impose le cycle `REGISTERED → VALIDATING → SUBMITTED → APPROVED → CHAMPION → RETIRED`. L’approbation requiert un acteur; la promotion exige une approbation enregistrée; un nouveau champion retraite l’ancien et le rollback peut restaurer un modèle retiré [14]. Côté base, `0006` introduit les champs de période d’entraînement et de validation, hyperparamètres, approbateur et dates, ainsi qu’un index unique conditionnel garantissant un seul statut `CHAMPION` [5]. Les runs possèdent une lignée JSON persistée depuis `0007`, et leur contrainte de statut inclut `REGISTERED` depuis `0008` [2] [3].

Les snapshots de monitoring contiennent un domaine, une métrique, une valeur, un statut, des seuils, une date d’observation et un trace ID; les journaux de gouvernance contiennent l’action, l’objet, les valeurs avant/après, l’acteur, la raison et la trace [4]. Ces structures constituent un bon socle d’auditabilité.

**Limites de gouvernance.** Le registre local et l’adaptateur SQL sont des composants du dépôt; aucun registre externe n’est connecté. Le modèle est donc « enregistré » dans la persistance applicative, mais cela ne constitue pas une homologation indépendante. Le document d’état maintient la readiness `BLOCKED` pour la production, notamment en attente de données/labels réels, de validation modèle, de gouvernance data, de sécurité et de continuité [9].

## 5. Labels et dataset d’apprentissage

Les labels possèdent une observation, une date de disponibilité, une définition, un horizon et une maturité. `assess_label_maturity` distingue `MATURE`, `IMMATURE` et `MISSING`; l’apprentissage n’est prêt que lorsque les labels nécessaires sont matures [12]. Le schéma SQL persiste `snapshot_version`, `dataset_version`, `observation_as_of`, `label_available_from`, `outcome_label`, `outcome_value`, la source et les références d’opportunité/action [4].

Le point bloquant est la nature des données : le document final qualifie les outcomes de **synthétiques et non training-ready**, et indique que l’entraînement BOA réel reste non implémenté [9]. L’application expose bien un `trainingDatasetVersion` dans les scores et le registre, mais ce champ assure la traçabilité déclarative; il ne prouve pas qu’un dataset réel, suffisamment mature, versionné et approuvé a servi à entraîner le modèle. Le service de sérialisation marque d’ailleurs `productionPerformanceClaim: false` et `automaticTraining: false` [11].

## 6. Qualité, données dégradées et catégorisation

Le dépôt traite plusieurs dégradations importantes : la contamination temporelle est détectée; la maturité incomplète interdit la préparation à l’entraînement; les métriques renvoient `N/A` lorsque les entrées sont absentes, mal formées, dégénérées ou insuffisantes; les snapshots analytiques portent un état de qualité [12] [15]. Les contrats d’intégration prévoient également la vérification de présence, bornes et fraîcheur des scores, avec bascule si le score est absent ou obsolète [16].

Le contrôle n’est cependant pas uniforme au niveau d’une preuve d’exploitation. Les seuils opérationnels, la réaction à chaque type de qualité dégradée, les valeurs observées par source et l’historique des alertes ne sont pas consultables sans base runtime. La documentation d’industrialisation demande encore de valider les systèmes sources, la fraîcheur, les codes produit, les absences et les rejouabilités avec des adaptateurs homologués [17]. Il faut donc distinguer **contrôles implémentés** et **qualité empirique démontrée** : seule la première est établie ici.

## 7. Métriques, calibration, confusion et comparaison

La fonction d’évaluation expose `Precision@K`, `Recall@K`, `PR-AUC`, erreur de calibration de type ECE à dix intervalles, lift et, si un traitement est fourni, uplift entre groupes traité et contrôle [12]. La précision et le rappel sont calculés au top-K; la PR-AUC est renvoyée lorsque le calcul est possible; les entrées non utilisables sont explicitement marquées `N/A` [15].

Deux limites doivent être signalées précisément :

1. **Calibration.** Le score d’inférence conserve une bande qualitative `LOW`, `MEDIUM` ou `HIGH` selon des seuils de propension. Cette bande n’est pas une calibration empirique. L’erreur de calibration existe comme métrique d’évaluation du domaine, mais aucune valeur indépendante et reproductible sur un dataset mature n’a été fournie dans les éléments vérifiés.
2. **Confusion et comparaison.** La structure `MetricReport` et `evaluate_metrics` exposent les métriques ci-dessus, mais pas une matrice de confusion (`TP`, `FP`, `TN`, `FN`) ni une comparaison persistée « modèle ML contre règles seules ». Le seed contient des scénarios de faux positifs, ce qui facilite un futur test, mais ne constitue pas à lui seul une matrice de confusion ni une mesure comparative. Les documents refusent explicitement toute revendication de performance réelle [9] [11].

En conséquence, l’audit confirme la **capacité de calcul** de plusieurs métriques, mais pas un résultat de performance, une calibration validée, une confusion mesurée ou un gain démontré par rapport aux règles.

## 8. Mode « règles seules » et dégradation contrôlée

Le contrat de résilience définit `HYBRID_ML` comme une tentative de score ML courant, suivie d’une bascule explicite vers les règles si le score est absent, incompatible, obsolète ou si la dépendance échoue. `RULES_ONLY` est le seul résultat opérationnel de secours; aucun score synthétique, cache ancien ou moyenne par défaut ne doit être produit [16]. L’explication doit conserver le mode, la cause du fallback et l’événement d’audit. Le circuit breaker est volontairement mémoire et par instance; la cohérence inter-workers n’est pas supposée [16].

Cette conception est adaptée à un POC assistif : la panne ML ne doit pas empêcher la production d’opportunités issues des règles. Elle ne suffit pas encore à une garantie de production, car la documentation identifie le sink d’audit comme best-effort et recommande une outbox persistante transactionnelle et idempotente [16]. Le script de validation prévoit des assertions sur les 500 matérialisations, les 500 scores, la lignée Rule Studio/Signal, la trace modèle/features/dataset et l’absence de privilèges SQL croisés [18]; ces assertions n’ont pas été exécutées dans cette session faute d’accès Docker/PostgreSQL.

## Limites et points à traiter avant toute décision de production

Les preuves établissent un POC reproductible sur données synthétiques. Elles n’établissent pas :

- un dataset d’apprentissage réel, mature, approuvé et représentatif;
- un entraînement BOA reproductible ou une validation indépendante du modèle;
- des valeurs de calibration, de matrice de confusion ou de comparaison ML/règles;
- une qualité runtime mesurée sur les sources réelles, y compris retards, valeurs manquantes et catégories inconnues;
- l’exécution indépendante de la migration et du pipeline PostgreSQL dans la présente session;
- la persistance transactionnelle et idempotente de chaque événement de fallback;
- la readiness production, que le dépôt classe lui-même `BLOCKED` [9].

**Décision d’audit.** Conserver le périmètre pour démonstration et tests contrôlés. Ne pas présenter la propension comme une performance validée, ni comme une décision de crédit. Avant production, obtenir les validations data, juridique/DPO, sécurité et gouvernance; intégrer des labels observés et matures; produire un dataset manifesté; exécuter une validation temporelle indépendante; ajouter la matrice de confusion et la comparaison règles/ML; puis reconfirmer les migrations, les privilèges, la qualité et le fallback sur un environnement PostgreSQL représentatif.

## Références

[1]: ../../../database/alembic.ini "Configuration Alembic et chaîne de migration vérifiée"
[2]: ../../../database/migrations/versions/0007_training_run_lineage.py "Migration de lignée des runs d’entraînement"
[3]: ../../../database/migrations/versions/0008_training_run_registered_status.py "Migration du statut REGISTERED"
[4]: ../../../database/migrations/versions/0004_ml_and_portfolio.py "Objets persistants Feature Store, ML, labels et runs"
[5]: ../../../database/migrations/versions/0006_governance_resilience.py "Gouvernance, monitoring et politique de scoring"
[6]: ../../../tests/unit/test_models_seed_api.py "Contrats unitaires du seed et du modèle"
[7]: ../../../database/seed/generate.py "Générateur de données synthétiques et seuil de transactions"
[8]: ../../../database/seed/naming.py "Affectation PME-CC, agences et catégorisation"
[9]: ../../finalization-status-2026-09-19.md "État final et limites de production du POC"
[10]: ../../../backend/src/boa_oi/feature_store_api.py "Persistance des matérialisations et lignée Feature Store"
[11]: ../../../backend/src/boa_oi/ml/service.py "Sérialisation du modèle et des scores ML"
[12]: ../../../backend/src/boa_oi/mlops/domain.py "Lignée, labels, splits, métriques et registre"
[13]: ../../workstreams/mlops-governance.md "Gouvernance MLOps et limites de traçabilité"
[14]: ../../../backend/src/boa_oi/mlops/domain.py "Transitions et rollback du Model Registry"
[15]: ../../../backend/src/boa_oi/models/entities.py "Champs persistants de qualité, features et scores"
[16]: ../../workstreams/fallback-rules-only.md "Politique de fallback RULES_ONLY et limites"
[17]: ../../industrialization-governance.md "Conditions d’industrialisation et validation des sources"
[18]: ../../../scripts/validate-ml-integration.sh "Assertions de validation de l’intégration ML"

> **Reproductibilité de l’audit.** Les tests ciblés exécutés sont `PYTHONPATH=backend/src:. pytest -q tests/unit/test_mlops_domain.py tests/unit/test_ml_engine.py tests/unit/test_models_seed_api.py` : **20 tests passés**, avec six avertissements FastAPI sur des Operation IDs dupliqués. Aucun fichier de code n’a été édité.

> **Limite d’accès runtime.** `docker compose ps` n’a pas pu interroger le démon Docker dans cet environnement (`permission denied` sur `/var/run/docker.sock`). Les compteurs PostgreSQL et les assertions du script d’intégration ne sont donc pas revalidés ici.

**Statut global : POC assistif gouverné sur données synthétiques — acceptable pour démonstration; production BOA non autorisée sur la base des preuves disponibles.**
