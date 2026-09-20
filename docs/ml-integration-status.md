# Rapport de validation d’intégration ML

> **RAPPORT HISTORIQUE REMPLACÉ — NE PAS UTILISER COMME ÉTAT COURANT.** Cette photographie documente l’ancien reranking synthétique 65/35. La migration `0017_ml_shadow_governance` l’a désactivé : le mode courant est `POC_SHADOW`, la priorité est `RULES_ONLY`, les poids actifs sont règles `1` et ML `0`, et les priorités historiques ont été recalculées sans composante ML. Utiliser le rapport du lot 10 et sa preuve JSON sous `docs/evidence/ml/`. Les chiffres, claims hybrides et statuts ci-dessous restent uniquement une trace datée du 19 septembre 2026.

**Produit :** BOA SME Opportunity Intelligence
**Date d’exécution :** 19 septembre 2026
**Branche :** `feat/ml-integration-validation`
**Environnement :** Ubuntu Linux `x86_64`, Docker Compose, PostgreSQL 16, Keycloak 25, Python 3.12.7, CPU uniquement
**Dataset :** `synthetic-demo-20260918-v1`, 500 PME synthétiques, aucune donnée bancaire réelle
**Mode :** `POC_ASSISTIVE`, aucune revendication de performance ML de production

> Le score est une **propension commerciale** utilisée pour prioriser des candidates déjà éligibles. Il ne constitue ni un score de crédit, ni une probabilité de défaut, ni une décision d’octroi, de refus, de limite ou de tarification. `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner par un humain.

## 1. Résultat des dix contrôles demandés

| N° | Contrôle | Statut | Preuve exécutée |
|---:|---|---|---|
| 1 | Rule Studio et Signals alimentent réellement les features ML | **PASS** | Feature Store appelle Customer, Analytics, Signal Service et Rule Engine par HTTP. Le Feature Set `sales-features-v2` contient `confirmed_signal_ratio` et `published_rule_match_strength`. La lignée persistée contient les références de signaux, les versions de règles actives/correspondantes et `rule-engine-0.1.0`. |
| 2 | La propension est consommée par Opportunity Engine et modifie la priorité | **PASS** | `rerank_with_propensity` applique les poids règles `0,65` et ML `0,35`. Exemple PostgreSQL : priorité règles seule `70,0000`, propension `0,89330497`, priorité persistée `76,7657`, moteur `rule-engine-0.1.0+ml-rerank-poc-v1`. Le composant persiste modèle, feature set, dataset, mode et trace. |
| 3 | Chaîne Feature Store → Rules/Signals → ML → Propensity → Opportunity → Dashboard CC | **PASS** | Run Docker corrélé `ml-http-chain-eight-v2` : 8 appels Feature Store `200`, 8 scores ML `200`, évaluations Rule Engine `200`, génération Opportunity `202`. Les dashboards lisent les opportunités et scores persistés via Portfolio Service. |
| 4 | Périmètre backend CC/agence non contournable | **PASS** | Tests backend : un CC conserve `rm-01` malgré `relationshipManagerId=rm-02`, reçoit `404` sur un client `rm-02`, et ne peut ouvrir le dashboard agence. Le responsable ne voit que `BR-01` et peut drill-down seulement vers ses CC. Les listes globales commerciales sont refusées par le Gateway. E2E authentifié : scénario CC et scénario agence réussis. |
| 5 | Outcomes structurés pour de futurs labels | **PASS** | Action Service persiste actions et outcomes. ML Engine matérialise `synthetic-commercial-outcomes-v1` avec `observationAsOf`, `labelAvailableFrom`, `outcomeLabel`, valeur et référence `action-outcome:*`. Résultat exécuté : 5 événements sources lus, 2 labels clients uniques, entraînement automatique `false`, training-ready `false`. |
| 6 | Aucune performance de production revendiquée | **PASS** | Modèle enregistré comme `sales-propensity-logit-poc-v1`, dataset synthétique, mode `POC_ASSISTIVE`, `productionPerformanceClaim=false`. Aucune métrique AUC, précision, rappel, calibration ou gain commercial n’est revendiquée comme performance réelle. |
| 7 | Versions et traçabilité dans chaque prédiction | **PASS** | Chaque score persiste et expose `modelVersion`, `featureVersion`, `featureChecksum`, `trainingDatasetVersion`, `deploymentMode`, `traceId`, `asOf` et `scoredAt`. Opportunity conserve ces références dans `priority_components_json` et une version moteur hybride. |
| 8 | Tests d’intégration et E2E | **PASS** | Ruff, mypy, 75 tests backend, 11 tests frontend, build Vite, validation Compose/ShellCheck et 4 parcours Playwright authentifiés réussissent. La suite E2E couvre CC, agence, outcome, propension, Rule Studio, séparation auteur/approbateur et mobile. |
| 9 | Fonctionnement sans LLM et sans GPU | **PASS** | Recherche de dépendances interdite : aucune occurrence runtime OpenAI, Anthropic, LangChain, CUDA, Torch, TensorFlow, Bedrock ou SageMaker. ML Engine tourne en Python 3.12.7 sur `x86_64`, limite `0,60 CPU` et `384 MiB`, `DeviceRequests=null`. L’inférence est une fonction logistique locale déterministe. |
| 10 | Docker complet après validations | **PASS** | Migrations jusqu’à `0005`, **20/20 services** en exécution saine, script `validate-ml-integration.sh` vert, 500 feature vectors, 500 scores et 426 opportunités hybrides persistés. Le batch final de 500 PME, par lots de 25 avec renouvellement du jeton technique, termine sans erreur en 511 s. |

## 2. Lignée technique démontrée

La chaîne runtime finale est la suivante :

```text
Analytics Service ─┐
Signal Service ─────┼─HTTP─> Feature Store sales-features-v2
Rule Engine ────────┘          │
                               └─HTTP─> ML Engine CPU
                                         │
                                         └─> PropensityScoreRecord
                                                   │
Rule Engine + règles historiques ──────────────────┼─> Opportunity Service
                                                   │    reranking 65/35
                                                   └─> Portfolio Service
                                                        ├─ Dashboard CC
                                                        └─ Dashboard agence
```

Pour `SME-00003`, la preuve persistée contient `confirmed_signal_ratio=1.0`, `published_rule_match_strength=0.7`, quatre références Signal Service, la règle active `RULE-13D60FCAB386:v2`, le modèle `sales-propensity-logit-poc-v1`, le Feature Set `sales-features-v2`, le dataset `synthetic-demo-20260918-v1`, le mode `POC_ASSISTIVE` et un `traceId` UUID.

ML Engine ne lit plus le schéma Feature Store et Feature Store ne lit plus les schémas Customer, Analytics, Signal ou Rule : les cinq privilèges de schéma contrôlés valent `false`. Les échanges du chemin d’inférence passent par les contrats HTTP authentifiés. Portfolio Service et la construction des futurs labels utilisent encore des lectures SQL dédiées décrites parmi les limites ci-dessous.

## 3. Tests exécutés

| Porte | Résultat |
|---|---|
| Ruff backend, migrations et tests | **PASS** |
| mypy sur 60 modules backend | **PASS** |
| pytest | **PASS — 75 tests** |
| TypeScript frontend | **PASS** |
| Vitest composants | **PASS — 11 tests** |
| Build Vite | **PASS** |
| Validation Compose et Keycloak | **PASS** |
| ShellCheck | **PASS** |
| Playwright authentifié | **PASS — 4/4 en 22,9 s** |
| Batch Docker 8 scénarios après frontières HTTP | **PASS** |
| Batch Docker 500 PME | **PASS — 500/500 en 511 s, 426 opportunités hybrides** |
| Script `scripts/validate-ml-integration.sh` | **PASS** |

Les temps de traitement indiquent uniquement la faisabilité technique sur le sandbox. Ils ne constituent pas un SLO BOA, un benchmark de production ou une mesure de qualité prédictive.

## 4. Éléments non implémentés

| Élément | Statut | Conséquence |
|---|---|---|
| Entraînement sur historique BOA réel | **NON IMPLÉMENTÉ** | Le modèle courant utilise des coefficients POC et un dataset synthétique versionné. |
| Mesures réelles de discrimination, calibration, uplift ou valeur commerciale | **NON IMPLÉMENTÉ** | Aucune activation de production ni comparaison à un champion ne peut être décidée. |
| Pipeline de training reproductible, validation indépendante et promotion challenger/champion | **NON IMPLÉMENTÉ** | Le registre POC conserve les métadonnées, mais pas un cycle MLOps de production. |
| Monitoring de drift opérationnel avec seuils approuvés et alertes | **NON IMPLÉMENTÉ** | Les contrats existent ; la surveillance G2 n’est pas démontrée. |
| Fallback automatique `RULES_ONLY` lors d’une panne ML | **NON IMPLÉMENTÉ** | Le pipeline échoue explicitement au lieu d’inventer un score ; ce point bloque une activation de production. |
| Politique de fusion versionnée et approuvable | **NON IMPLÉMENTÉ** | Les poids POC `65/35` sont configurés par environnement, pas par un registre de gouvernance. |
| Isolation SQL totale de tous les read models | **NON IMPLÉMENTÉ** | Feature Store et ML inference sont découplés par HTTP ; Portfolio Service et la vue de futurs labels conservent des accès SQL en lecture dédiés. |
| Gouvernance juridique/DPO, consentement ou base de traitement réelle | **NON IMPLÉMENTÉ** | Les labels présents sont exclusivement synthétiques et ne sont pas training-ready. |
| Déploiement et test AWS | **NON IMPLÉMENTÉ** | Aucun compte, rôle, connecteur ou identité AWS utilisable n’était disponible dans la session ; aucune ressource AWS n’a été créée. |
| Haute disponibilité, sauvegarde/restauration, secrets de production et intégration SI bancaire réelle | **NON IMPLÉMENTÉ** | Docker Compose reste un environnement de démonstration. |
| LLM | **NON IMPLÉMENTÉ PAR CHOIX** | Extension architecturale future seulement ; aucune dépendance, route, clé ou appel runtime. |

## 5. Décision

**Décision technique : PASS pour le POC d’intégration CPU sur données synthétiques.** Les dix contrôles demandés sont démontrés dans l’environnement Docker local, notamment l’influence réelle de la propension sur la priorité et le non-contournement des périmètres CC/agence.

**Décision de production : NON IMPLÉMENTÉE et non autorisée.** Les absences de données historiques réelles gouvernées, de validation prédictive, de monitoring de drift, de fallback et de cycle MLOps empêchent de présenter le modèle comme prêt pour la production. Le produit reste une aide commerciale explicable ; le CC demeure responsable de la décision de contact et aucun composant ne prend de décision de crédit.
