# Lot 02 — Cycle de vie Opportunity, actions et résilience

**Date :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Statut du lot :** **PASS**

## Conclusion

Le lot ferme les dettes P0/P1 relatives au cycle de vie des opportunités et des actions commerciales. Les opportunités disposent désormais d’états contrôlés, d’une expiration, de cooldowns versionnés par règle et d’une déduplication lors des reruns. Le choix commercial « À revoir » est relié à l’état `DEFERRED` et à l’outcome structuré `REVIEW_LATER`.

L’historique transactionnel minimal est vérifié avant toute génération. La preuve Docker a d’abord retourné `422 INSUFFICIENT_TRANSACTION_HISTORY` sur un snapshot historique dépourvu de lignée. Après recalcul explicite, le client présentait une profondeur de **365 jours**, puis le rerun a supprimé deux candidats pendant le cooldown au lieu de recréer l’opportunité différée.

La porte finale passe avec **171 tests backend**, **16 tests frontend** et **8 scénarios E2E**. La migration passe sur la base existante et sur une base PostgreSQL vierge de `0001` à `0011`. Les invariants ML restent inchangés : modèle POC assistif/shadow, CPU-only, sans LLM, sans décision de crédit et sans revendication de performance sur les données synthétiques.

## Résultats par exigence

| Exigence | Statut | Preuve |
|---|---|---|
| Machine d’états Opportunity | PASS | États `OPEN`, `ACCEPTED`, `CONTACTED`, `CONVERTED`, `DISMISSED`, `DEFERRED`, `EXPIRED`; transitions autorisées explicitement; transitions interdites en `409`. |
| Expiration et cooldown | PASS | `expiresAt`, `cooldownUntil`, `statusUpdatedAt`, `statusReason`, `lastActionAt`; maintenance avec `SKIP LOCKED`; l’expiration ne simule pas une action commerciale. |
| Politique configurable par règle | PASS | Bloc `lifecycle` versionné dans Rule Studio, affiché dans l’éditeur et le détail, propagé par Rule Engine puis appliqué dans Opportunity Service. |
| Déduplication et rerun | PASS | Une opportunité active est rafraîchie; un candidat sous cooldown est `SUPPRESSED`; claim non bloquant par `(client,type)`; chaque décision est auditée. |
| Historique transactionnel d’au moins 90 jours | PASS | `historyDays` et `observedFrom` proviennent des transactions réelles; l’absence de lignée ou une profondeur insuffisante bloque la génération en `422`. |
| Action « À revoir » | PASS | `DEFER_OPPORTUNITY` exige un `dueAt` futur avec fuseau, produit `REVIEW_LATER` et projette l’état `DEFERRED`. |
| Outcomes structurés | PASS | Outcomes idempotents; remplacement refusé; doublon métier d’action terminale refusé; persistance dans `action.action_outcomes`. |
| Audit avant/après | PASS | Action Service et Opportunity Service écrivent dans `audit.audit_logs` avec acteur, corrélation, ressource, état avant et état après. |
| Isolation CC/agence backend | PASS | Opportunity Service filtre liste, détail et explication; Action Service valide aussi chaque liste filtrée et chaque PATCH auprès du service propriétaire avec le jeton utilisateur. |
| Résilience OAuth interservice | PASS | Renouvellement anticipé, verrou de refresh concurrent, validation de réponse et retry unique après `401`; tests dédiés. |
| Saga Action→Opportunity | PASS | Intention locale durable `PENDING/FAILED/APPLIED`, identifiant de commande stable, compte de tentatives, erreur auditée, transition distante idempotente et reprise avec la même clé. |
| Migration existante `0010 → 0011` | PASS | Base au head `0011_action_transition_saga`; historique repris en `APPLIED` ou `NOT_REQUIRED`; aucune valeur obligatoire nulle. |
| Migration vierge `0001 → 0011` | PASS | Onze migrations appliquées; colonnes, contrainte des statuts de saga et unicité de `transition_command_id` vérifiées; base temporaire supprimée. |
| E2E navigateur | PASS | **8/8** : gouvernance, MLOps, Scoring Policy, cockpit CC, agence, tablette, Rule Studio et registre ML. |
| Retry automatique en arrière-plan | NON IMPLÉMENTÉ DANS CE LOT | La saga est durable et reprenable, mais le pilote exige encore le rejeu du même appel idempotent; aucun dispatcher permanent n’est revendiqué. |
| Tests de charge 50 000 clients | NON IMPLÉMENTÉ DANS CE LOT | Planifiés dans le lot de performance et de preuves pilote; aucune capacité de charge n’est revendiquée ici. |

## Comportement métier livré

### Graphe de transitions

Le chemin nominal autorise `OPEN → ACCEPTED → CONTACTED → CONVERTED`. Le contact direct `OPEN → CONTACTED` est autorisé lorsqu’une action prouve que le client a été joint. Les états actifs peuvent évoluer vers `DISMISSED`, `DEFERRED` ou `EXPIRED`. Une instance terminale ne peut pas être rouverte.

Une transition terminale strictement identique peut être rejouée. Ce comportement permet à Action Service de terminer sa transaction locale si la transition distante a réussi avant une panne. Un rejeu avec une autre date de cooldown retourne `409 OPPORTUNITY_TRANSITION_REPLAY_CONFLICT`.

### Paramètres du pilote

Les durées initiales sont des **hypothèses configurables**, pas des résultats mesurés. Les cooldowns par défaut sont de 30 jours après rejet, 180 jours après conversion, 30 jours après report et 7 jours après expiration. La validité est de 90 jours pour `INVESTMENT_FINANCING` et `TRADE_FINANCE`, 60 jours pour `CASH_INVESTMENT` et 30 jours pour `FINANCIAL_STRESS_SIGNAL`.

Rule Studio valide ces valeurs, les persiste avec chaque version et les propage au Rule Engine. Les anciennes versions reçoivent les valeurs par défaut lors de la lecture sans réécrire leur historique.

### Historique et qualité de données

La profondeur historique correspond au nombre de jours calendaires entre la première transaction observée et `asOfDate`. Elle ne remplace pas `dataCoverage`, qui mesure la complétude des observations dans les fenêtres. Une profondeur inférieure à 90 jours bloque la génération et n’est jamais remplacée par une valeur implicite.

La première tentative Docker sur `SME-00427` a été refusée parce que les anciens snapshots ne contenaient ni `historyDays` ni `observedFrom`. Le mode `HISTORICAL` a recalculé **55 métriques** avec une profondeur de **365 jours**, observée depuis le 1er octobre 2025 jusqu’au 30 septembre 2026.

## Preuves Docker reproductibles

### Report et audit

L’action créée sur l’opportunité `0039c5cb-2357-52bd-b62d-8cb3e65ab701` a produit :

```text
actionType=DEFER_OPPORTUNITY
status=COMPLETED
outcome=REVIEW_LATER
dueAt=2026-10-30T09:00:00Z
```

La projection Opportunity a produit `OPEN → DEFERRED`, avec `cooldownUntil=2026-10-30T09:00:00Z`. Deux événements corrélés sont persistés : `ACTION_CREATED` et `OPPORTUNITY_DEFERRED`.

La revue indépendante a ensuite exigé la fermeture du risque de succès partiel. La version finale persiste d’abord l’action et sa commande en `PENDING`. Une transition distante simulée en échec laisse la commande en `FAILED`, conserve le code `DEPENDENCY_UNAVAILABLE` et incrémente le nombre de tentatives. Le rejeu du même payload avec la même clé reprend cette ligne, déduplique la transition côté Opportunity, finalise l’action en `COMPLETED/APPLIED` et n’écrit l’outcome qu’après le succès distant.

### Rerun sous cooldown

Après recalcul historique, le rerun a retourné :

```json
{
  "status": "COMPLETED",
  "created": 0,
  "refreshed": 1,
  "suppressed": 2,
  "expired": 0
}
```

Les deux décisions supprimées sont reliées à l’opportunité terminale par `OPPORTUNITY_GENERATION_SUPPRESSED`. La trace contient le client, le type, l’identifiant terminal et la date de fin de cooldown. Le compteur `refreshed=1` correspond à un autre type d’opportunité active du même client; il ne duplique pas l’opportunité différée.

### Concurrence de génération

Deux générations HTTP ont été déclenchées simultanément sur `SME-00427` avec deux clés techniques distinctes. La première a terminé en `202 COMPLETED` avec `created=0`, `refreshed=1` et `suppressed=5`. La seconde a retourné immédiatement `409 GENERATION_IN_PROGRESS`. Aucun `500`, aucune attente indéfinie et aucun doublon ne sont observés; Feature Store est resté `healthy` avec `FailingStreak=0`. Une première variante utilisant un verrou bloquant, placé trop tard, avait figé le worker async et révélé une contention de matérialisation. Elle a été rejetée : le claim client intervient désormais avant tout appel aval et chaque matérialisation possède également son propre `pg_try_advisory_xact_lock` non bloquant.

### Migrations

Sur la base existante, Alembic indique `0011_action_transition_saga`. Les **617** opportunités avaient déjà été reprises par `0010`; les six actions historiques présentes lors du passage à `0011` ont été classées en **5 `APPLIED`** et **1 `NOT_REQUIRED`**, sans statut ni compteur de tentatives nul. `action_service` dispose de `SELECT, INSERT` sur `audit.audit_logs`.

Sur la base vierge temporaire, Alembic a appliqué successivement `0001_initial` à `0011_action_transition_saga`. Les six colonnes `transition_*`, `pending_outcome_type`, la contrainte `NOT_REQUIRED/PENDING/APPLIED/FAILED` et l’unicité de `transition_command_id` ont été vérifiées. La base temporaire a été supprimée après contrôle.

## Porte de qualité finale

| Contrôle | Résultat |
|---|---|
| `ruff format --check backend/src database tests/unit` | PASS — 116 fichiers formatés |
| `ruff check backend/src database tests/unit` | PASS |
| `mypy backend` | PASS — 75 fichiers source |
| `PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings` | PASS — **171 tests**, 6 avertissements préexistants |
| `shellcheck -x -e SC1091 scripts/*.sh` | PASS — seule l’inférence de chemin dynamique `common.sh` est explicitement exclue |
| `./scripts/validate.sh` | PASS |
| `npm run test -- --run` | PASS — **16 tests** |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| `npm run test:e2e` | PASS — **8 scénarios** en 1,8 minute |
| `./scripts/validate-ml-integration.sh` | PASS |

La validation ML confirme **500 vecteurs de features** et **500 scores de propension** persistés, la lignée Rule Studio/Signal, l’influence du score sur la priorité, la trace modèle/features/dataset/mode POC, les outcomes comme futurs labels et l’absence de dépendance LLM/GPU/cloud.

## Écarts rencontrés et corrigés

La première commande E2E était lancée depuis `frontend` alors que les spécifications résolvaient un second runtime Playwright dans `tests/e2e`. La commande `test:e2e` exécute désormais Playwright depuis son propre dossier. L’URL par défaut utilisait ensuite `127.0.0.1`, non autorisé par le `redirect_uri` Keycloak configuré pour `localhost`; la configuration est maintenant alignée sur `http://localhost:3000`.

Le helper de connexion attendait le bouton local alors que l’initialisation OIDC avait déjà redirigé vers Keycloak. Il accepte désormais les deux chemins. Enfin, le premier parcours métier a révélé un jeton interservice expiré : le provider OAuth mettait le JWT en cache sans respecter `expires_in`. Le renouvellement anticipé et le retry unique sur `401` ont été ajoutés et testés. Après reconstruction complète, le parcours CC ciblé puis les huit E2E passent.

Une revue indépendante du diff indexé a ensuite identifié trois P1 supplémentaires. Le PATCH Action et les listes filtrées validaient insuffisamment le périmètre objet; ils délèguent désormais la validation au service propriétaire avec le jeton utilisateur. La génération et l’expiration n’avaient pas de claim concurrent; elles utilisent respectivement un advisory lock non bloquant et `FOR UPDATE SKIP LOCKED`. Enfin, Action appelait Opportunity avant son commit local; la migration `0011` introduit une commande de saga durable, auditée et reprenable. Les réponses OAuth malformées et les refresh concurrents ont également été couverts.

## Risques résiduels et suite

Le flux Action→Opportunity est une **saga persistante, convergente et rejouable**, mais il ne constitue pas une transaction ACID distribuée. Il n’existe pas encore de dispatcher permanent qui reprenne automatiquement les commandes `FAILED`; le pilote les reprend au rejeu de la même clé idempotente. Une exploitation de production devrait ajouter ce worker avec backoff, limite de tentatives et alerte sur file morte.

Ce lot ne couvre pas encore la synchronisation contrôlée de portefeuille, l’export Excel, l’envoi SMTP, les libellés administrables, la campagne d’accessibilité, les captures responsive formelles, la charge 50 000 clients ni les documents pitch/pilote/FAQ. Ces éléments restent dans les lots suivants de la préparation pilote. Aucun résultat de performance n’est revendiqué avant l’existence d’un artefact de run.

## Références

[1]: ../audit/ETAT-REEL-2026-09-19.md "Audit consolidé de préparation pilote"
[2]: ../api.md "Contrats API-first — BOA SME Opportunity Intelligence"
[3]: ../business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[4]: ../DECISIONS.md "Journal des décisions"
