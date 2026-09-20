# Lot 10 — ML shadow défendable, outcomes candidats et garde-fous d’activation

**Auteur :** Manus AI
**Date :** 2026-09-20
**Branche :** `feat/pilot-readiness`
**Statut du lot :** **PASS technique en `POC_SHADOW` ; entraînement, calibration et activation BOA BLOCKED**

## 1. Décision de lot

Le lot valide une chaîne exécutable **Rules → Signals/Features → inférence ML → Opportunity → dashboards** sur 500 PME synthétiques. Les 500 inférences ont été observées en `POC_SHADOW`, sans repli, tandis que la génération, le classement et l’affichage des priorités commerciales sont restés strictement `RULES_ONLY`. Le score de propension est conservé pour observation et traçabilité. Il ne crée, ne supprime, ne départage et ne réordonne aucune opportunité.[1]

Cette validation ne transforme pas le POC en modèle entraîné ou validé par BOA. La fixture ne contient aucun outcome commercial. Le protocole n’en invente donc aucun : zéro label candidat a été matérialisé. Le manifeste point-in-time et l’évaluation restent `BLOCKED` avec le motif `BOA_HISTORICAL_LABELS_UNAVAILABLE`. Les valeurs Brier et ECE enregistrées proviennent de deux paires synthétiques explicites qui testent uniquement la persistance et les garde-fous. Elles ne mesurent aucune performance BOA ou production.[1]

Le produit ne prend aucune décision de crédit. Il fonctionne sans LLM, sans GPU et avec un modèle classique déterministe exécuté sur CPU. Toute activation ultérieure d’un poids ML non nul exige des labels historiques BOA gouvernés, une évaluation temporelle reproductible, une calibration validée, des critères approuvés et une décision humaine distincte. Ces conditions sont **NON SATISFAITES** dans ce lot.

## 2. Périmètre livré et statut réel

| Capacité | Statut | Preuve ou limite |
|---|---|---|
| Rule Studio actif dans la chaîne | **IMPLÉMENTÉ / PROUVÉ** | une règle synthétique publiée apparaît dans `activeRuleVersions`; au moins une matérialisation contient également sa version dans `matchedRuleVersions` |
| Signals et Features consommés par le ML | **IMPLÉMENTÉ / PROUVÉ** | 500 vecteurs `sales-features-v2`; lineage Signal Service et Rule Studio persisté |
| Inférence classique CPU-only | **IMPLÉMENTÉ / PROUVÉ** | 500 scores frais, conteneur limité à `0,60` CPU et `384 MiB`, aucun device GPU |
| LLM/GPU au runtime | **ABSENT / PROUVÉ** | aucun package ou service LLM/GPU, variables CUDA/NVIDIA neutralisées |
| Lineage de prédiction | **IMPLÉMENTÉ / PROUVÉ** | modèle, feature set, dataset, manifest hash, artifact checksum, mode et instant d’inférence persistés |
| Influence ML sur Opportunity | **DÉSACTIVÉE / PROUVÉ** | poids actif `rules=1`, `ml=0`; priorité persistée et tri backend/frontend indépendants de la propension |
| Dashboards CC/agence | **IMPLÉMENTÉ / PROUVÉ E2E** | score présenté comme observation shadow; priorité et ordre explicitement issus des règles |
| Outcomes comme labels candidats | **IMPLÉMENTÉ STRUCTURELLEMENT** | définition de cible, horizon, population, source et snapshot versionnés |
| Labels réels disponibles | **NON DISPONIBLES** | zéro outcome dans la fixture; aucune donnée BOA inventée |
| Dataset point-in-time | **IMPLÉMENTÉ / BLOCKED** | manifest persistant et contrôles anti-fuite; statut bloqué faute de labels BOA |
| Évaluation/calibration | **IMPLÉMENTÉE STRUCTURELLEMENT / NON VALIDÉE** | Brier/ECE persistés avec provenance; statut `NOT_VALIDATED`; valeurs synthétiques non interprétables comme performance |
| Promotion ou policy hybride active | **BLOQUÉE** | gates applicatifs et SQL; une policy hybride peut être simulée, jamais activée dans l’état actuel |
| Décision de crédit | **HORS PÉRIMÈTRE / INTERDITE** | vocabulaire de seed contrôlé; signaux présentés comme éléments à examiner |
| Seuil de règle synthétique | **HYPOTHÈSE À VALIDER AVEC BOA** | seuil de croissance uniquement destiné à la démonstration autonome du Rule Studio |

## 3. Chaîne d’intégration effectivement exécutée

Le générateur public initialise désormais une règle Rule Studio active nommée `SYNTHETIC_GROWTH_REVIEW`. Sa description et son scope la qualifient explicitement de donnée synthétique. Son seuil n’est ni une politique BOA ni une valeur recommandée. Il sert uniquement à rendre le bootstrap autonome et à démontrer que le Rule Studio publié produit une source consommable par le Feature Store.

Pour chaque client, Analytics et Signal Service recalculent les observations à la date du `2026-09-30`. Le Feature Store matérialise ensuite dix features. La feature `published_rule_match_strength` est produite à partir du résultat Rule Studio; son lineage contient les versions actives et correspondantes. Le ML Engine consomme ce vecteur et écrit un score shadow avec son lineage immuable. Opportunity appelle réellement le ML Engine, mais conserve le mode opérationnel `RULES_ONLY`. Portfolio et les dashboards n’utilisent plus la propension comme composante, filtre ou départage.

Le protocole final a traité 500 clients en 20 lots. Il a enregistré **500 observations `POC_SHADOW` et zéro repli `RULES_ONLY` dû à une indisponibilité ML**. Il a persisté 500 vecteurs et 500 scores frais. À la fin du run, la base locale contenait 564 opportunités cumulées après les validations précédentes et les E2E. Ce total n’est donc pas une mesure par run; il ne constitue ni un objectif métier ni une volumétrie BOA.[1]

## 4. Garde-fous ML et outcomes

La migration `0017` verrouille les enregistrements de modèle et de score en `POC_SHADOW`. Elle neutralise les anciennes priorités hybrides en recalculant les valeurs opérationnelles à partir des seules composantes règles. Elle remplace également la policy active par `commercial-rules-shadow-poc`, avec un poids règles égal à `1` et un poids ML égal à `0`.[2]

Les outcomes commerciaux restent persistés par le produit et peuvent devenir des labels candidats. Leur matérialisation exige une définition versionnée de la cible, un horizon, une population, une provenance et une date de disponibilité strictement postérieure à l’observation. Une source locale ou synthétique ne peut pas être déclarée `TRAINING_READY`. Dans la preuve finale, aucun outcome n’existe; le statut exact est donc **`NOT_AVAILABLE`**, et non `PASS`.

Le manifeste de dataset contrôle notamment la disponibilité effective des sources, l’unicité des exemples, l’absence de feature postérieure à l’observation et la disponibilité future du label. Le service MLOps exige ensuite que le manifeste, le snapshot de labels et l’évaluation existent réellement en base et correspondent au run. Les métriques de calibration doivent être numériques et bornées. Les critères doivent être approuvés par un acteur distinct. Malgré ces structures, la promotion reste bloquée dans ce lot parce que les preuves BOA requises n’existent pas.

## 5. Preuve exécutable finale

Le protocole [`validate-ml-integration.sh`](../../scripts/validate-ml-integration.sh) exécute lui-même la chaîne complète sur 500 PME. Il ne se contente pas de compter des lignes historiques. Il ouvre une fenêtre de mesure, rejoue Analytics, Signals, Feature Store, ML et Opportunity, puis exige 500 réponses shadow et zéro fallback. Il contrôle ensuite la priorité rules-only, le lineage, les permissions SQL, les policies, les manifests, les évaluations, le runtime CPU-only et l’absence de dépendance LLM/GPU.[1]

| Mesure ou contrôle | Résultat final |
|---|---|
| Run | `ml-shadow-20260920T030321Z-2337894` |
| Statut | **PASS** |
| Clients / lots | `500 / 20` |
| Vecteurs / scores frais | `500 / 500` |
| Observations shadow / fallbacks | `500 / 0` |
| Opportunités présentes en base à la fin | `564` — cumul local, pas une mesure par run |
| Labels candidats matérialisés | `0 — NOT_AVAILABLE` |
| Manifest dataset | `BLOCKED — BOA_HISTORICAL_LABELS_UNAVAILABLE` |
| Calibration | `NOT_VALIDATED` |
| Claim performance production | `false` |
| Claim décision de crédit | `false` |
| LLM / GPU | `false / false` |

L’artefact final est [`RESULTATS-ML-SHADOW.json`](../evidence/ml/RESULTATS-ML-SHADOW.json). Son SHA-256 est `99d43e87aae09f1414dcbcd13e207094c3bd361ff80e7943aa213f272093ff7b`. Il référence le commit de base `050a541084e48f4b8cb6766760ebd57d668e86d0` et un digest reproductible de 44 fichiers runtime/protocole : `8ebaa58edebeb9433b2e040d9cbf072d706ac8d3c995071df27c129d647339ec`. Ce digest a été recalculé indépendamment avec succès. Le manifeste d’intégrité est [`SHA256SUMS.txt`](../evidence/ml/SHA256SUMS.txt).[1] [3]

## 6. Migration et rollback

Le protocole [`validate-ml-migration-rollback.sh`](../../scripts/validate-ml-migration-rollback.sh) utilise deux bases PostgreSQL isolées. Il applique `0001→0017` sur une base vierge. Il clone ensuite la fixture, vérifie la neutralisation shadow, redescend de `0017` à `0016`, compare exactement les valeurs métier sauvegardées, puis réapplique `0017`. Il contrôle aussi l’unicité de la policy active et la validité de sa fenêtre temporelle.[2]

Les six contrôles sont **PASS** dans le run `ml-migration-rollback-20260920T024930Z`. L’artefact [`RESULTATS-MIGRATION-ML-SHADOW.json`](../evidence/ml/RESULTATS-MIGRATION-ML-SHADOW.json) a pour SHA-256 `ff33c550eb6a5fb680024a716c04bffa6b78495b056492660f3faf8b9c6cbe83`.[2] [3]

## 7. Porte de livraison

| Porte | Résultat final |
|---|---|
| Ruff format/lint | **PASS** — 139 fichiers, aucun écart |
| mypy | **PASS** — 80 fichiers backend et 2 validateurs |
| pytest backend | **PASS** — 235 tests, 7 avertissements non bloquants |
| ShellCheck | **PASS** — scripts du dépôt |
| frontend typecheck | **PASS** — `tsc -b` direct sur le lockfile existant |
| frontend Vitest | **PASS** — 7 fichiers, 26 tests |
| frontend Vite build | **PASS** — 2 286 modules, 5,63 s |
| Compose / Keycloak / syntaxe scripts | **PASS** |
| preuve ML shadow 500 | **PASS** |
| migration vierge / downgrade / ré-upgrade | **PASS** |
| Playwright E2E | **PASS** — 19 tests |
| intégrité SHA-256 | **PASS** |

Le wrapper `pnpm` de l’environnement a refusé une installation implicite à cause de sa politique locale sur le script de build `esbuild`. Cette erreur est antérieure à TypeScript et ne constitue pas un échec applicatif. La porte frontend a été exécutée avec les binaires déjà verrouillés dans `frontend/node_modules`, puis le build Docker et les 19 E2E ont réussi.

Le premier lancement Playwright utilisait par erreur le binaire du frontend alors que `tests/e2e` possède sa propre installation. Il a été rejeté pour double instance de Playwright. Le lancement de référence avec `tests/e2e/node_modules` a ensuite exécuté les 19 scénarios. Une assertion attendait encore le libellé obsolète « Seuil de décision »; elle a été alignée sur « Seuil descriptif POC ». La suite complète finale est **PASS 19/19**.

## 8. Écarts détectés et corrigés pendant la validation

La validation sur base vierge a révélé que le seed autonome ne créait aucune règle Rule Studio active. Le bootstrap pouvait donc produire des features de règles, mais sans version publiée réelle. Une règle synthétique explicitement gouvernée a été ajoutée, puis la base a été recréée depuis `0001` avant la preuve finale.

Le premier materialize CPU pouvait dépasser le timeout inter-service de deux secondes. Le retry démarrait alors pendant que la première transaction détenait encore son verrou advisory et recevait un `409`. Le timeout Docker par défaut est désormais de dix secondes. Ce réglage fiabilise le bootstrap local; il ne constitue pas un SLO de production et reste **À VALIDER AVEC BOA** pour tout environnement cible.

Enfin, l’adaptateur d’une règle Studio correspondante créait une ligne de traçabilité dans le registre Opportunity. Le run suivant tentait à tort de revalider cette ligne comme une configuration technique statique. Le chargeur exclut désormais explicitement les lignes `source=rule-studio`, et un test de non-régression couvre ce cas. Aucun seuil d’acceptation ou critère ML n’a été assoupli pour obtenir le PASS.

## 9. Limites et décision d’activation

> **Le résultat de ce lot est une preuve d’intégration shadow sur données locales/synthétiques. Il ne prouve ni performance ML BOA, ni calibration BOA, ni capacité de production, ni homologation, ni décision de crédit.**

Le modèle reste un baseline classique CPU destiné au POC. Les coefficients synthétiques, le seuil descriptif, la volumétrie de 500 PME et les deux paires de l’évaluation technique ne sont pas des résultats métier. Toute valeur à retenir pour le pilote est une **HYPOTHÈSE À VALIDER AVEC BOA**.

L’activation ML doit rester **BLOCKED** tant que BOA n’a pas fourni et gouverné des outcomes historiques, validé la définition de la cible et l’horizon, approuvé le découpage temporel, mesuré la calibration et les métriques pertinentes, défini des seuils d’acceptation, réalisé les revues conformité/risque, et autorisé formellement une expérimentation qui demeure sans décision de crédit. Le produit actuel peut être utilisé en pilote shadow pour collecter ces éléments sans modifier le classement commercial.

## 10. Contre-revue P0/P1

La contre-revue indépendante n’a relevé aucun P0 et un P1 de provenance. Le premier digest couvrait les services modifiés, la migration, le seed, l’interface et le protocole, mais omettait les implémentations Feature Store, Rule Engine et stratégies Opportunity exécutées sans modification dans la chaîne. La liste a été étendue à ces modules ainsi qu’aux routes de scoring policy, puis le protocole complet 500 PME a été rejoué. L’artefact final couvre désormais 44 fichiers et son digest a été recalculé indépendamment. Le P1 est **FERMÉ**.

## Références

[1]: ../evidence/ml/RESULTATS-ML-SHADOW.json "Résultats de la validation intégrée ML shadow sur 500 PME synthétiques"
[2]: ../evidence/ml/RESULTATS-MIGRATION-ML-SHADOW.json "Résultats de migration, neutralisation shadow et rollback exact de 0017"
[3]: ../evidence/ml/SHA256SUMS.txt "Manifestes SHA-256 des preuves ML du lot 10"
