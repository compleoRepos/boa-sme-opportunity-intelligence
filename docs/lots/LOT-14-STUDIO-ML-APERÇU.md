# Lot 14 — Aperçu gouverné du Studio ML

**Date :** 21 septembre 2026

**Branche :** `feat/ml-studio-parallel`

**Révision testée :** `d99bdb0`

**Statut :** **IMPLÉMENTÉ ET VALIDÉ LOCALEMENT SUR LE PÉRIMÈTRE UNITAIRE / BLOCKED POUR E2E ET RELEASE**

## 1. Décision

Le Studio ML est disponible comme **aperçu local gouverné** sur la branche séparée `feat/ml-studio-parallel`. Il combine le catalogue produit et la clôture de `feat/pilot-readiness` avec un backend d’entraînement CPU, une interface en six onglets et des contrôles de séparation des tâches.

Ce lot ne modifie pas la décision de release. Le ML reste `POC_SHADOW`, la priorité reste `RULES_ONLY`, les artefacts issus des labels synthétiques restent `DEMO_ONLY`, la promotion demeure bloquée et le produit ne prend aucune décision de crédit. Aucun LLM, GPU ou service cloud n’est requis. AWS reste hors périmètre.

## 2. Capacités implémentées

| Capacité | Statut | Limite |
|---|---|---|
| Job d’entraînement logistique CPU | **IMPLÉMENTÉ** | données de démonstration synthétiques uniquement |
| Progression persistée | **IMPLÉMENTÉ** | étapes, pourcentage, durées, erreurs et état terminal persistés |
| Polling frontend | **IMPLÉMENTÉ** | toutes les 2 secondes, arrêt automatique à l’état terminal |
| Annulation | **IMPLÉMENTÉ** | demande persistée et transition auditée |
| Idempotence | **IMPLÉMENTÉ** | même manifeste et même configuration ; conflit explicite si configuration divergente |
| Manifeste | **IMPLÉMENTÉ** | l’API expose l’UUID technique réellement consommé par `POST /trainings` |
| Comparaison | **IMPLÉMENTÉE** | refus explicite lorsque les modèles ne partagent pas un jeu de test comparable |
| Registre et portes G0–G4 | **IMPLÉMENTÉS** | G2/G3 restent bloquées sans historiques BOA et validation indépendante |
| Séparation des tâches | **IMPLÉMENTÉE** | auteur, approbateur et administrateur contrôlés côté serveur ; auto-approbation refusée |
| Ratio règles/ML | **IMPLÉMENTÉ** | curseur borné côté client et serveur entre 0 et 50 % ; activation ML toujours bloquée |
| Interface Studio ML | **IMPLÉMENTÉE** | six onglets : vue d’ensemble, données, entraînement, évaluation, fusion, approbation/journal |
| Persona Karim | **IMPLÉMENTÉE localement** | `ML_STEWARD` + `DATA_ANALYST`; mapping IAM **À VALIDER AVEC BOA** |
| Catalogue produit | **FUSIONNÉ** | 28 produits publics indicatifs ; aucune validation commerciale BOA |
| Migration combinée | **IMPLÉMENTÉE** | tête unique `0019_ml_studio_catalog_merge` après les deux branches additives `0018` |

## 3. Simulation de politique

La simulation d’impact avant/après n’est **pas implémentée**. Le backend retourne explicitement HTTP `501 NOT_IMPLEMENTED` et ne change pas le statut de la politique. Il indique que les sorties requises sont la distribution de priorité avant/après, les montées/descentes et le top 10 des variations.

Cette décision évite de répercuter un échantillon fourni par le client ou de calculer des chiffres dans l’IHM. Le calcul ne sera implémentable honnêtement qu’avec un dataset point-in-time persistant réunissant, pour la même population, scores règles et scores ML. L’interface désactive donc l’action et affiche cette limite.

## 4. Résultats mesurés

| Porte | Résultat |
|---|---|
| Ruff format | **PASS**, 151 fichiers |
| Ruff lint | **PASS** |
| mypy | **PASS**, 86 fichiers source |
| pytest backend | **PASS**, 266 tests ; 10 avertissements non bloquants |
| TypeScript | **PASS** |
| Vitest | **PASS**, 31 tests dans 8 fichiers |
| Build Vite | **PASS**, 2 290 modules |
| ShellCheck | **PASS** |
| PostgreSQL vierge | **PASS**, upgrade vers `0019_ml_studio_catalog_merge` |
| PostgreSQL existant | **PASS**, upgrade idempotent |
| Downgrade/ré-upgrade | **PASS**, `0019→0017→0019` |
| Tables Studio ML | **PASS**, `training_jobs` et `training_examples` présentes après ré-upgrade |
| Colonnes catalogue | **PASS**, `family`, `description`, `source_url` présentes après ré-upgrade |
| E2E Karim | **NON EXÉCUTÉ** |
| Capture 1440 px | **NON PRODUITE** |
| Simulation portefeuille | **NON IMPLÉMENTÉE**, HTTP 501 explicite |

La preuve JSON et son manifeste SHA-256 sont versionnés sous [`docs/evidence/ml-studio/`](../evidence/ml-studio/).[1]

## 5. Blocages

1. L’E2E réel de Karim et la capture des six onglets ne sont pas encore produits.
2. La simulation avant/après nécessite un dataset point-in-time serveur qui n’existe pas encore.
3. Les labels historiques BOA ne sont pas disponibles ; toute performance, calibration et training-readiness de production restent bloquées.
4. Le gate de release global demeure `BLOCKED_IMAGE_CVES`.
5. Le rôle `ML_STEWARD`, la séparation de tâches et la persona doivent être mappés vers l’IAM BOA avant tout pilote réel.
6. Les seuils de 200 exemples et 30 positifs sont **HYPOTHÈSE À VALIDER AVEC BOA**.

## 6. Usage autorisé

**GO limité** pour revue de code, démonstration locale synthétique et poursuite des tests E2E.

**NO-GO** pour fusion dans `main`, release, données BOA réelles, promotion de modèle, activation d’un poids ML non nul ou production.

## Références

[1]: ../evidence/ml-studio/RESULTATS-STUDIO-ML-PREVIEW.json "Preuve locale de l’aperçu Studio ML"
[2]: ../ml-acceptance.md "Checklist normative d’acceptation ML"
[3]: ../RBAC-MATRIX.md "Matrice RBAC"
[4]: LOT-12-CATALOGUE-PRODUITS-BOA.md "Lot 12 — catalogue produit"
[5]: LOT-13-CLOTURE-PILOTE.md "Lot 13 — clôture de la branche pilote"
