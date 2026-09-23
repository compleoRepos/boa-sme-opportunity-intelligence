# Financial Intelligence API — contrat `fi.v1`

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Statut et périmètre

La **Financial Intelligence API** est une capacité de lecture et de composition ajoutée à la plateforme BOA SME Opportunity Intelligence. Elle est destinée à une démonstration B2B contrôlée pour des fonds, holdings et partenaires autorisés. Le lot utilise exclusivement le dataset synthétique du dépôt et chaque enveloppe déclare `syntheticData=true`, `nonProduction=true` et `NO_CREDIT_DECISION`.

La capacité ne décide ni l’éligibilité, ni l’octroi, ni le refus, ni une limite, ni une tarification. L’exécution opérationnelle reste déterministe et rules-only. Une réponse n’atteste `POC_SHADOW`, `rulesWeight=1` et `mlWeight=0` que lorsque Portfolio Service fournit exactement ces métadonnées dans un objet conforme ; une structure mal typée, incomplète ou contenant un champ inconnu est refusée en `502 DEPENDENCY_INVALID_RESPONSE`. Si Portfolio est indisponible, `mlGovernanceStatus=UNAVAILABLE` et les quatre valeurs ML restent `null`. Le ML est CPU-only, sans LLM ni GPU. Les seuils, usages, SLO et contrats juridiques sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Frontière et ownership

Le Gateway est l’unique frontière publique. Le service `financial-intelligence-service` possède uniquement les entitlements B2B, la composition et l’audit d’accès. Il n’accède pas directement aux tables métier Customer, Transaction, Analytics, Signal, Opportunity ou Portfolio : il appelle leurs contrats internes avec une identité technique OAuth2 distincte du bearer externe.

| Domaine propriétaire | Données réutilisées par FI | Ce que FI ne fait pas |
|---|---|---|
| Customer | identité société et visibilité multibancaire point-in-time | aucun master client parallèle |
| Analytics | agrégats `BOOKED` 30/90/365 jours | aucune lecture de transaction brute |
| Signal | signaux persistés et versions de règle | aucune détection parallèle |
| Opportunity | opportunités existantes, priorité et preuves | aucune création ou repriorisation |
| Portfolio | projection rules-only et lineage shadow | aucune activation ML |
| Financial Intelligence | grants, memberships externes, composition, audit | aucune décision de crédit |

## Authentification et autorisation

Les routes publiques exigent un token OAuth2/OIDC valide portant le rôle d’accès FI `EXTERNAL_CONSUMER` sans rôle privilégié `ADMIN` ou `SERVICE`. Un token mixte `EXTERNAL_CONSUMER` + `ADMIN|SERVICE` est refusé au Gateway puis au service FI. Les scopes sont explicites : `financial.read`, `signals.read`, `opportunities.read` et `portfolio.read`. Le backend exige un `client_id` OAuth non vide et croise le sujet, ce client, les scopes du token, les scopes maximaux du Consumer et le `DataAccessGrant` actif. Le grant doit porter exactement la finalité `SYNTHETIC_PORTFOLIO_MONITORING` ; aucun grant sans client et aucun joker de scope ne sont acceptés.

Une ressource inconnue et une ressource hors périmètre renvoient uniformément `404 RESOURCE_NOT_FOUND`. Un scope absent renvoie `403 INSUFFICIENT_SCOPE`. Un token absent ou invalide renvoie `401`. Un grant révoqué, expiré, non démarré ou destiné à un autre sujet/client ne permet aucun accès. Les paramètres inconnus, dont `consumerId`, sont rejetés par `400 UNKNOWN_FILTER` ; le client ne peut donc jamais élargir son périmètre en modifiant l’URL.

## Routes publiques

| Méthode et chemin | Scopes requis | Réponse |
|---|---|---|
| `GET /api/v1/financial-intelligence/portfolios?asOf=YYYY-MM-DD&pageSize=50&offset=0` | `financial.read`, `portfolio.read` | catalogue paginé des portfolios autorisés |
| `GET /api/v1/financial-intelligence/portfolios/{portfolioId}/summary?asOf=...` | `financial.read`, `portfolio.read` | agrégats et sociétés du portfolio, maximum 500 PME |
| `GET /api/v1/financial-intelligence/companies/{companyId}/summary?asOf=...` | `financial.read` | synthèse société minimisée |
| `GET /api/v1/financial-intelligence/companies/{companyId}/signals?asOf=...` | `financial.read`, `signals.read` | signaux persistés et explicables |
| `GET /api/v1/financial-intelligence/companies/{companyId}/opportunities?asOf=...` | `financial.read`, `opportunities.read` | opportunités existantes uniquement |
| `GET /api/v1/financial-intelligence/companies/{companyId}/cash-position?asOf=...` | `financial.read` | agrégats de position de trésorerie disponibles |
| `GET /api/v1/financial-intelligence/companies/{companyId}/flow-summary?asOf=...` | `financial.read` | agrégats d’encaissements et décaissements disponibles |

Aucune route d’écriture, de recompute, d’export, de décision de crédit ou de transaction brute n’est exposée. Le chemin volontairement non documenté `credit-decision` renvoie toujours `404`.

## Enveloppe et provenance

Chaque réponse suit l’enveloppe `fi.v1` :

```json
{
  "data": {},
  "meta": {
    "contractVersion": "fi.v1",
    "asOf": "2026-09-30",
    "generatedAt": "2026-09-30T12:00:00Z",
    "traceId": "correlation-id",
    "requestId": "correlation-id",
    "sources": ["analytics-service", "customer-service"],
    "calculationVersion": "fi-composition-1.0.0",
    "featureVersion": "feature-set-version-or-null",
    "modelVersion": "shadow-model-version-or-null",
    "trainingDatasetVersion": null,
    "deploymentMode": "POC_SHADOW",
    "mlGovernanceStatus": "VERIFIED",
    "sourceStatus": [],
    "partial": false,
    "executionMode": "DETERMINISTIC_RULES",
    "mlMode": "POC_SHADOW",
    "rulesWeight": 1,
    "mlWeight": 0,
    "syntheticData": true,
    "nonProduction": true,
    "downstreamCallCount": 5,
    "fanOutConcurrency": 5
  }
}
```

`sourceStatus` distingue `AVAILABLE`, `EMPTY`, `UNAVAILABLE` et `NOT_IMPLEMENTED`. Une dépendance `UNAVAILABLE` ou une capacité `NOT_IMPLEMENTED` rend `partial=true`; aucune valeur n’est fabriquée. `mlGovernanceStatus` distingue `VERIFIED`, `UNAVAILABLE` et `NOT_APPLICABLE`. En dehors de `VERIFIED`, `deploymentMode`, `mlMode`, `rulesWeight` et `mlWeight` sont obligatoirement `null`. Les métriques sans support propriétaire restent `null` et sont signalées `NOT_IMPLEMENTED — BLOCKED` dans l’interface.

## Sémantique financière et minimisation

Les indicateurs sont des projections des métriques Analytics existantes et conservent leur `asOf`, période, qualité, couverture et taille d’échantillon. Le calcul Analytics existant exclut les transactions non `BOOKED`. La visibilité multibancaire est reprise du Lot 15 sans modification de ses règles `DECLARED`, `TURNOVER_RATIO`, `TRANSACTION_FINGERPRINTS` et `NONE`.

Le contrat interdit les IBAN, numéros de compte, identifiants de transaction, contreparties, informations de remise et listes de transactions brutes. Les signaux sont référencés par `signalRef`; les opportunités par `opportunityId`. Leurs versions de règle, moteur, politique de scoring et références de preuve sont conservées lorsqu’elles existent. Les statuts courants Signal et Opportunity ne sont pas historisés par les domaines propriétaires : FI renvoie donc `status=null`, `stateAsOfStatus=NOT_IMPLEMENTED` et un `sourceStatus` explicite plutôt que de les présenter comme des états historiques.

## Point-in-time, limites et résilience

`asOf` est obligatoire. Les memberships de portfolio sont filtrés par `validFrom <= asOf < validUntil`. Après le filtrage demandé aux domaines propriétaires, le compositeur réapplique localement la fenêtre inclusive `[asOf-364 jours, asOf]` aux signaux et opportunités : une ligne future ou trop ancienne est exclue, ainsi qu’une opportunité dont `expiresAt` est antérieur à la fin de journée `asOf`. La propension Portfolio est appelée avec le même `asOf`, sélectionne uniquement un score dont `score.as_of_date <= asOf` et dont `valid_until` est nul ou supérieur ou égal à `asOf`, puis exclut de son score rules-only toute opportunité générée après la fin de journée `asOf` ou expirée avant cette borne. La sélection de visibilité accepte également une borne `asOf` et rejette alors tout snapshot futur. La fenêtre de validité est la source de vérité historique : `status` décrit l’état courant de la ligne et ne remplace jamais cette fenêtre ; un membership actuellement `INACTIVE` reste donc valide pour une date historique strictement antérieure à `validUntil`, et la base refuse `INACTIVE` sans date de fin. L’autorisation et les grants sont évalués à l’instant d’accès, non à la date historique demandée.

L’endpoint propriétaire Portfolio de propension accepte encore l’absence de `asOf` pour les dashboards internes non FI : cette forme signifie « dernier snapshot cohérent » et non « état historique courant ». Elle exclut les enregistrements dont `valid_until < as_of_date`. La surface FI n’utilise jamais cette forme et transmet toujours son `asOf` obligatoire.

Le catalogue accepte `pageSize` de 1 à 100 et `offset >= 0`. Une composition portfolio est limitée à 500 PME et utilise une concurrence bornée de 1 à 25, configurée par `FI_PORTFOLIO_CONCURRENCY`. Chaque appel propriétaire possède un timeout configuré par `FI_DEPENDENCY_TIMEOUT_SECONDS`. Les limites et objectifs de latence restent une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Erreurs principales

| HTTP | Code | Signification |
|---:|---|---|
| 400 | `UNKNOWN_FILTER` | filtre non documenté, dont injection de périmètre |
| 401 | `AUTHENTICATION_REQUIRED` | token absent ou invalide |
| 403 | `INSUFFICIENT_SCOPE` | scopes OIDC ou Consumer insuffisants |
| 403 | `FI_CLIENT_BINDING_REQUIRED` | identifiant de client OAuth absent |
| 404 | `RESOURCE_NOT_FOUND` | ressource inconnue ou hors périmètre, sans fuite |
| 422 | `FI_PORTFOLIO_LIMIT_EXCEEDED` | plus de 500 PME dans une composition |
| 500 | `FI_MINIMIZATION_FAILURE` | garde de sortie ayant détecté un champ interdit |
| 502 | `DEPENDENCY_INVALID_RESPONSE` | invariant rules-only invalide dans un domaine propriétaire |
| 503 | `DEPENDENCY_UNAVAILABLE` | dépendance indispensable indisponible |

## Compatibilité

Le contrat initial est `fi.v1`. Toute suppression ou modification sémantique nécessite une nouvelle version. Les extensions additives doivent conserver les garde-fous, la minimisation, le point-in-time, la non-fuite et le mode rules-only. Le mapping BIAN reste **candidat et à valider avec BOA** ; aucune conformité BIAN intégrale n’est revendiquée.
