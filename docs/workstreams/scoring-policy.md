# Opportunity Scoring Policy — domaine et intégration

> **Statut courant : intégré, persistant et validé par E2E.** Le texte ci-dessous conserve le contrat et le plan qui ont guidé l’implémentation. Voir [`../finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) pour les preuves actuelles.

**Workstream :** scoring policy versionnée pour `Opportunity`
**Statut :** contrat de domaine pur et plan d’intégration
**Périmètre POC :** les composants implémentés dans `backend/src/boa_oi/scoring_policy/` ne dépendent ni de SQLAlchemy, ni de FastAPI, ni d’un identity provider.

## 1. Finalité et invariants

Une **Opportunity Scoring Policy** est une configuration nommée par `policyId`, composée de versions immuables et ordonnées. Une version porte `version`, `weights`, `status`, sa fenêtre d’effectivité, son auteur, son approbateur et le motif de l’approbation ou de l’opération. Elle permet à `Opportunity` de conserver exactement la politique ayant produit un score, sans recalculer l’historique lorsqu’une politique change.

Le domaine est déterministe et pur : les services d’application lui fournissent l’horodatage, l’identité d’acteur et l’identifiant de simulation. Les valeurs de pondération restent des données de configuration. **POC explicitement marqué :** l’invariant actuel exige que les poids soient des nombres finis non négatifs et que leur somme soit exactement `1`; les noms de composantes sont libres (`rules`, `propensity`, etc.) et aucune pondération métier n’est codée dans le domaine.

Les invariants bloquants sont les suivants :

1. une version est immuable après construction (`frozen`), et toute révision crée `version + 1` en `DRAFT` ;
2. un `policyId` ne peut contenir qu’une version unique par numéro, dans l’ordre croissant ;
3. une version ne devient exécutable par `Opportunity` qu’en `ACTIVE` et dans sa fenêtre `effectiveFrom` inclusive / `effectiveTo` exclusive ;
4. le workflow autorisé est `DRAFT → SIMULATED → SUBMITTED → APPROVED → PUBLISHED → ACTIVE`, avec sorties vers `DISABLED` ou `ROLLED_BACK` selon le contexte ;
5. `SIMULATED` exige une référence de simulation persistée par le service d’application ;
6. `APPROVED`, `PUBLISHED` et `ACTIVE` exigent un approbateur, un motif d’approbation et une date d’approbation ;
7. l’auteur d’une version ne peut jamais l’approuver, y compris avec un rôle administrateur ;
8. `DISABLED` et `ROLLED_BACK` exigent un motif opérationnel ;
9. un rollback ne réécrit jamais l’historique : la version courante est marquée `ROLLED_BACK` et une version antérieure publiée/active est réactivée ;
10. chaque création et transition ajoute un événement d’audit immuable avec acteur, horodatage, états source/cible, motif et métadonnées.

## 2. Modèle de domaine

Le module expose `ScoringPolicy` (agrégat), `ScoringPolicyVersion` (version), `ScoringPolicyAuditEvent` (événement) et les énumérations `PolicyStatus` / `PolicyAuditEventType`. Les alias `OpportunityScoringPolicy` et `OpportunityScoringPolicyVersion` sont fournis pour les adaptateurs dont le vocabulaire est centré sur Opportunity.

| Objet | Attributs principaux | Règle |
|---|---|---|
| `ScoringPolicy` | `policyId`, `versions[]`, `activeVersion`, `auditEvents[]` | historique ordonné ; un seul pointeur actif |
| `ScoringPolicyVersion` | `policyId`, `version`, `weights`, `status`, `effectiveFrom`, `effectiveTo`, `authorId`, `approverId`, `approvalReason`, `approvedAt`, `reason`, `simulationId`, `auditEvents[]` | version immuable et autonome |
| `ScoringPolicyAuditEvent` | `eventId`, `policyId`, `version`, `eventType`, `actorId`, `occurredAt`, `fromStatus`, `toStatus`, `reason`, `metadata` | append-only ; aucune suppression |
| `PolicyApproval` | `approverId`, `reason`, `decidedAt` | valeur de contrat pour persister une décision d’approbation |

Événements prévus : `CREATED`, `VERSION_CREATED`, `SIMULATED`, `SUBMITTED`, `APPROVED`, `PUBLISHED`, `ACTIVATED`, `DISABLED`, `ROLLED_BACK`, `ROLLBACK_ACTIVATED`.

## 3. Tables de persistance nécessaires

Le domaine ne crée pas les tables. Le service propriétaire recommandé est `scoring-policy-service` (ou le bounded context Rule Management si la plateforme conserve ce service). Les tables ci-dessous sont le contrat d’intégration PostgreSQL cible ; elles ne doivent pas être ajoutées au périmètre du module pur sans migration dédiée.

### `scoring_policies`

| Colonne | Type logique | Contraintes |
|---|---|---|
| `id` | UUID opaque | PK |
| `policy_id` | varchar | UNIQUE, stable, `policyId` public |
| `current_version` | integer | non nul, positif |
| `active_version` | integer nullable | FK logique vers `(policy_id, version)` ; au plus une active |
| `created_at`, `updated_at` | timestamptz | serveur |
| `created_by` | varchar | sujet OIDC |

### `scoring_policy_versions`

| Colonne | Type logique | Contraintes |
|---|---|---|
| `id` | UUID opaque | PK |
| `policy_id` | varchar | FK logique vers `scoring_policies.policy_id` |
| `version` | integer | UNIQUE `(policy_id, version)`, positif |
| `weights_json` | JSONB | objet non vide ; nombres finis non négatifs ; somme `1` côté domaine |
| `status` | varchar | enum exact du domaine |
| `effective_from`, `effective_to` | timestamptz nullable | `from < to`, borne de fin exclusive |
| `author_subject_id` | varchar | non nul |
| `approver_subject_id` | varchar nullable | différent de l’auteur lorsqu’il est présent |
| `approval_reason` | text nullable | obligatoire dès `APPROVED` |
| `approved_at` | timestamptz nullable | obligatoire dès `APPROVED` |
| `reason` | text nullable | motif de création/révision/transition |
| `simulation_id` | varchar nullable | obligatoire dès `SIMULATED` |
| `definition_checksum` | char(64) | SHA-256 du JSON canonique incluant `policyId`, `version`, `weights` et métadonnées métier |
| `created_at` | timestamptz | serveur |

La ligne de version est **append-only** pour les attributs de définition. Les transitions peuvent être persistées comme changement de statut contrôlé dans une transaction, mais l’état précédent doit toujours rester récupérable via l’audit. Une version `ACTIVE` ne doit pas être éditée en place ; une modification crée une nouvelle ligne `version + 1`.

### `scoring_policy_approvals`

| Colonne | Type logique | Contraintes |
|---|---|---|
| `id` | UUID opaque | PK |
| `policy_id`, `version` | clé logique | FK vers version |
| `decision` | varchar | `APPROVED` (extensible à `REJECTED` si le contrat le prévoit) |
| `approver_subject_id` | varchar | différent de `author_subject_id` |
| `reason` | text | non vide |
| `decided_at` | timestamptz | non nul |

Cette table sépare la décision d’approbation de la projection de statut et permet une preuve de séparation des tâches.

### `scoring_policy_audit_events`

| Colonne | Type logique | Contraintes |
|---|---|---|
| `event_id` | UUID opaque | PK |
| `policy_id`, `version` | clé logique | indexés |
| `event_type` | varchar | enum du domaine |
| `actor_subject_id` | varchar | non nul |
| `occurred_at` | timestamptz | non nul, index temporel |
| `from_status`, `to_status` | varchar nullable | états source/cible |
| `reason` | text nullable | motif fourni par l’acteur |
| `metadata_json` | JSONB | références de simulation, rollback, corrélation, checksum ; pas de secret |
| `correlation_id` | varchar | indexé |

Aucun `DELETE` métier n’est autorisé sur cette table. La rétention, l’archivage et le chiffrement relèvent de la plateforme d’audit.

### `scoring_policy_simulations` (référence d’intégration)

La simulation peut être possédée par `scoring-policy-service` ou par un `rule-simulation-service`. Elle doit au minimum exposer `simulationId`, `policyId`, `version`, `status`, `datasetWatermark`, `requestedBy`, `createdAt`, `completedAt`, `resultChecksum` et un résultat agrégé. La transition vers `SIMULATED` est interdite sans un résultat `SUCCEEDED` vérifiable.

## 4. Endpoints proposés

Le Gateway expose les routes publiques sous `/api/v1/scoring-policies`; le service expose les routes internes sous `/internal/v1/scoring-policies`. Toutes les commandes propagent `X-Correlation-ID`; les mutations concurrentes utilisent `If-Match`; les créations et commandes asynchrones utilisent `Idempotency-Key` lorsque le Gateway l’exige.

| Méthode et route | Rôle | Résultat / erreurs principales |
|---|---|---|
| `POST /api/v1/scoring-policies` | créer `policyId` + v1 `DRAFT` | `201`; `409` doublon, `422` poids invalides |
| `GET /api/v1/scoring-policies` | lister les policies | `200` paginé, filtre `status`, `policyId` |
| `GET /api/v1/scoring-policies/{policyId}` | lire l’agrégat et la version active | `200`, `404` |
| `GET /api/v1/scoring-policies/{policyId}/versions` | historique immuable | `200` paginé, jamais de suppression |
| `GET /api/v1/scoring-policies/{policyId}/versions/{version}` | lire une version exacte | `200`, `404` |
| `POST /api/v1/scoring-policies/{policyId}/versions` | créer la version suivante en `DRAFT` | `201`, `409` concurrence |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/simulate` | lancer ou référencer une simulation | `202` avec `simulationId`; `409` état invalide |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/submit` | soumettre la version | `200`; `409` état invalide |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/approve` | approuver avec `reason` | `200`; `403 SELF_APPROVAL_FORBIDDEN`; `409`; `422` motif absent |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/publish` | publier après approbation | `202` ou `200` selon orchestration ; `409` si non approuvée |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/activate` | activer atomiquement, avec `effectiveFrom` | `200`; une seule active |
| `POST /api/v1/scoring-policies/{policyId}/versions/{version}/disable` | désactiver avec motif | `200`; `422` motif absent |
| `POST /api/v1/scoring-policies/{policyId}/rollback` | réactiver `targetVersion` | `200`; current devient `ROLLED_BACK`, cible `ACTIVE` |
| `GET /api/v1/scoring-policies/{policyId}/audit` | lire l’audit append-only | `200` paginé |
| `GET /internal/v1/scoring-policies/active` | bundle des seules versions actives | `200`; utilisé par Opportunity/engine |
| `GET /internal/v1/scoring-policies/{policyId}/versions/{version}/decision-context` | récupérer checksum et métadonnées d’exécution | `200`; pas de mutation |

Les corps JSON reprennent les noms camelCase du domaine. Une erreur `409 INVALID_POLICY_TRANSITION` identifie l’état courant et l’état requis ; une erreur `403 SELF_APPROVAL_FORBIDDEN` ne révèle pas de données sensibles ; `412` est utilisé lorsque `If-Match` ne correspond plus.

## 5. Intégration dans Opportunity

`Opportunity` reste propriétaire de la décision d’opportunité et de ses preuves. Il ne lit jamais les tables scoring policy directement et ne peut ni créer, ni approuver, ni publier une policy.

### Flux de production

1. L’orchestrateur Opportunity obtient un snapshot Analytics/features et un `asOf`.
2. Il demande à `scoring-policy-service` le bundle actif correspondant au périmètre, ou consomme un cache validé par `(policyId, version, definitionChecksum)`.
3. Le moteur calcule le score avec les poids reçus ; aucune valeur de poids n’est redéfinie dans Opportunity.
4. Lors de la persistance, `opportunities` conserve `scoring_policy_id`, `scoring_policy_version`, `scoring_policy_checksum`, `score`, `score_components_json`, `as_of` et `generated_at`.
5. `opportunity_evidence` conserve les composantes et références de snapshot utilisées, sans recopier un secret ni la totalité des données sources.
6. `audit_logs`/`decision_audit` conserve la corrélation, les identifiants de policy et le checksum ; un rollback n’altère jamais les opportunités déjà produites.

### Contrat interne minimal pour Opportunity

```json
{
  "policyId": "OPP-SCORE-001",
  "version": 3,
  "status": "ACTIVE",
  "effectiveFrom": "2026-01-01T00:00:00Z",
  "effectiveTo": null,
  "weights": { "rules": 0.65, "propensity": 0.35 },
  "definitionChecksum": "sha256..."
}
```

Opportunity doit refuser un bundle dont le statut n’est pas `ACTIVE`, dont la fenêtre ne couvre pas `asOf`, dont le checksum est invalide ou dont les poids ne sont pas normalisés. En cas d’indisponibilité du service, le comportement de repli doit être explicitement décidé par l’architecture : **il n’est pas permis de hardcoder une pondération de secours dans le moteur**.

### Événements d’intégration

Le service peut publier `ScoringPolicyPublished`, `ScoringPolicyActivated`, `ScoringPolicyDisabled` et `ScoringPolicyRolledBack` via une outbox. Le consommateur Opportunity invalide son cache sur `Activated`, `Disabled` et `RolledBack`, puis recharge le bundle actif. Chaque message contient `eventId`, `policyId`, `version`, `status`, `definitionChecksum`, `occurredAt` et `correlationId`. La livraison est au moins une fois ; le consommateur doit être idempotent par `eventId`.

## 6. Rôles et séparation des tâches

| Commande | Rôle minimal recommandé | Contrôle domaine |
|---|---|---|
| créer/réviser | `SCORING_POLICY_AUTHOR` | auteur enregistré |
| simuler/soumettre | `SCORING_POLICY_AUTHOR` | simulation référencée |
| approuver | `SCORING_POLICY_APPROVER` | approbateur différent de l’auteur |
| publier/activer | `SCORING_POLICY_OPERATOR` | approbation déjà enregistrée |
| désactiver/rollback | `SCORING_POLICY_OPERATOR` | motif obligatoire, audit obligatoire |
| lire/auditer | `SCORING_POLICY_VIEWER` / audit | périmètre Gateway |

La plateforme doit dériver `actorId` du JWT et ne doit jamais accepter un acteur arbitraire dans le corps de la requête. Les droits de rôle et de périmètre sont des contrôles d’application ; les invariants de version, de workflow et de séparation auteur-approbateur restent contrôlés dans le domaine.

## 7. Points à implémenter hors de ce workstream

Les migrations SQL, repositories, endpoints FastAPI, outbox, vérification de checksum, appels Analytics/Rule Engine, enrichissement du modèle `Opportunity`, RBAC Gateway et métriques opérationnelles sont des intégrations ultérieures. Ils doivent consommer le domaine sans le modifier et respecter les tables/endpoints ci-dessus. Les champs ou règles spécifiques au catalogue produit, aux seuils de score et aux segments ne doivent pas être ajoutés en dur dans `scoring_policy`.
