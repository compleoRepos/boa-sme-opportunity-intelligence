# Statut courant — BOA SME Opportunity Intelligence

**Date :** 19 septembre 2026

Le produit est un **POC d’intelligence commerciale PME** exécutable sur CPU avec Docker Compose. Il combine Analytics, Signal Service, Rule Studio, Feature Store, un modèle logistique de propension commerciale et Opportunity Service. Il ne prend aucune décision de crédit et ne dépend d’aucun LLM ou GPU.

## Implémenté et validé

| Capacité | Statut |
|---|---|
| Microservices FastAPI, PostgreSQL, Keycloak et Gateway | **PASS** |
| Frontend React/TypeScript authentifié | **PASS** |
| Rule Studio versionné avec simulation, séparation auteur/approbateur, activation, désactivation et rollback | **PASS** |
| Feature Store `sales-features-v2` alimenté par Analytics, Signals et Rule Engine via HTTP | **PASS** |
| ML Engine CPU avec score, contributions et versions persistées | **PASS — POC synthétique** |
| Influence du score sur la priorité Opportunity, pondération POC 35 % ML / 65 % règles | **PASS** |
| Dashboard CC limité à son portefeuille | **PASS** |
| Dashboard responsable d’agence consolidé et limité à ses branches | **PASS** |
| Fiche PME, opportunités, actions et outcomes | **PASS** |
| Outcomes matérialisables comme futurs labels versionnés, sans auto-entraînement | **PASS** |
| Quatre parcours Playwright authentifiés desktop/mobile | **PASS** |
| Batch de 500 PME synthétiques | **PASS** |

Les preuves et limites détaillées sont disponibles dans [`ml-integration-status.md`](./ml-integration-status.md).

## Non implémenté

L’entraînement et la validation sur données BOA réelles, la calibration, le monitoring de drift opérationnel, le fallback automatique `RULES_ONLY`, la gouvernance juridique/DPO, le déploiement AWS, la haute disponibilité, les sauvegardes testées, les secrets de production et l’intégration aux SI bancaires réels ne sont pas implémentés.

Le LLM est **non implémenté par choix** : il reste une possibilité architecturale future, hors du score, de l’éligibilité et de la priorisation.

## Positionnement

Le modèle actif `sales-propensity-logit-poc-v1` utilise le dataset `synthetic-demo-20260918-v1` et le Feature Set `sales-features-v2` en mode `POC_ASSISTIVE`. Aucune performance prédictive ou commerciale de production n’est revendiquée. `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner par le chargé de clientèle.
