# Lot 09 — Ingestion gouvernée et qualité Transaction

**Date :** 2026-09-20
**Branche :** `feat/pilot-readiness`
**Statut du lot :** **PASS sur le périmètre Transaction ; extension Customer/Account/Product NON IMPLÉMENTÉE**

## 1. Décision de lot

Le lot introduit une frontière d'ingestion réellement gouvernée pour les transactions : contrat `1.0` strict, manifeste PostgreSQL, claim atomique, acceptation partielle explicite, quarantaine minimisée, compteurs persistés, contrôle de complétude, mesure de fraîcheur sans seuil inventé, catalogue de catégories versionné et traçabilité de chaque ligne acceptée.

La preuve exécutable est **PASS sur huit contrôles**. Elle utilise une fixture technique synthétique déterministe et une base PostgreSQL isolée. Elle ne prouve ni une connexion au SI BOA, ni la qualité ou la fraîcheur des données BOA, ni un débit/SLO de production. Elle ne mesure aucune performance ML et ne prend aucune décision de crédit.

## 2. Périmètre livré

| Capacité | Statut | Preuve ou limite |
|---|---|---|
| Contrat Transaction versionné | **IMPLÉMENTÉ / PROUVÉ** | `contractVersion: "1.0"`, champs inconnus interdits, formats et dates-heures zonées validés |
| Hash canonique et replay | **IMPLÉMENTÉ / PROUVÉ** | même contenu rejoué sans nouvel effet; contenu différent avec la même clé rejeté en `409` |
| Claim PostgreSQL concurrent | **IMPLÉMENTÉ / PROUVÉ** | deux appels concurrents obtiennent le même `jobId` et un seul jeu de lignes |
| Acceptation partielle gouvernée | **IMPLÉMENTÉ / PROUVÉ** | lignes valides écrites, doublons comptés, catégorie inconnue quarantainée |
| Rejets minimisés | **IMPLÉMENTÉ / PROUVÉ** | aucun payload brut; référence, hash, code motif et détail allowlisté uniquement |
| Complétude | **IMPLÉMENTÉ / PROUVÉ** | `expected` et `received` persistés; `PASS`, `FAIL` ou `UNKNOWN` explicite |
| Fraîcheur | **IMPLÉMENTÉ / PROUVÉ TECHNIQUEMENT** | délai calculé si `producedAt` existe; seuil toujours `null` tant que BOA ne l'a pas validé |
| Catalogue de catégories | **IMPLÉMENTÉ / PROUVÉ** | code/version/checksum/provenance/acteur/raison; une seule version active |
| Identité multi-source | **IMPLÉMENTÉ / PROUVÉ** | identité UUID incluant la source; lecture ambiguë refusée sans `sourceSystem` |
| Lineage des transactions acceptées | **IMPLÉMENTÉ / PROUVÉ** | `import_batch_id`, `source_record_hash`, `category_version` présents sur 5/5 lignes de preuve |
| Manifeste avant fan-out Banking Integration | **IMPLÉMENTÉ / PROUVÉ UNITAIREMENT** | états `RETRYABLE_FAILED` ou `PARTIAL`; `COMPLETED` exige quatre réponses sémantiquement complètes; pas encore de panne E2E injectée dans ce banc |
| Gouvernance commune Customer/Account/Product | **NON IMPLÉMENTÉ** | ces trois imports conservent leurs receipts historiques et ne partagent pas encore quarantaine/qualité/taxonomie |
| Connexion à une source BOA | **BLOCKED / À VALIDER AVEC BOA** | aucun endpoint, secret, contrat ni échantillon BOA autorisé disponible |
| Seuil de fraîcheur, SLA ou qualité BOA | **HYPOTHÈSE À VALIDER AVEC BOA** | aucune valeur n'est inventée dans le code ou la preuve |

## 3. Contrat et invariants

Le contrat Transaction `1.0` exige `sourceSystem`, `externalBatchId` et une liste de transactions. Il accepte en plus `sourceWatermark`, `producedAt` et `expectedRowCount`. Les champs inconnus sont refusés. Les montants sont des décimaux strictement positifs, les directions sont limitées à `CREDIT` et `DEBIT`, les codes devise/pays/catégorie sont normalisés, et `bookingDate` doit inclure un fuseau.

Le traitement est transactionnel dans la base du Transaction Service. Le manifeste est réclamé par `INSERT ... ON CONFLICT DO NOTHING`, puis relu sous l'unicité `(source_system, batch_ref)`. Un replay strictement identique retourne le résultat mémorisé. Une réutilisation avec un hash différent est rejetée. Une ligne de catégorie inconnue ou inactive est placée en quarantaine et n'apparaît jamais dans `transaction.transactions`. Les doublons identiques du lot ou déjà stockés ne gonflent pas le nombre accepté.

Les catégories initiales `CUSTOMER_RECEIPT`, `SUPPLIER_PAYMENT` et `OPERATING_EXPENSE` proviennent uniquement du générateur synthétique existant. Elles sont marquées `SYNTHETIC_POC` et **ne constituent pas une taxonomie BOA**. Une catégorie peut être ajoutée administrativement avec une version, une provenance, un motif, un acteur et un checksum; l'approbation métier reste une responsabilité BOA.

## 4. Qualité et fraîcheur

Le manifeste conserve les compteurs `expected`, `received`, `accepted`, `duplicate`, `rejected` et `quarantined`. Sur la fixture finale, quatre lots ont produit cinq transactions acceptées, un rejet quarantainé, quatre receipts et quatre entrées de catalogue. Les cinq transactions acceptées disposent de leur lineage complet.

La complétude est `UNKNOWN` sans `expectedRowCount`, `PASS` en cas d'égalité et `FAIL` en cas d'écart. La fraîcheur est `UNKNOWN` sans timestamp source. Si `producedAt` est fourni, le délai est mesuré en secondes mais aucun seuil `CURRENT/STALE` n'est appliqué : **HYPOTHÈSE À VALIDER AVEC BOA**.

## 5. Preuve PostgreSQL reproductible

Le protocole [`validate-ingestion-governance.sh`](../../scripts/validate-ingestion-governance.sh) crée une base PostgreSQL isolée, applique toutes les migrations jusqu'à `0016`, démarre un Transaction Service isolé, exécute les contrôles HTTP et interroge la base. Le validateur [`validate_ingestion_governance.py`](../../scripts/validate_ingestion_governance.py) produit l'artefact JSON.

| Contrôle final | Résultat |
|---|---|
| Acceptation partielle et quarantaine | **PASS** |
| Rejet redacted/minimisé | **PASS** |
| Replay idempotent et conflit de hash | **PASS** |
| Contrat strict et validation des filtres | **PASS** |
| Catalogue de catégorie versionné | **PASS** |
| Identité de transaction scopée par source | **PASS** |
| Claim atomique concurrent | **PASS** |
| Lineage et compteurs PostgreSQL | **PASS** |

L'artefact final est [`RESULTATS-INGESTION-GOUVERNEE.json`](../evidence/ingestion/RESULTATS-INGESTION-GOUVERNEE.json), protégé par [`SHA256SUMS.txt`](../evidence/ingestion/SHA256SUMS.txt). Son empreinte est `00fbf267cf1e728c5b7947d48f3d403159b8e473c1054749473bbff17273cb56`.

Comme le run précède le commit atomique du lot, la preuve ne prétend pas que le commit
de base `c8235f8` contient les sources testées. Elle déclare explicitement
`worktreeDirty: true`, liste les huit fichiers constitutifs du protocole et enregistre leur digest
reproductible `089160525c7f1c07a8ae5e3d93149efaf708e4d74cb14fb5bc411adaeb336c43`.
Le digest a été recalculé indépendamment à partir des fichiers listés et correspond à la
valeur de l'artefact.

Le premier run du banc a échoué sur un oracle de test erroné : la fixture crée cinq transactions acceptées, pas six. Toutes les assertions API avaient déjà réussi. Seule cette attente a été corrigée; le protocole fonctionnel, les données, les statuts et les critères n'ont pas été assouplis. Le second run est **PASS**.

### 5.1 Porte complète après fermeture des P1

| Porte | Résultat final |
|---|---|
| Ruff format/lint | **PASS** — 135 fichiers formatés, aucun écart |
| mypy backend et validateur | **PASS** — 79 fichiers backend et 1 script sans erreur |
| pytest backend | **PASS** — 226 tests, 6 avertissements historiques |
| ShellCheck / Compose / Keycloak JSON | **PASS** |
| frontend typecheck | **PASS** |
| frontend Vitest | **PASS** — 7 fichiers, 25 tests |
| frontend build Vite | **PASS** — 2 286 modules transformés |
| intégration ML/Docker | **PASS** — 500 vecteurs, 500 scores, lineage Rules/Signals/ML/Opportunity, outcomes futurs, aucune dépendance LLM/GPU |
| Playwright E2E | **PASS** — 19 tests |
| intégrité SHA-256 de la preuve | **PASS** |

La porte complète a été rejouée après les deux corrections P1, y compris le rebuild de
`banking-integration-service`. Les captures E2E responsive régénérées ont été restaurées
afin de ne pas mélanger des artefacts sans changement visuel à ce commit.

## 6. Migrations

La migration [`0016_ingestion_governance.py`](../../database/migrations/versions/0016_ingestion_governance.py) est additive. Elle étend `integration.import_batches`, crée `integration.import_rejections` et `config.transaction_categories`, puis ajoute la provenance de lot aux transactions. Les trois chemins suivants ont été exécutés sur PostgreSQL réel :

| Chemin | Résultat |
|---|---|
| base à `0015` → `0016` | **PASS** |
| `0016` → `0015` | **PASS** |
| ré-upgrade `0015` → `head` | **PASS** |
| base vierge `0001` → `head` | **PASS** |

La base vierge contient exactement une clé étrangère et un index de lineage sur `transaction.transactions`, ainsi que trois catégories synthétiques initiales. La migration ne supprime ni ne réécrit les transactions historiques et n'invente aucun backfill métier.

## 7. Sécurité et minimisation

Les routes d'import, de statut, de rejet et d'administration du catalogue exigent un rôle d'administration. Le Transaction Service reçoit uniquement les droits SQL nécessaires sur `integration.import_batches`, `integration.import_rejections` et `config.transaction_categories`. La quarantaine conserve un hash et une allowlist technique (`sourceSystem`, `category`), jamais le payload brut. La politique de rétention, le chiffrement supplémentaire éventuel et l'accès opérationnel restent **À VALIDER AVEC BOA**.

## 8. Limites et suite

Ce lot ferme la dette P0 du flux Transaction consommé par Analytics, Rules, Features et ML shadow. Il ne généralise pas encore le mécanisme aux référentiels Customer, Account et Product. Leur contrat versionné, leur claim atomique commun, leurs rejets par ligne et leurs métriques qualité/fraîcheur restent **NON IMPLÉMENTÉS** et doivent constituer un lot séparé pour éviter de masquer la portée réelle de la preuve.

Le fan-out `imports/all` possède désormais un manifeste durable avant les appels aval et ne publie plus de faux `COMPLETED`. Il n'est toutefois pas une transaction distribuée. La reprise automatique et la reconciliation d'un état `PARTIAL` restent **NON IMPLÉMENTÉES**.

Enfin, les données de preuve sont synthétiques et déterministes. Elles valident des invariants logiciels, pas la qualité des données BOA, pas un SLA, pas une capacité de production, pas une performance ML, et pas une décision de crédit.

## 9. Contre-revue P0/P1

La contre-revue indépendante n'a relevé aucun P0 et deux P1. Le premier concernait la
possibilité de finaliser le fan-out bancaire après une réponse HTTP réussie mais
sémantiquement `PARTIAL` ou incomplète. Il est fermé par une validation obligatoire de
`status`, `jobId`, `imported` et, pour Transaction, de la cohérence `counts.accepted`.
Les tests couvrent un statut partiel, un identifiant absent, un compteur absent, un
payload non objet et des compteurs Transaction incohérents.

Le second P1 concernait des lignes aspiratives de `docs/data-model.md` qui mentionnaient
`source_system_id` et `integration.source_records` comme s'ils étaient livrés. La
documentation décrit désormais `source_system`, les compteurs/statuts et la quarantaine
réels; `source_records` est explicitement **NON IMPLÉMENTÉ** et aucun payload brut n'est
présenté comme conservé.
