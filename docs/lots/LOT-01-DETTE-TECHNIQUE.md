# Lot 01 — Dette technique bloquante

**Date :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Statut :** PASS

## Objectif

Corriger les trois dettes P0 identifiées par l’audit préalable : filtres Opportunity annoncés mais inactifs, absence de checkpoint incrémental Analytics et absence d’historique daté des affectations client/CC/agence.

## Réalisations

| Exigence | Résultat | Preuve |
|---|---|---|
| Filtres `sector`, `customerSegment`, `relationshipManagerId` | PASS | Les trois filtres sont appliqués côté SQL. Le filtre CC utilise l’affectation active datée, et non le pointeur historique `Customer.rm_id`. |
| Traitement Analytics incrémental | PASS | Mode `INCREMENTAL` par client ou lot, hash canonique d’entrée, checkpoint persistant dans `integration.import_batches`, compteur `processed/skipped` et `lastEvaluatedAt`. Le mode `HISTORICAL` force explicitement une reprise complète. |
| Historique client/CC/agence | PASS | Table `customer.portfolio_assignments` avec `valid_from`, `valid_to`, `actor`, `reason`, index unique partiel sur l’affectation active et reprise des 500 clients existants. |
| Scopes et dashboards | PASS | Customer Service et Portfolio Service lisent l’affectation active. Les anciennes fixtures SQLite conservent un fallback contrôlé. |
| Permissions minimales | PASS | Opportunity Service peut lire les trois tables client nécessaires au filtrage ; Analytics Service peut lire/écrire les checkpoints uniquement dans `integration.import_batches`. |

## Validation

Les contrôles exécutés sur l’arbre du lot ont produit :

- **136 tests unitaires passés** ;
- Ruff : PASS ;
- mypy : PASS ;
- ShellCheck : PASS ;
- validation Compose/Keycloak : PASS ;
- upgrade de la base existante vers `0009_pilot_readiness_debts` : PASS ;
- reprise de **500 affectations actives** depuis les données existantes : PASS ;
- migration PostgreSQL vierge `0001_initial → 0009_pilot_readiness_debts` : PASS ;
- preuve Docker incrémentale : premier run `processed=1, skipped=0, metrics=55`, second run identique `processed=0, skipped=1, metrics=0` ;
- preuve Docker du filtre CC : `relationshipManagerId=rm-01`, 29 opportunités retournées.

## Risques résiduels

Le checkpoint évite le recalcul si les entrées n’ont pas changé, mais la détection d’un changement recharge encore la fenêtre source afin d’en calculer le hash. Un futur connecteur bancaire peut fournir un watermark monotone natif pour éviter cette relecture. Le mode historique reste volontairement disponible pour les reprises contrôlées.

## Écart détecté et corrigé pendant le lot

La première migration sur base vierge a échoué parce que `0001_initial` créait automatiquement la nouvelle table depuis les métadonnées ORM courantes. La migration initiale exclut désormais `portfolio_assignments`, qui est créée exclusivement par `0009`. Le test vierge complet passe après cette correction.
