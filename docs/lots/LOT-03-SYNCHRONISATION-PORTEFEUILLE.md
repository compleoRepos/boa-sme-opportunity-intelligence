# Lot 03 — Synchronisation portefeuille gouvernée

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Migration cible :** `0012_portfolio_sync_governance`
**Verdict du lot :** **PASS**, avec limites de production explicites

## 1. Objectif

Ce lot ferme la dette pilote relative à l’absence de synchronisation portefeuille contrôlée. Il ne remplace pas l’import client existant : il ajoute un contrat séparé pour les événements d’affectation, avec dates d’effet, idempotence HTTP et source, historique non superposé, audit avant/après et outbox.

Le lot conserve l’isolation backend CC/agence. Customer Service, Portfolio Service et Opportunity Service utilisent désormais la même définition d’une affectation active : `validFrom <= instant < validTo`, avec une borne supérieure ouverte lorsque `validTo` est nul.

## 2. Résultat fonctionnel

| Exigence | Statut | Preuve |
|---|---|---|
| Contrat d’affectation versionné | **PASS** | `contractVersion=1.0`, source, lot, événement, portefeuille, CC, agence, type, dates, motif et watermark validés par Pydantic. |
| Endpoint dédié | **PASS** | `POST /internal/v1/portfolio-assignments/sync` et façade `POST /api/v1/admin/portfolio-assignments/sync`. |
| Historique `asOf` | **PASS** | `GET /internal/v1/portfolio-assignments?customerId=...&asOf=...` retourne l’affectation valable avant ou après une date d’effet future. |
| Idempotence HTTP | **PASS** | Premier appel `202 replayed=false`; rejeu immédiat `202 replayed=true`, même `jobId`. |
| Idempotence événement source | **PASS** | Unicité `(sourceSystem, sourceEventId)` dans `portfolio_sync_events`; contenu divergent refusé par `409 SOURCE_EVENT_REUSED`. |
| Concurrence contrôlée | **PASS** | Claims PostgreSQL non bloquants sur lot, événement et client; conflits traduits en `409`, sans attente indéfinie. |
| Intervalles non superposés | **PASS** | Contrainte PostgreSQL `ex_portfolio_assignments_no_overlap` sur la plage `[validFrom, validTo)`. |
| Affectation future | **PASS** | L’ancienne affectation reste courante jusqu’à la date d’effet; la nouvelle devient visible après cette date. |
| Événement hors ordre | **PASS** | Rejet explicite `409 OUT_OF_ORDER_ASSIGNMENT`; aucune réécriture silencieuse de l’historique. |
| Intervalle déjà terminé | **PASS** | Rejet `409 HISTORICAL_RECONCILIATION_REQUIRED`; aucune suppression de l’affectation active. |
| Référentiel CC | **PASS** | Une affectation ne modifie pas un CC existant; une agence divergente retourne `409 RELATIONSHIP_MANAGER_BRANCH_CONFLICT`. |
| RBAC de synchronisation | **PASS** | Façade publique limitée à `ADMIN`; route interne limitée à `ADMIN` ou au `client_id=banking-integration-service`. |
| Rôles OAuth client | **PASS** | Les rôles de `resource_access` sont lus uniquement pour l’audience BOA configurée; un rôle `ADMIN` d’une autre application est ignoré. |
| Audit et provenance | **PASS** | Un reçu, un événement source, un audit avant/après et une outbox sont persistés dans la transaction métier. |
| Audit SQL append-only | **PASS** | Trigger `trg_audit_logs_append_only`; une tentative `UPDATE audit.audit_logs` échoue réellement. |
| Compatibilité import client | **PASS** | L’import existant enrichit les affectations legacy; il refuse de contourner une affectation future planifiée. |

## 3. Modèle persistant

La migration `0012_portfolio_sync_governance` enrichit `customer.portfolio_assignments` avec `portfolio_id`, `assignment_type`, `is_primary`, `source_system`, `source_event_id`, `source_payload_hash` et `source_watermark`. Elle crée :

| Table | Usage |
|---|---|
| `customer.portfolio_sync_receipts` | réponse de lot rejouable par clé HTTP ou référence source ; hash SHA-256 du contenu |
| `customer.portfolio_sync_events` | déduplication et statut de chaque événement source |
| `integration.outbox_messages` | événement `PORTFOLIO_ASSIGNMENT_CHANGED` pour intégration aval |
| `audit.audit_logs` | acteur, corrélation, avant/après, lot, watermark et hash de provenance |

Le trigger append-only protège le journal générique contre `UPDATE` et `DELETE`. Il s’agit d’une protection PostgreSQL locale ; elle n’est pas présentée comme un stockage WORM ou une intégration SIEM.

## 4. Preuve API PostgreSQL

Un lot de preuve post-revue a planifié la réaffectation future de `SME-00430` vers `rm-06` et `BR-02` au 1er novembre 2026. Les résultats observés sont :

| Mesure | Résultat observé |
|---|---:|
| Premier appel | HTTP `202`, `applied=1`, `replayed=false` |
| Rejeu immédiat | HTTP `202`, même `jobId`, `replayed=true` |
| Affectation avant date d’effet | ancien portefeuille et ancien CC |
| Affectation après date d’effet | `PORTFOLIO-BR-02-PILOT`, `rm-06` |
| Reçus pour le lot | 1 |
| Événements source | 1 |
| Audits métier | 1 |
| Messages outbox | 1 |
| Tentative de déplacer `rm-06` vers `BR-03` | HTTP `409`; le référentiel reste `BR-02` |

Les données sont synthétiques et utilisées uniquement comme preuve fonctionnelle. Elles ne constituent pas un raccordement au SI bancaire ni une mesure de performance.

## 5. Validation technique

### 5.1 Qualité et tests

| Porte | Résultat |
|---|---|
| Ruff format | **PASS** — 120 fichiers déjà formatés |
| Ruff | **PASS** |
| Mypy | **PASS** — 75 fichiers source |
| Pytest backend | **PASS** — 186 tests, 6 avertissements existants |
| ShellCheck | **PASS** avec exclusion documentée `SC1091` pour les sources dynamiques |
| `scripts/validate.sh` | **PASS** |
| TypeScript | **PASS** |
| Vitest | **PASS** — 16 tests |
| Build Vite | **PASS** — 2 284 modules transformés |
| Playwright | **PASS** — 8 scénarios sur 8 |

### 5.2 Bases de données

| Porte | Résultat |
|---|---|
| Upgrade base existante `0011→0012` | **PASS** |
| Upgrade PostgreSQL vierge `0001→0012` | **PASS** |
| Tables `portfolio_sync_events` et `portfolio_sync_receipts` | **PASS** sur base vierge |
| Contrainte anti-chevauchement | **PASS** |
| Trigger append-only audit | **PASS** sur base existante et base vierge |
| Rejeu idempotent de `scripts/migrate.sh` | **PASS** |

### 5.3 Stack et intégration existante

Les services PostgreSQL, Keycloak, Customer, Analytics, Signal, Rule Engine, Feature Store, ML Engine, Opportunity, Action, Portfolio, Gateway et Frontend ont été reconstruits et observés `healthy`. Cette validation historique confirmait 500 vecteurs, 500 scores, la lignée et l’absence de dépendance LLM/GPU. **Le claim d’influence est remplacé par le lot 10 : le score est désormais shadow et la priorité rules-only.**

Cette validation confirme une intégration POC/shadow CPU-only. Elle ne revendique aucune performance ML de production et ne réalise aucune décision de crédit.

## 6. Commandes reproductibles

```bash
ruff format --check backend/src database tests/unit
ruff check backend/src database tests/unit
mypy backend
PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings
shellcheck -x -e SC1091 scripts/*.sh
./scripts/validate.sh
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run
npm --prefix frontend run build
./scripts/migrate.sh
./scripts/validate-ml-integration.sh
npm --prefix frontend run test:e2e
```

La migration vierge se rejoue dans une base PostgreSQL temporaire en lançant `alembic -c alembic.ini upgrade head` avec `DATABASE_URL` pointant vers cette base.

## 7. Limites et décisions BOA restantes

| Sujet | Statut |
|---|---|
| Identifiant et version du système source réel | **À confirmer par BOA** |
| Sémantique définitive de `portfolioId` | **À confirmer par BOA** |
| Affectations secondaires et délégations | **NON IMPLÉMENTÉ** |
| Réconciliation rétroactive multi-intervalles | **NON IMPLÉMENTÉ** |
| Suppression/résiliation envoyée par la source | **NON IMPLÉMENTÉ** |
| Projection de scope signée avec expiration | **NON IMPLÉMENTÉ** |
| Dispatcher permanent d’outbox avec file morte | **NON IMPLÉMENTÉ** |
| Stockage WORM, SIEM et politique de rétention | **À définir avant production** |
| Test de charge 50 000 PME | **HORS LOT — aucun résultat revendiqué ici** |

## 8. Conclusion

Le lot est **PASS pour le pilote technique** : le produit dispose maintenant d’un flux d’affectation distinct, daté, idempotent, concurrent-safe, audité et exposé par le Gateway. La validation d’un raccordement réel reste conditionnée par le contrat source, l’IAM, la politique de réconciliation et les exigences de conservation BOA.
