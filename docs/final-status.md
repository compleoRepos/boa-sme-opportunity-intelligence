# Statut courant — BOA SME Opportunity Intelligence

**Date :** 20 septembre 2026

BOA SME Opportunity Intelligence est un **POC d’intelligence commerciale PME** exécutable sur CPU. Il combine Analytics, Signals, Rule Studio, Feature Store point-in-time, modèle logistique de propension, Scoring Policy gouvernée, Opportunity Engine, dashboards CC/agence et actions/outcomes. Il ne prend aucune décision de crédit et ne dépend d’aucun LLM, GPU ou appel IA externe.

## Statut technique

| Capacité | Statut |
|---|---|
| Stack Docker Compose, PostgreSQL, Keycloak, Gateway et frontend premium | **PASS — 20/20 services sains** |
| Rule Studio versionné, simulation, séparation auteur/approbateur et rollback | **PASS** |
| Feature Store alimenté par Analytics, Signals et Rule Engine via HTTP | **PASS** |
| ML Engine CPU avec lignée, score, contributions et versions | **PASS — POC synthétique** |
| Scoring Policy active verrouillée à règles `1`, ML `0` | **PASS** |
| Score disponible ou indisponible → priorité opérationnelle `RULES_ONLY` | **PASS** |
| Score ML observé et audité sans effet sur Opportunity/Portfolio | **PASS — `POC_SHADOW`** |
| Model Registry, lineage, manifest et évaluation descriptive persistés | **PASS — SOCLE MLOps, activation bloquée** |
| Monitoring drift/opérationnel persistant et readiness prudente | **PASS — SOCLE** |
| Dashboard CC limité à son portefeuille | **PASS** |
| Dashboard agence consolidé et limité à ses branches/CC | **PASS** |
| Outcomes matérialisés comme labels candidats versionnés | **PASS — `trainingReady=false`** |
| Migration base vierge `0001` → `0017_ml_shadow_governance` | **PASS** |
| Suite navigateur complète | **PASS — 8/8** |
| Tests backend/frontend et build | **PASS — 119 backend, 15 frontend** |

## Positionnement et limites

Le modèle actif et les challengers restent en mode **`POC_SHADOW`** sur données locales/synthétiques. Les bandes LOW/MEDIUM/HIGH sont des `scoreBand`, pas une calibration. Brier et ECE peuvent être calculés descriptivement, mais `calibrationStatus=NOT_VALIDATED` et l’évaluation reste `BLOCKED`. Aucune précision, AUC, uplift ou performance commerciale de production n’est revendiquée. `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner par un humain.

La production est **BLOCKED**. Les données et labels BOA réels, la validation indépendante du modèle, l’homologation DPO/Sécurité, les adaptateurs CBS/CRM/Payments/Trade, la haute disponibilité, la restauration testée, les secrets/TLS de production et les choix cloud restent à réaliser et approuver. Aucun déploiement AWS n’a été créé.

Le rapport de référence est [`finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md). La gouvernance des données et la cible d’industrialisation sont détaillées dans [`industrialization-governance.md`](./industrialization-governance.md).

Le LLM est **non implémenté par choix** et reste une possibilité architecturale future hors score, éligibilité, priorisation et décision métier.
