# Lot 14 — Studio ML gouverné

**Date :** 21 septembre 2026

**Branche d’origine :** `feat/ml-studio-parallel`

**Statut :** **IMPLÉMENTÉ ET PROUVÉ LOCALEMENT SUR DONNÉES SYNTHÉTIQUES / NO-GO POUR ACTIVATION ML ET PRODUCTION**

## 1. Décision

Le Studio ML fournit un parcours gouverné en six onglets : vue d’ensemble, données, entraînement, évaluation, fusion règles/ML et approbation/journal. L’entraînement logistique utilise scikit-learn `1.5.2` sur CPU, sans GPU, LLM ni service cloud. Les jobs, étapes, erreurs, durées et résultats sont persistés.

Cette capacité ne modifie pas le comportement opérationnel : le mode reste `POC_SHADOW`, la priorité demeure `RULES_ONLY`, `rules_weight=1` et `ml_weight=0`. Les modèles construits avec les labels synthétiques portent `DEMO_ONLY` et leur promotion est refusée côté serveur. Le produit ne prend aucune décision de crédit.

## 2. Capacités implémentées

| Capacité | Statut | Limite |
|---|---|---|
| Entraînement logistique CPU | **IMPLÉMENTÉ et testé** | données de démonstration synthétiques uniquement |
| Progression et historique | **IMPLÉMENTÉS et testés** | polling frontend borné ; états persistés |
| Annulation et idempotence | **IMPLÉMENTÉES et testées** | conflit explicite si une clé est réutilisée avec une configuration divergente |
| Manifestes point-in-time | **IMPLÉMENTÉS** | aucun manifeste BOA historique approuvé |
| Comparaison de modèles | **IMPLÉMENTÉE et testée** | jeu de test commun obligatoire |
| Simulation règles/ML | **IMPLÉMENTÉE et auditée** | lit seulement opportunités et scores shadow persistés ; ne réécrit jamais la priorité opérationnelle |
| Cycle auteur/approbateur/admin | **IMPLÉMENTÉ et testé** | auto-approbation refusée ; activation G3 bloquée |
| Promotion `DEMO_ONLY` | **BLOQUÉE côté serveur** | aucune promotion de modèle synthétique |
| Interface six onglets | **IMPLÉMENTÉE et testée** | mapping IAM BOA à valider |
| Migration combinée | **PROUVÉE** | tête unique `0019_ml_studio_catalog_merge` après les deux branches 0018 |

## 3. Simulation de politique

`POST /api/v1/admin/scoring-policies/{id}/versions/{version}/simulate` calcule côté serveur, pour une population point-in-time persistée :

- la distribution de priorité avant et après ;
- le nombre de montées, descentes et priorités inchangées ;
- les plus fortes variations ;
- le nombre de lignes sans score shadow exploitable.

Le serveur refuse une simulation sans score shadow exploitable. Le résultat détaillé est inscrit dans l’audit append-only, puis la version passe à `SIMULATED`. La simulation n’écrit aucune opportunité, ne change aucune priorité persistée et ne constitue ni une activation, ni un résultat de production.

## 4. Parcours multi-rôles

Le scénario Playwright `tests/e2e/ml-studio.spec.ts` exerce :

1. Karim (`ML_STEWARD`) consulte le manifeste synthétique ;
2. deux entraînements CPU sont lancés et suivis jusqu’à `SUCCEEDED` ;
3. les deux candidats `DEMO_ONLY` sont comparés sur un jeu de test commun ;
4. une politique 90/10 est simulée côté serveur puis soumise ;
5. Karim ne peut ni approuver sa politique ni promouvoir le modèle `DEMO_ONLY` ;
6. Nadia (`RULE_APPROVER`) approuve ;
7. Youssef (`ADMIN`) tente l’activation, refusée par la porte G3.

Le parcours produit des captures 1440 × 900 lors de la suite complète. Ces captures documentent l’IHM ; les tests API, les audits et les assertions PostgreSQL restent les preuves d’autorité.

## 5. Statut des portes

| Porte | Statut |
|---|---|
| G0 — architecture | **PASS** |
| G1 — technique locale | **PASS sur données synthétiques** |
| G2 — shadow en environnement BOA | **BLOCKED** — données, monitoring et validation BOA absents |
| G3 — reranking métier | **BLOCKED** — aucune performance shadow BOA approuvée |
| G4 — candidate ML | **HORS MVP** |

Les seuils de préparation des labels, la politique de pondération et les critères de promotion restent **HYPOTHÈSE À VALIDER AVEC BOA**.

## 6. Usage autorisé

**GO limité** pour démonstration synthétique, revue de code, exercice de gouvernance et validation du parcours CPU.

**NO-GO** pour données BOA réelles, activation d’un poids ML non nul, promotion de modèle, décision de crédit ou production. Le gate global reste `BLOCKED_IMAGE_CVES` tant que les images externes ne sont pas corrigées ou qu’une acceptation de risque formelle n’est pas approuvée.

## Références

- [`ml-acceptance.md`](../ml-acceptance.md)
- [`RBAC-MATRIX.md`](../RBAC-MATRIX.md)
- [`test_ml_training.py`](../../tests/unit/test_ml_training.py)
- [`test_scoring_policy_api.py`](../../tests/unit/test_scoring_policy_api.py)
- [`ml-studio.spec.ts`](../../tests/e2e/ml-studio.spec.ts)
