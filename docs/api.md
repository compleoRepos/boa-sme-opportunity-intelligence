# Contrats API-first — BOA SME Opportunity Intelligence

**Statut :** contrat cible du MVP  
**Version du contrat :** `1.6.0`
**Préfixe public :** `/api/v1`  
**Préfixe interne :** `/internal/v1`  
**Format :** REST/JSON et XLSX, OpenAPI 3.0
**Source normative :** exigences du MVP [1]

## 1. Objet et principes contractuels

Ce document définit les contrats d’interface du MVP **BOA SME Opportunity Intelligence**. Il précise les APIs exposées au Relationship Manager (RM), les APIs privées utilisées entre microservices, les formats communs, les règles de sécurité et les dépendances d’intégration.

Le système transforme des données transactionnelles synthétiques en métriques, signaux puis opportunités commerciales explicables. Il ne réalise ni scoring de crédit, ni décision de crédit, ni calcul de probabilité de défaut. Le type `FINANCIAL_STRESS_SIGNAL` reste un **signal commercial et relationnel**.

Les décisions suivantes sont normatives :

- Le frontend ne contacte jamais une base de données ni un microservice directement. Il appelle uniquement l’API Gateway.
- Les routes publiques sont versionnées sous `/api/v1`. Les routes privées sont réservées au réseau de services et portent `/internal/v1`.
- Les identifiants sont opaques et stables. Ils ne doivent pas exposer de clé technique séquentielle.
- Les listes sont paginées côté serveur. La taille maximale d’une page est contrôlée par le serveur.
- Les décisions du moteur sont déterministes, explicables, versionnées et auditables.
- Les noms de produits, seuils et règles sont fournis par leurs services de référence. Ils ne sont pas codés dans le frontend ou dans une réponse simulée.
- Les adaptateurs bancaires sont invoqués derrière `banking-integration-service`. Le moteur ne connaît pas les APIs du Core Banking, des paiements ou du Trade Finance.

## 2. Surface d’exposition et services

### 2.1 API Gateway

Le Gateway est le seul point d’entrée public. Il assure la validation JWT, le contrôle RBAC, le filtrage par périmètre RM/agence, le routage, la limitation de débit, la propagation du `X-Correlation-ID`, le contrôle de version et la normalisation des erreurs.

Les URLs publiques sont de la forme :

```text
https://<host>/api/v1/...
```

Les URLs internes ne sont pas routables depuis Internet :

```text
http://<service>:<port>/internal/v1/...
```

### 2.2 Bounded contexts et ownership

| Service | Responsabilité | Données possédées | Domaine BIAN-inspired |
|---|---|---|---|
| `api-gateway` | Entrée, authN/authZ, routage, quotas, corrélation | Aucun domaine métier | API Gateway / orchestration |
| `customer-service` | PME, profil, segment, affectation RM | `customers`, relation RM | Party Reference Data Management |
| `account-service` | Comptes, soldes, statut, devise | `accounts`, `balances` | Current Account / Current Account Service |
| `transaction-service` | Mouvements et recherche transactionnelle | `transactions` | Payment / Payment Execution |
| `banking-integration-service` | Anti-corruption layer vers les systèmes bancaires | État d’import, références externes | Banking Integration |
| `analytics-service` | Métriques et comparaisons historiques | `financial_metrics`, agrégats | Financial Analysis |
| `signal-service` | Détection de signaux et leur preuve | `signals` | Financial Analysis / Event Detection |
| `opportunity-service` | Opportunités, confiance, priorité, explication | `opportunities`, `opportunity_evidence`, décisions moteur | Sales Opportunity Management |
| `product-service` | Catalogue et éligibilité de produits | `products`, règles de catalogue | Product Management / Product Directory |
| `action-service` | Actions RM et résultats commerciaux | `opportunity_actions`, outcomes | Customer Offer / Sales Action |
| `audit/observability` | Audit, santé, métriques techniques | `audit_logs`, métriques/traces | Contrôle transversal |

Le mapping est une inspiration de séparation de responsabilités et ne constitue pas une certification BIAN.

## 3. Conventions HTTP communes

### 3.1 Méthodes et représentation

Les APIs utilisent `GET` pour la lecture, `POST` pour la création ou le lancement d’un traitement, `PATCH` pour une modification partielle et `DELETE` uniquement lorsque la suppression métier est explicitement autorisée. Une suppression physique d’une décision moteur ou d’un audit est interdite dans le MVP.

Les requêtes et réponses métier utilisent `Content-Type: application/json`. Les dates sont au format RFC 3339 UTC, par exemple `2026-09-18T08:00:00Z`. Les montants sont représentés par un nombre décimal JSON accompagné d’une devise ISO 4217. Les pourcentages et taux de croissance sont des décimaux entre `-1` et `+∞`, par exemple `0.365` pour `36,5 %`.

Les noms de propriétés JSON sont en `camelCase`. Les énumérations sont en majuscules avec underscore. Les champs inconnus doivent être ignorés par les clients afin de permettre l’ajout rétrocompatible de propriétés.

### 3.2 Headers obligatoires et recommandés

| Header | Direction | Obligatoire | Règle |
|---|---|---:|---|
| `Authorization: Bearer <JWT>` | Client → Gateway | Oui pour `/api/v1` | Jeton OIDC signé, non expiré, audience attendue |
| `X-Correlation-ID` | Toutes | Oui côté Gateway, généré si absent | UUID ou identifiant opaque de 16 à 128 caractères |
| `traceparent` | Toutes | Recommandé | Format W3C Trace Context, propagé sans modification s’il est valide |
| `Content-Type: application/json` | Requête avec corps | Oui | Corps JSON UTF-8 |
| `Accept: application/json` | Client → service | Recommandé | Le serveur retourne JSON |
| `Idempotency-Key` | `POST` créant une action/import | Obligatoire selon endpoint | Clé opaque, TTL minimum 24 h |
| `If-Match` | `PATCH` concurrent | Recommandé | ETag de la représentation lue précédemment |
| `X-Service-Name` | Service → service | Interne | Injecté par la plateforme, jamais accepté du client |

Le Gateway renvoie toujours `X-Correlation-ID` dans la réponse, y compris en cas d’erreur. Un service conserve le même identifiant dans ses logs, événements et appels sortants. Il ne doit pas générer un nouvel identifiant pour remplacer celui du Gateway.

### 3.3 Statuts HTTP

| Statut | Usage contractuel |
|---:|---|
| `200` | Lecture ou modification réussie avec représentation retournée |
| `201` | Ressource créée; le header `Location` est retourné lorsque pertinent |
| `202` | Traitement accepté de manière asynchrone; un identifiant de job est retourné |
| `204` | Succès sans corps |
| `304` | Ressource inchangée avec `If-None-Match` |
| `400` | Requête syntaxiquement invalide ou paramètre impossible |
| `401` | Jeton absent, invalide ou expiré |
| `403` | Jeton valide mais rôle ou périmètre insuffisant |
| `404` | Ressource non trouvée dans le périmètre autorisé |
| `409` | Conflit d’état, doublon ou idempotence avec contenu différent |
| `412` | Échec de précondition `If-Match` |
| `422` | JSON valide mais règle de validation métier non satisfaite |
| `429` | Limite de débit atteinte; `Retry-After` est retourné |
| `500` | Erreur interne non exposée en détail |
| `502` | Dépendance distante indisponible ou réponse invalide |
| `503` | Service non prêt ou temporairement indisponible |
| `504` | Timeout d’une dépendance |

## 4. Pagination, tri, recherche et filtres

### 4.1 Contrat de pagination

Toutes les listes importantes utilisent une pagination par curseur opaque. Le curseur encode l’état de tri serveur et ne doit pas être interprété par le client.

Paramètres communs :

| Paramètre | Type | Défaut | Contraintes |
|---|---|---:|---|
| `pageSize` | entier | `25` | `1..100`; le serveur peut réduire la valeur |
| `cursor` | chaîne | absent | Valeur retournée dans `meta.nextCursor` |
| `sort` | chaîne | dépend de la ressource | Champ autorisé, préfixe `-` pour décroissant |
| `q` | chaîne | absent | Recherche textuelle bornée au périmètre de la ressource |

Réponse standard :

```json
{
  "data": [],
  "meta": {
    "pageSize": 25,
    "nextCursor": "eyJvZmZzZXQiOjI1LCJzb3J0IjoicHJpb3JpdHlTY29yZSJ9",
    "hasMore": true,
    "totalCount": null
  },
  "links": {
    "self": "/api/v1/opportunities?pageSize=25",
    "next": "/api/v1/opportunities?pageSize=25&cursor=eyJ..."
  }
}
```

`totalCount` est facultatif et peut être `null` pour éviter une requête coûteuse. Il n’est jamais utilisé pour calculer le curseur. Une réponse de liste vide est un succès `200` avec `data: []`.

### 4.2 Filtres communs

Les valeurs de filtre doivent être répétées pour plusieurs choix, par exemple `type=TRADE_FINANCE&type=CASH_INVESTMENT`. Les dates sont inclusives au début et exclusives à la fin : `fromDate=2026-09-01&toDate=2026-10-01` couvre septembre.

Filtres métier du dashboard :

- opportunités : `type`, `minConfidence`, `maxConfidence`, `priorityLevel`, `sector`, `customerSegment`, `relationshipManagerId`, `horizon`, `fromDate`, `toDate`, `status` ;
- clients : `q`, `customerId`, `companyName`, `industry`, `sector`, `segment`, `relationshipManagerId` ;
- transactions : `customerId`, `accountId`, `fromDate`, `toDate`, `type`, `direction`, `currency`, `category`, `international`, `minAmount`, `maxAmount` ;
- signaux : `customerId`, `type`, `severity`, `fromDate`, `toDate` ;
- actions : `opportunityId`, `customerId`, `actionType`, `outcome`, `assignedTo`, `fromDate`, `toDate`.

Chaque service rejette les filtres inconnus avec `400 UNKNOWN_FILTER` plutôt que de les ignorer silencieusement. Les champs de tri autorisés sont publiés dans le contrat OpenAPI de chaque service.

## 5. Authentification, autorisation et RBAC

### 5.1 Authentification OIDC

Le MVP utilise OAuth 2.0 / OpenID Connect avec l’Identity Provider local, recommandé : Keycloak. Le client obtient un access token JWT et l’envoie au Gateway. Le Gateway vérifie au minimum la signature, `iss`, `aud`, `exp`, `nbf` et, si présent, `azp`.

Le jeton doit porter :

```json
{
  "iss": "https://identity.example/realms/boa",
  "sub": "user-123",
  "aud": ["boa-sme-api"],
  "preferred_username": "rm.dupont",
  "realm_access": { "roles": ["RELATIONSHIP_MANAGER"] },
  "boa": {
    "branchIds": ["BR-001"],
    "customerScopes": ["assigned"]
  },
  "exp": 1790000000
}
```

Les secrets, mots de passe, tokens et clés API ne figurent jamais dans le dépôt ou dans une réponse API. La politique de mot de passe et la MFA éventuelle sont gérées par l’IdP.

### 5.2 Rôles et périmètres

| Rôle | Lecture | Écriture / administration | Périmètre par défaut |
|---|---|---|---|
| `RELATIONSHIP_MANAGER` | Clients, comptes, transactions autorisées, signaux, opportunités, produits actifs | Accepter/rejeter une opportunité, créer et mettre à jour ses actions | Clients qui lui sont affectés |
| `BRANCH_MANAGER` | Données de la branche, opportunités et KPI des RM de la branche | Lecture et pilotage ; action au nom d’un CC uniquement avec `actions:write:branch` | Intersection des branches du token et des affectations actives de Customer Service |
| `DATA_ANALYST` | Données analytiques, métriques, signaux, résultats agrégés | Recalcul/import selon permission dédiée; pas d’action commerciale | Périmètre analytique accordé |
| `ADMIN` | Configuration, registres et audits autorisés | Configuration des règles, activation produits/règles, administration | Aucun accès client détaillé par défaut ; scope et périmètre explicites requis |

La règle d’autorisation est l’intersection de **rôle**, **scopes**, **périmètre organisationnel**, **affectation temporelle** et **ownership**. Un `RELATIONSHIP_MANAGER` ne peut pas contourner un filtre pour lire la fiche d’un client hors de son portefeuille. Le service doit préférer `404` à `403` lorsque révéler l’existence d’une ressource hors périmètre serait une fuite d’information.

Les services internes n’acceptent pas un JWT utilisateur comme preuve suffisante. Ils exigent un token de service OAuth2 `client_credentials`, avec une audience propre au service cible, ainsi que mTLS ou un contrôle réseau équivalent en environnement déployé. Le contexte utilisateur (subject, rôles, périmètre) est propagé dans des headers internes signés par le Gateway ou dans des claims du token d’échange; il ne doit jamais être pris depuis un header client non authentifié.

### 5.3 Scopes minimaux

Scopes recommandés : `customers:read`, `accounts:read`, `transactions:read`, `analytics:read`, `signals:read`, `opportunities:read`, `opportunities:write`, `products:read`, `actions:read`, `actions:write`, `rules:read`, `rules:write`, `audit:read`, `integration:write`. Les rôles mappent vers ces scopes dans l’IdP.

## 6. Corrélation, traçabilité et idempotence

`X-Correlation-ID` identifie une requête utilisateur de bout en bout. `traceparent` identifie le span distribué. Les deux sont enregistrés dans les logs structurés avec `service`, `route`, `subject`, `statusCode`, `durationMs` et, lorsque pertinent, `resourceId`.

Les créations d’actions et déclenchements d’import/recalcul exigent `Idempotency-Key`. Une répétition avec la même clé et un corps identique retourne la réponse initiale. Une répétition avec un corps différent retourne `409 IDEMPOTENCY_KEY_REUSED`.

Les événements métier sont persistés dans une outbox locale ; un transport de messages pourra être ajouté ultérieurement sans modifier le domaine. Le contrat minimal d’un événement est :

```json
{
  "eventId": "evt_01J...",
  "eventType": "OpportunityCreated",
  "eventVersion": "1.0",
  "occurredAt": "2026-09-18T08:00:00Z",
  "producer": "opportunity-service",
  "correlationId": "corr_01J...",
  "aggregateType": "Opportunity",
  "aggregateId": "opp_01J...",
  "data": {}
}
```

Les événements sont au moins une fois délivrés. Les consommateurs doivent être idempotents. La présente version n’impose pas de broker pour le MVP, mais impose de préserver ces métadonnées.

## 7. Erreurs standardisées

Toutes les erreurs publiques et internes utilisent le même enveloppe. Les détails techniques et stack traces restent dans les logs corrélés et ne sont jamais retournés au frontend.

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "message": "One or more fields are invalid.",
  "correlationId": "corr_01J9Q0...",
  "timestamp": "2026-09-18T08:00:00Z",
  "details": [
    {
      "field": "toDate",
      "code": "DATE_RANGE_INVALID",
      "message": "toDate must be after fromDate."
    }
  ]
}
```

Codes minimaux :

| Code | HTTP | Signification |
|---|---:|---|
| `AUTHENTICATION_REQUIRED` | 401 | Access token absent ou invalide |
| `TOKEN_EXPIRED` | 401 | JWT expiré |
| `FORBIDDEN` | 403 | Rôle, scope ou périmètre insuffisant |
| `RESOURCE_NOT_FOUND` | 404 | Ressource absente ou invisible dans le périmètre |
| `CUSTOMER_NOT_FOUND` | 404 | Client inconnu dans le contexte autorisé |
| `OPPORTUNITY_NOT_FOUND` | 404 | Opportunité inconnue dans le contexte autorisé |
| `VALIDATION_ERROR` | 422 | Corps ou paramètre valide syntaxiquement mais invalide métier |
| `UNKNOWN_FILTER` | 400 | Filtre non supporté |
| `INVALID_CURSOR` | 400 | Curseur absent, expiré ou incompatible avec le tri |
| `STATE_CONFLICT` | 409 | Transition d’état non autorisée |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Clé réutilisée avec un contenu différent |
| `PRECONDITION_FAILED` | 412 | ETag obsolète |
| `RATE_LIMIT_EXCEEDED` | 429 | Quota dépassé |
| `DEPENDENCY_UNAVAILABLE` | 503 | Service dépendant non disponible |
| `DEPENDENCY_TIMEOUT` | 504 | Timeout d’un appel sortant |
| `INTERNAL_ERROR` | 500 | Erreur non détaillée au client |

Le message est stable et non sensible. Les erreurs métier de règle sont renvoyées en `422`; les erreurs de disponibilité sont séparées afin que le client puisse distinguer une absence de résultat d’un problème temporaire.

## 8. Schémas métier partagés

Les schémas ci-dessous sont les exemples normatifs abrégés réutilisés par les OpenAPI de service.

### 8.1 CustomerSummary et CustomerDetail

```json
{
  "customerId": "SME-00125",
  "legalName": "ABC Industrie SARL",
  "tradeName": "ABC Industrie",
  "industry": "INDUSTRY",
  "sector": "MANUFACTURING",
  "segment": "SME",
  "country": "MA",
  "branchId": "BR-001",
  "relationshipManagerId": "rm-104",
  "status": "ACTIVE",
  "createdAt": "2025-01-10T10:00:00Z",
  "updatedAt": "2026-09-18T07:45:00Z"
}
```

### 8.2 Account et Balance

```json
{
  "accountId": "ACC-00981",
  "customerId": "SME-00125",
  "accountType": "CURRENT_ACCOUNT",
  "currency": "MAD",
  "status": "ACTIVE",
  "openedAt": "2022-04-01",
  "balance": {
    "asOf": "2026-09-18T07:59:00Z",
    "available": 1684000.25,
    "ledger": 1712000.25,
    "currency": "MAD"
  }
}
```

### 8.3 Transaction

```json
{
  "transactionId": "TX-20260918-0001",
  "customerId": "SME-00125",
  "accountId": "ACC-00981",
  "bookingDate": "2026-09-17",
  "valueDate": "2026-09-17",
  "type": "TRANSFER",
  "direction": "CREDIT",
  "amount": 245000.00,
  "currency": "MAD",
  "category": "CUSTOMER_RECEIPT",
  "counterpartyName": "Client Distribution Nord",
  "international": false,
  "countryCode": "MA",
  "description": "Règlement facture 2026-091",
  "sourceSystem": "MOCK_CORE",
  "externalReference": "CORE-88421",
  "categoryVersion": "existing-synthetic-v1",
  "importBatchId": "55fc37c1-0e3e-4b4c-80d9-5036c699b0a2",
  "sourceRecordHash": "sha256-hex"
}
```

`categoryVersion`, `importBatchId` et `sourceRecordHash` sont renseignés pour les
transactions passées par l'ingestion gouvernée. Ils restent `null` pour les lignes
historiques antérieures à la migration `0016`; aucun backfill métier n'est inventé.

### 8.4 FinancialMetric

```json
{
  "customerId": "SME-00125",
  "metric": "monthly_inflow",
  "currentValue": 1420000.0,
  "previousPeriodValue": 1040000.0,
  "historicalBaselineValue": 1200000.0,
  "growthRate": 0.365,
  "deviationFromBaseline": 0.183,
  "period": "90D",
  "asOf": "2026-09-18T08:00:00Z",
  "currency": "MAD",
  "calculationVersion": "analytics-0.1.0"
}
```

Les périodes autorisées sont `7D`, `30D`, `90D`, `180D` et `365D`. Une métrique insuffisamment alimentée porte `dataQuality: "INSUFFICIENT_HISTORY"` et ne doit pas être utilisée seule pour créer une opportunité.

### 8.5 Signal

```json
{
  "signalId": "SIG-123",
  "customerId": "SME-00125",
  "type": "INFLOW_GROWTH",
  "severity": "MEDIUM",
  "value": 0.36,
  "threshold": 0.25,
  "period": "90D",
  "detectedAt": "2026-09-18T08:00:00Z",
  "status": "ACTIVE",
  "evidence": [
    "90-day inflows increased by 36%",
    "Growth exceeds historical baseline by 18%"
  ],
  "metricReferences": ["monthly_inflow:90D"],
  "engineVersion": "signal-0.1.0",
  "ruleVersion": "2026-09-01"
}
```

Types MVP : `INFLOW_GROWTH`, `OUTFLOW_GROWTH`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_GROWTH`, `BALANCE_SURPLUS`, `BALANCE_DECLINE`, `CREDIT_UTILIZATION_INCREASE`, `TRANSACTION_VOLUME_GROWTH`.

### 8.6 Opportunity et Explanation

```json
{
  "opportunityId": "OPP-000451",
  "customerId": "SME-00125",
  "opportunityType": "INVESTMENT_FINANCING",
  "status": "OPEN",
  "confidence": 0.86,
  "confidenceLevel": "HIGH",
  "priorityScore": 89.0,
  "priorityLevel": "P1",
  "horizon": "1-3_MONTHS",
  "why": [
    "Inflows increased by 36%",
    "Supplier payments increased by 29%",
    "Transaction volume increased by 18%"
  ],
  "what": "Évaluer un besoin de financement d’investissement ou de fonds de roulement.",
  "when": "Dans les 1 à 3 mois",
  "recommendedProducts": [
    { "productId": "PROD-INV-FIN", "name": "Investment Financing" },
    { "productId": "PROD-WC-FAC", "name": "Working Capital Facility" }
  ],
  "evidenceCount": 3,
  "generatedAt": "2026-09-18T08:00:00Z",
  "engineVersion": "opportunity-0.1.0",
  "ruleVersion": "2026-09-01",
  "lastActionAt": null
}
```

`confidence` est compris entre `0` et `1`. `confidenceLevel` est `LOW` pour `[0, 0.50)`, `MEDIUM` pour `[0.50, 0.75)` et `HIGH` pour `[0.75, 1]`, sauf configuration explicitement versionnée. `priorityScore` est un score de priorisation commerciale, jamais un score de risque.

La ressource `Explanation` retourne notamment les signaux, métriques, seuils, comparaison historique, composantes de confiance, produits recommandés, horizon et versions du moteur :

```json
{
  "opportunityId": "OPP-000451",
  "signals": [
    { "signalId": "SIG-123", "type": "INFLOW_GROWTH", "value": 0.36, "threshold": 0.25 }
  ],
  "metrics": [
    { "metric": "monthly_inflow", "period": "90D", "currentValue": 1420000, "growthRate": 0.365 }
  ],
  "thresholds": {
    "inflowGrowthThreshold": 0.25,
    "supplierGrowthThreshold": 0.20,
    "transactionVolumeGrowthThreshold": 0.15
  },
  "historicalComparison": {
    "baselinePeriod": "12M",
    "method": "previous_period_and_historical_baseline"
  },
  "confidenceComponents": [
    { "name": "INFLOW_GROWTH", "points": 20, "maxPoints": 20, "satisfied": true },
    { "name": "SUPPLIER_PAYMENT_GROWTH", "points": 20, "maxPoints": 20, "satisfied": true },
    { "name": "TRANSACTION_VOLUME_GROWTH", "points": 15, "maxPoints": 15, "satisfied": true },
    { "name": "HISTORICAL_CONSISTENCY", "points": 15, "maxPoints": 15, "satisfied": true },
    { "name": "PRODUCT_GAP", "points": 10, "maxPoints": 10, "satisfied": true },
    { "name": "RECENCY", "points": 6, "maxPoints": 10, "satisfied": true }
  ],
  "recommendedProducts": [
    { "productId": "PROD-INV-FIN", "name": "Investment Financing" }
  ],
  "horizon": "1-3_MONTHS",
  "engineVersion": "opportunity-0.1.0",
  "ruleVersion": "2026-09-01"
}
```

### 8.7 Action et outcome

```json
{
  "actionId": "ACT-00091",
  "opportunityId": "OPP-000451",
  "customerId": "SME-00125",
  "actionType": "CONTACT_CUSTOMER",
  "status": "OPEN",
  "assignedTo": "rm-104",
  "dueAt": "2026-09-25T09:00:00Z",
  "note": "Appeler le dirigeant pour qualifier l’investissement prévu.",
  "outcome": null,
  "createdAt": "2026-09-18T09:00:00Z",
  "createdBy": "user-123",
  "updatedAt": "2026-09-18T09:00:00Z"
}
```

Types d’action : `ACCEPT_OPPORTUNITY`, `DISMISS_OPPORTUNITY`, `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP`, `SCHEDULE_MEETING`, `MARK_CONVERTED`. Outcomes : `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED`, `NOT_RELEVANT`.

## 9. Endpoints publics via API Gateway

Tous les endpoints ci-dessous exigent OIDC/JWT sauf `/health`, `/ready` et la documentation OpenAPI, qui peuvent être publics dans un environnement de développement mais doivent être protégés ou restreints en production. Le Gateway applique le RBAC avant le routage.

### 9.1 Accès et documentation

| Méthode | Route | Autorisation | Réponse |
|---|---|---|---|
| `GET` | `/health` | aucune; exposition contrôlée | `200` état liveness du Gateway |
| `GET` | `/ready` | aucune; exposition contrôlée | `200` si dépendances obligatoires prêtes, sinon `503` |
| `GET` | `/metrics` | réseau d’observabilité ou `ADMIN` | `200` format métriques |
| `GET` | `/swagger` | `ADMIN` ou réseau interne | UI Swagger |
| `GET` | `/openapi.json` | `ADMIN` ou réseau interne | document OpenAPI agrégé |

### 9.2 Dashboard et opportunités

| Méthode | Route | Autorisation | Notes |
|---|---|---|---|
| `GET` | `/api/v1/opportunities` | `opportunities:read` | Pagination et filtres métier; tri par défaut `-priorityScore` |
| `GET` | `/api/v1/opportunities/{opportunityId}` | `opportunities:read` | Détail incluant `why`, `what`, `when`, confiance et produits |
| `GET` | `/api/v1/opportunities/{opportunityId}/explanation` | `opportunities:read` | Explication complète et audit de décision |
| `POST` | `/api/v1/opportunities/{opportunityId}/actions` | `opportunities:write`, `actions:write` | Crée une action et applique la transition autorisée |
| `GET` | `/api/v1/opportunities/{opportunityId}/actions` | `actions:read` | Historique des actions |
| `GET` | `/api/v1/actions` | `actions:read` | Recherche/pagination des actions du périmètre |
| `PATCH` | `/api/v1/actions/{actionId}` | `actions:write` | Mise à jour de statut, outcome, note ou échéance |

Création d’une action :

```http
POST /api/v1/opportunities/OPP-000451/actions
Authorization: Bearer <jwt>
X-Correlation-ID: corr_01J...
Idempotency-Key: action-OPP-000451-contact-20260918
Content-Type: application/json
```

```json
{
  "actionType": "CONTACT_CUSTOMER",
  "dueAt": "2026-09-25T09:00:00Z",
  "note": "Appeler le dirigeant pour qualifier l’investissement prévu."
}
```

Réponse `201` : ressource `Action`. Une transition invalide, par exemple `MARK_CONVERTED` avant une action de suivi ou outcome compatible, retourne `409 STATE_CONFLICT` si la règle de workflow l’interdit.

### 9.3 Clients et Customer 360

| Méthode | Route | Autorisation | Paramètres principaux |
|---|---|---|---|
| `GET` | `/api/v1/customers` | `customers:read` | `q`, `companyName`, `customerId`, `industry`, `sector`, `segment`, `relationshipManagerId`, pagination |
| `GET` | `/api/v1/customers/{customerId}` | `customers:read` | Fiche entreprise et affectation |
| `GET` | `/api/v1/customers/{customerId}/accounts` | `accounts:read` | Comptes du client |
| `GET` | `/api/v1/customers/{customerId}/products` | `products:read` | Produits détenus |
| `GET` | `/api/v1/customers/{customerId}/transactions` | `transactions:read` | Tous les filtres transactionnels |
| `GET` | `/api/v1/customers/{customerId}/metrics` | `analytics:read` | `metric`, `period`, dates |
| `GET` | `/api/v1/customers/{customerId}/signals` | `signals:read` | Type, sévérité, dates |
| `GET` | `/api/v1/customers/{customerId}/opportunities` | `opportunities:read` | Statut, type, confiance, priorité |
| `GET` | `/api/v1/customers/{customerId}/actions` | `actions:read` | Historique des actions et outcomes |

Le Customer 360 peut être composé par le Gateway ou un endpoint d’agrégation interne. Chaque service conserve néanmoins son contrat de domaine séparé. Une réponse d’agrégation partielle indique explicitement `partial: true` et les sections indisponibles; elle ne fabrique pas de valeurs par défaut.

### 9.3 bis Séries d’activité et registre ML (ajouts UI premium)

| Méthode | Route | Autorisation | Notes |
|---|---|---|---|
| `GET` | `/api/v1/customers/{customerId}/activity` | `transactions:read` | Série agrégée par `granularity` (`DAY`, `WEEK`, `MONTH`), `fromDate`, `toDate` : `inflow`, `outflow`, `net`, `transactionCount`, `supplierPayments`, `internationalAmount`, `internationalCount` par période. Sommes SQL sur les transactions importées, aucune valeur synthétisée. |
| `GET` | `/api/v1/ml/models` | lecture | Registre complet des modèles de propension (statut, features, coefficients, métriques, dataset). |
| `GET` | `/api/v1/ml/models/active` | lecture | Modèle actif. |
| `GET` | `/api/v1/ml/models/{modelVersion}` | lecture | Une version. |

Le dashboard agence (`/api/v1/dashboards/branch`) expose en plus `opportunitiesByType`, `opportunitiesBySector`, `opportunitiesByProduct`, `opportunitiesByPriority`, `opportunitiesByRelationshipManager`, `opportunityTimeline`, `actionsByType`, `outcomes`, `actionTimeline`. Les lignes de portefeuille (`/api/v1/dashboards/me`) portent `branchName`, `segment` et, pour chaque opportunité ouverte, `why`, `recommendedProducts`, `priorityScore`, `priorityLevel`, `generatedAt`.

**Persona de développement.** Lorsque `BOA_AUTH_DISABLED=true`, le header `X-Dev-Principal` (JSON : `subject`, `username`, `roles`, `branchIds`, `relationshipManagerIds`) remplace le jeton pour rejouer un périmètre. Il est propagé par le Gateway aux services et ignoré dès que l’authentification OIDC est active.

### 9.4 Comptes et soldes

| Méthode | Route | Autorisation | Paramètres |
|---|---|---|---|
| `GET` | `/api/v1/accounts` | `accounts:read` | `customerId`, `status`, `currency`, `accountType`, pagination |
| `GET` | `/api/v1/accounts/{accountId}` | `accounts:read` | Détail du compte |
| `GET` | `/api/v1/accounts/{accountId}/balances` | `accounts:read` | `fromDate`, `toDate`, `period`, pagination si série longue |

### 9.5 Transactions

| Méthode | Route | Autorisation | Filtres |
|---|---|---|---|
| `GET` | `/api/v1/transactions` | `transactions:read` | `customerId`, `accountId`, `fromDate`, `toDate`, `type`, `direction`, `currency`, `category`, `international`, `minAmount`, `maxAmount`, pagination |
| `GET` | `/api/v1/transactions/{transactionId}` | `transactions:read` | Détail et référence source |
| `GET` | `/api/v1/customers/{customerId}/transactions` | `transactions:read` | Même contrat, customerId imposé par chemin |
| `GET` | `/api/v1/accounts/{accountId}/transactions` | `transactions:read` | Même contrat, accountId imposé par chemin |

### 9.6 Signaux et métriques

| Méthode | Route | Autorisation | Notes |
|---|---|---|---|
| `GET` | `/api/v1/signals` | `signals:read` | Type, sévérité, client, dates, pagination |
| `GET` | `/api/v1/signals/{signalId}` | `signals:read` | Signal et preuves |
| `GET` | `/api/v1/analytics/metrics` | `analytics:read` | Métriques par client et période |
| `GET` | `/api/v1/customers/{customerId}/metrics` | `analytics:read` | Vue Customer 360 |

### 9.7 Catalogue produit et administration

| Méthode | Route | Autorisation | Notes |
|---|---|---|---|
| `GET` | `/api/v1/products` | `products:read` | Produits actifs par défaut; `active` filtrable pour admin |
| `GET` | `/api/v1/products/{productId}` | `products:read` | Détail et règles d’éligibilité publiables |
| `GET` | `/api/v1/admin/rules` | `rules:read` | `ADMIN` ou scope analytique dédié |
| `PATCH` | `/api/v1/admin/rules/{ruleId}` | `rules:write` | Admin uniquement; versionne la configuration |
| `GET` | `/api/v1/admin/engine` | `rules:read` | Versions moteur, règles et configuration active |
| `POST` | `/api/v1/admin/recompute` | `rules:write` | Lance un recalcul contrôlé; retourne `202` et `jobId` |

La modification d’une règle n’écrase pas la configuration historisée. Elle crée une nouvelle `ruleVersion`, avec auteur, date, justification et date d’effet. Toute opportunité conserve la version ayant produit sa décision.

## 10. Contrats internes par microservice

Les routes internes sont accessibles uniquement entre services autorisés. Elles utilisent des tokens de service, mTLS, `X-Correlation-ID`, timeout explicite et retries bornés. Un service ne lit jamais directement la base d’un autre service.

### 10.1 Customer Service

**OpenAPI 3.0 — résumé de service**

```yaml
openapi: 3.0.3
info:
  title: Customer Service API
  version: 1.0.0
servers:
  - url: http://customer-service/internal/v1
security:
  - serviceOAuth2: [customers:read]
paths:
  /customers:
    get:
      operationId: listCustomers
      parameters: [PageSize, Cursor, CustomerSearch, RelationshipManagerFilter]
      responses:
        '200': { description: CustomerPage, content: { application/json: { schema: { $ref: '#/components/schemas/CustomerPage' } } } }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/Forbidden' }
  /customers/{customerId}:
    get:
      operationId: getCustomer
      parameters: [CustomerId]
      responses:
        '200': { description: Customer, content: { application/json: { schema: { $ref: '#/components/schemas/Customer' } } } }
        '404': { $ref: '#/components/responses/NotFound' }
  /customers/{customerId}/profile:
    get:
      operationId: getCustomerProfile
      parameters: [CustomerId]
      responses:
        '200': { description: Profile, content: { application/json: { schema: { $ref: '#/components/schemas/Customer' } } } }
components:
  securitySchemes:
    serviceOAuth2:
      type: oauth2
      flows: { clientCredentials: { tokenUrl: https://identity.example/realms/boa/protocol/openid-connect/token, scopes: { customers:read: Read customers } } }
```

Routes internes : `GET /customers`, `GET /customers/{customerId}`, `GET /customers/{customerId}/profile`, `GET /customers/{customerId}/relationship`, `GET /customers/{customerId}/product-ownership`. Le dernier endpoint peut être alimenté par `product-service` via composition; le Customer Service ne duplique pas le catalogue maître.

### 10.2 Account Service

```yaml
openapi: 3.0.3
info: { title: Account Service API, version: 1.0.0 }
servers: [{ url: http://account-service/internal/v1 }]
paths:
  /accounts:
    get:
      operationId: listAccounts
      parameters: [PageSize, Cursor, CustomerId, AccountStatus, Currency]
      responses:
        '200': { $ref: '#/components/responses/AccountPage' }
  /accounts/{accountId}:
    get:
      operationId: getAccount
      parameters: [AccountId]
      responses:
        '200': { $ref: '#/components/responses/Account' }
        '404': { $ref: '#/components/responses/NotFound' }
  /accounts/{accountId}/balances:
    get:
      operationId: listBalances
      parameters: [AccountId, FromDate, ToDate, PageSize, Cursor]
      responses:
        '200': { $ref: '#/components/responses/BalancePage' }
components:
  schemas:
    Account: { type: object, required: [accountId, customerId, accountType, currency, status], properties: { accountId: { type: string }, customerId: { type: string }, accountType: { type: string, enum: [CURRENT_ACCOUNT, SAVINGS, CREDIT_LINE] }, currency: { type: string, pattern: '^[A-Z]{3}$' }, status: { type: string, enum: [ACTIVE, BLOCKED, CLOSED] } } }
```

Le service fournit les soldes historisés nécessaires aux comparaisons. Il ne calcule pas les signaux.

### 10.3 Transaction Service

```yaml
openapi: 3.0.3
info: { title: Transaction Service API, version: 1.0.0 }
servers: [{ url: http://transaction-service/internal/v1 }]
paths:
  /transactions:
    get:
      operationId: searchTransactions
      parameters: [PageSize, Cursor, CustomerId, AccountId, FromDate, ToDate, TransactionType, Direction, Currency, Category, International, MinAmount, MaxAmount]
      responses:
        '200': { $ref: '#/components/responses/TransactionPage' }
  /imports/transactions:
    post:
      operationId: importTransactions
      security: [{ serviceOAuth2: [integration:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/ImportBatch' } } } }
      responses:
        '202': { description: Import exécuté avec manifeste, compteurs et qualité }
        '422': { description: Contrat ou version invalide }
        '409': { $ref: '#/components/responses/Conflict' }
  /imports/transactions/{jobId}:
    get:
      operationId: getTransactionImport
      security: [{ serviceOAuth2: [integration:write] }]
      responses:
        '200': { description: Manifeste, qualité, complétude et fraîcheur du lot }
  /imports/transactions/{jobId}/rejections:
    get:
      operationId: getTransactionImportRejections
      security: [{ serviceOAuth2: [integration:write] }]
      responses:
        '200': { description: Rejets/quarantaines minimisés et sans payload brut }
  /transaction-categories:
    get: { operationId: listTransactionCategories }
    post: { operationId: createTransactionCategory }
components:
  schemas:
    ImportBatch: { type: object, additionalProperties: false, required: [contractVersion, sourceSystem, externalBatchId, transactions], properties: { contractVersion: { type: string, enum: ['1.0'] }, sourceSystem: { type: string }, externalBatchId: { type: string }, sourceWatermark: { type: string, nullable: true }, producedAt: { type: string, format: date-time, nullable: true }, expectedRowCount: { type: integer, minimum: 0, nullable: true }, transactions: { type: array, maxItems: 25000, items: { $ref: '#/components/schemas/Transaction' } } } }
```

`GET /transactions` est strictement en lecture pour les consommateurs métier. L'import
est réservé à `banking-integration-service` et à une tâche d'administration autorisée.
Le contrat `1.0` refuse les champs inconnus, impose les dates-heures zonées et conserve
un hash canonique SHA-256. Une catégorie absente ou inactive du catalogue versionné
place uniquement la ligne concernée en quarantaine; elle n'est jamais visible dans
`transaction.transactions`. Les compteurs `received`, `accepted`, `duplicate`,
`rejected` et `quarantined` sont persistés dans le même manifeste. La fraîcheur reste
`UNKNOWN` sans timestamp source; avec un timestamp, le délai est mesuré mais aucun seuil
n'est déduit sans validation BOA.

Cette gouvernance est **IMPLÉMENTÉE et PROUVÉE pour le domaine Transaction**. Son
extension aux imports Customer, Account et Product est **NON IMPLÉMENTÉE** dans ce lot.

### 10.4 Banking Integration Service

Ce service est l’anti-corruption layer. Les interfaces internes sont stables même lorsque les adapters Mock sont remplacés par des APIs BOA réelles.

```yaml
openapi: 3.0.3
info: { title: Banking Integration Service API, version: 1.0.0 }
servers: [{ url: http://banking-integration-service/internal/v1 }]
paths:
  /imports/transactions:
    post:
      operationId: importTransactionsFromCore
      security: [{ serviceOAuth2: [integration:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/ImportRequest' } } } }
      responses:
        '202': { description: Job accepté, content: { application/json: { schema: { $ref: '#/components/schemas/JobAccepted' } } } }
  /customers/{customerId}/external-profile:
    get:
      operationId: getExternalCustomerProfile
      security: [{ serviceOAuth2: [customers:read] }]
      responses:
        '200': { description: Profil normalisé }
  /customers/{customerId}/international-flows:
    get:
      operationId: getInternationalFlows
      security: [{ serviceOAuth2: [transactions:read] }]
      responses:
        '200': { description: Flux normalisés }
  /customers/{customerId}/trade-finance-ownership:
    get:
      operationId: getTradeFinanceOwnership
      security: [{ serviceOAuth2: [products:read] }]
      responses:
        '200': { description: Produits Trade Finance normalisés }
components:
  schemas:
    ImportRequest: { type: object, additionalProperties: false, required: [fromDate, toDate], properties: { contractVersion: { type: string, enum: ['1.0'], default: '1.0' }, fromDate: { type: string, format: date }, toDate: { type: string, format: date }, customerIds: { type: array, items: { type: string } }, sourceWatermark: { type: string, nullable: true }, producedAt: { type: string, format: date-time, nullable: true } } }
    JobAccepted: { type: object, required: [jobId, status, counts], properties: { jobId: { type: string }, status: { type: string, enum: [COMPLETED, PARTIAL, RETRYABLE_FAILED] }, counts: { type: object }, quality: { type: object }, freshness: { type: object } } }
```

Le service réserve et committe le manifeste avant le fan-out. Une panne avant tout
appel aval donne `RETRYABLE_FAILED`; une panne après un ou plusieurs succès donne
`PARTIAL` et `reconciliationRequired: true`. Un succès partiel n'est jamais publié
comme `COMPLETED`. Chaque réponse aval doit confirmer `status: COMPLETED`, un `jobId`
et un compteur `imported` valide; le domaine Transaction doit en plus fournir un compteur
`accepted` identique. Ce mécanisme est une orchestration rejouable, **pas** une transaction
distribuée ni une garantie exactly-once interservices.

Les composants d’implémentation sont `CoreBankingAdapter`, `PaymentAdapter`, `TradeFinanceAdapter`, `CRMAdapter` et `ProductAdapter`. Les implémentations MVP sont `MockCoreBankingAdapter`, `MockPaymentAdapter`, `MockTradeFinanceAdapter` et `MockCRMAdapter`. Le contrat ne contient pas de branche `if mock`; le choix est injecté par configuration.

### 10.5 Analytics Service

```yaml
openapi: 3.0.3
info: { title: Transaction Analytics Service API, version: 1.0.0 }
servers: [{ url: http://analytics-service/internal/v1 }]
paths:
  /metrics:
    get:
      operationId: listMetrics
      security: [{ serviceOAuth2: [analytics:read] }]
      parameters: [CustomerId, MetricName, Period, FromDate, ToDate, PageSize, Cursor]
      responses:
        '200': { description: Financial metric page }
  /customers/{customerId}/metrics/recalculate:
    post:
      operationId: recalculateCustomerMetrics
      security: [{ serviceOAuth2: [analytics:write] }]
      parameters: [CustomerId, CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/RecomputeRequest' } } } }
      responses:
        '202': { description: Recalcul terminé avec compteurs processed/skipped }
  /analytics/recompute:
    post:
      operationId: recomputeAnalytics
      security: [{ serviceOAuth2: [analytics:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/RecomputeRequest' } } } }
      responses:
        '202': { description: Recalcul incrémental ou reprise historique terminé }
  /health/data-freshness:
    get:
      operationId: getDataFreshness
      security: [{ serviceOAuth2: [analytics:read] }]
      responses:
        '200': { description: Fraîcheur et qualité des données }
components:
  schemas:
    RecomputeRequest: { type: object, required: [customerIds, asOf], properties: { customerIds: { type: array, minItems: 1, maxItems: 1000, items: { type: string } }, asOf: { type: string, format: date }, periods: { type: array, items: { type: string, enum: [7D, 30D, 90D, 180D, 365D] } }, mode: { type: string, enum: [INCREMENTAL, HISTORICAL], default: INCREMENTAL }, checkpointScope: { type: string, enum: [CUSTOMER, BATCH], default: CUSTOMER }, checkpointKey: { type: string, maxLength: 200 } } }
```

Les indicateurs couvrent `MONTHLY_INFLOW`, `MONTHLY_OUTFLOW`, `AVERAGE_BALANCE`, `MINIMUM_BALANCE`, `MAXIMUM_BALANCE`, `TRANSACTION_COUNT`, `SUPPLIER_PAYMENT_GROWTH`, `INTERNATIONAL_FLOW_GROWTH`, `CASH_BALANCE_GROWTH` et `CREDIT_LINE_UTILIZATION`, sur `7D`, `30D`, `90D`, `180D` et `365D`. La comparaison utilise la période précédente et une baseline historique lorsque suffisamment de données existent.

Le mode `INCREMENTAL` réutilise un checkpoint persistant, par client ou par lot, et ignore les entrées dont le hash de contenu n'a pas changé. La réponse expose `processed`, `skipped` et `lastEvaluatedAt`. Le mode `HISTORICAL` reste explicite pour les reprises et force le recalcul sans consulter ni modifier le checkpoint incrémental.

### 10.6 Signal Service

```yaml
openapi: 3.0.3
info: { title: Signal Detection Service API, version: 1.0.0 }
servers: [{ url: http://signal-service/internal/v1 }]
paths:
  /signals:
    get:
      operationId: listSignals
      security: [{ serviceOAuth2: [signals:read] }]
      parameters: [PageSize, Cursor, CustomerId, SignalType, Severity, FromDate, ToDate]
      responses:
        '200': { description: Signal page }
  /signals/{signalId}:
    get:
      operationId: getSignal
      security: [{ serviceOAuth2: [signals:read] }]
      responses:
        '200': { description: Signal détaillé }
        '404': { $ref: '#/components/responses/NotFound' }
  /detections:
    post:
      operationId: detectSignals
      security: [{ serviceOAuth2: [signals:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/DetectionRequest' } } } }
      responses:
        '202': { description: Détection acceptée }
components:
  schemas:
    DetectionRequest: { type: object, required: [customerIds, periods], properties: { customerIds: { type: array, items: { type: string } }, periods: { type: array, items: { type: string, enum: [7D, 30D, 90D, 180D, 365D] } }, ruleVersion: { type: string } } }
```

La détection doit comparer la tendance à l’historique et éviter de transformer une transaction isolée, une saisonnalité connue ou une activité de décembre en signal persistant sans preuve suffisante.

### 10.7 Opportunity Service

```yaml
openapi: 3.0.3
info: { title: Opportunity Service API, version: 1.0.0 }
servers: [{ url: http://opportunity-service/internal/v1 }]
paths:
  /opportunities:
    get:
      operationId: listOpportunities
      security: [{ serviceOAuth2: [opportunities:read] }]
      parameters: [PageSize, Cursor, CustomerId, OpportunityType, Status, MinConfidence, PriorityLevel, FromDate, ToDate]
      responses:
        '200': { description: Opportunity page }
  /opportunities/{opportunityId}:
    get:
      operationId: getOpportunity
      security: [{ serviceOAuth2: [opportunities:read] }]
      responses:
        '200': { description: Opportunity }
  /opportunities/{opportunityId}/explanation:
    get:
      operationId: getExplanation
      security: [{ serviceOAuth2: [opportunities:read] }]
      responses:
        '200': { description: Explanation }
  /opportunities/generate:
    post:
      operationId: generateOpportunities
      security: [{ serviceOAuth2: [opportunities:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/GenerationRequest' } } } }
      responses:
        '202': { description: Génération acceptée }
components:
  schemas:
    GenerationRequest: { type: object, required: [customerIds], properties: { customerIds: { type: array, items: { type: string } }, asOf: { type: string, format: date-time }, engineVersion: { type: string }, ruleVersion: { type: string } } }
```

Les stratégies implémentées sont `RuleBasedOpportunityStrategy` et `StatisticalOpportunityStrategy`. L’interface prépare une future `MLOpportunityStrategy`, sans appel GenAI dans la décision du MVP.

Règles contractuelles des quatre opportunités :

| Type | Conditions minimales | Horizon |
|---|---|---|
| `INVESTMENT_FINANCING` | Croissance encaissements `> 25 %`, paiements fournisseurs `> 20 %`, volume transactions `> 15 %`, aucun financement d’investissement récent | `1-3_MONTHS` |
| `TRADE_FINANCE` | Flux internationaux `> 30 %`, fréquence croissante, produit Trade Finance absent ou sous-utilisé | `0-3_MONTHS` |
| `CASH_INVESTMENT` | Solde moyen élevé de façon persistante, excédent récurrent, faible utilisation crédit | `0-1_MONTH` |
| `FINANCIAL_STRESS_SIGNAL` | Baisse encaissements `> 25 %` et/ou baisse solde `> 20 %`, avec utilisation crédit croissante | `0-1_MONTH` |

Le dernier type ne peut jamais être sérialisé comme `CREDIT_SCORE`, `RISK_SCORE`, `DEFAULT_PROBABILITY` ou `CREDIT_DECISION`.

### 10.8 Product Service

```yaml
openapi: 3.0.3
info: { title: Product Service API, version: 1.0.0 }
servers: [{ url: http://product-service/internal/v1 }]
paths:
  /products:
    get:
      operationId: listProducts
      security: [{ serviceOAuth2: [products:read] }]
      parameters: [PageSize, Cursor, Category, TargetSegment, Currency, Active]
      responses:
        '200': { description: Product page }
  /products/{productId}:
    get:
      operationId: getProduct
      security: [{ serviceOAuth2: [products:read] }]
      responses:
        '200': { description: Product }
  /customers/{customerId}/product-gaps:
    get:
      operationId: getProductGaps
      security: [{ serviceOAuth2: [products:read] }]
      responses:
        '200': { description: Gaps de catalogue normalisés }
```

Un produit contient `productId`, `name`, `category`, `eligibilityRules`, `targetSegment`, `currency` et `active`. L’Opportunity Service ne fabrique pas les noms de produits; il référence les `productId` retournés par ce service.

### 10.9 Action Service

```yaml
openapi: 3.0.3
info: { title: Action Service API, version: 1.0.0 }
servers: [{ url: http://action-service/internal/v1 }]
paths:
  /actions:
    get:
      operationId: listActions
      security: [{ serviceOAuth2: [actions:read] }]
      parameters: [PageSize, Cursor, OpportunityId, CustomerId, ActionType, Outcome, AssignedTo, FromDate, ToDate]
      responses:
        '200': { description: Action page }
    post:
      operationId: createAction
      security: [{ serviceOAuth2: [actions:write] }]
      parameters: [CorrelationId, IdempotencyKey]
      requestBody: { required: true, content: { application/json: { schema: { $ref: '#/components/schemas/CreateAction' } } } }
      responses:
        '201': { description: Action créée }
        '409': { $ref: '#/components/responses/Conflict' }
  /actions/{actionId}:
    patch:
      operationId: updateAction
      security: [{ serviceOAuth2: [actions:write] }]
      parameters: [ActionId, IfMatch]
      responses:
        '200': { description: Action mise à jour }
        '412': { $ref: '#/components/responses/PreconditionFailed' }
components:
  schemas:
    CreateAction: { type: object, required: [opportunityId, customerId, actionType], properties: { opportunityId: { type: string }, customerId: { type: string }, actionType: { type: string, enum: [ACCEPT_OPPORTUNITY, DISMISS_OPPORTUNITY, CONTACT_CUSTOMER, CREATE_FOLLOW_UP, SCHEDULE_MEETING, MARK_CONVERTED] }, dueAt: { type: string, format: date-time }, note: { type: string, maxLength: 4000 } } }
```

Les actions alimentent la boucle de feedback `recommendation → action RM → réponse client → outcome commercial`. Les actions ne modifient pas rétroactivement la décision générée par le moteur.

## 11. OpenAPI commun et publication par service

Chaque service publie son propre document `GET /openapi.json` et sa propre UI `GET /swagger` sur son réseau interne. Le Gateway publie un document agrégé pour les consommateurs externes. Les documents doivent déclarer :

- `info.title`, `info.version`, `servers`, contacts et description du périmètre ;
- schémas de sécurité OAuth2/OIDC et scopes ;
- paramètres communs de pagination, corrélation, dates et filtres ;
- request body, response body, exemples et tous les statuts d’erreur pertinents ;
- tags par bounded context et `operationId` stable ;
- headers `X-Correlation-ID`, `traceparent`, `Idempotency-Key` et `ETag` lorsque pertinents ;
- liens ou descriptions vers les événements publiés et les dépendances.

Les réponses OpenAPI peuvent factoriser les schémas dans un composant partagé, mais chaque service reste responsable de son contrat et de sa compatibilité. La génération de code client doit utiliser le document du Gateway pour le frontend et le document du service cible pour les clients internes.

Schéma de sécurité commun :

```yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example/realms/boa/.well-known/openid-configuration
    serviceOAuth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example/realms/boa/protocol/openid-connect/token
          scopes:
            customers:read: Lire les clients
            transactions:read: Lire les transactions
            analytics:read: Lire les métriques
            signals:read: Lire les signaux
            opportunities:read: Lire les opportunités
            opportunities:write: Générer ou mettre à jour les opportunités
            actions:write: Créer ou mettre à jour les actions
            integration:write: Déclencher un import contrôlé
```

## 12. Dépendances et flux service-à-service

### 12.1 Dépendances synchrones

| Appelant | Cible | Contrat | Usage | Échec attendu |
|---|---|---|---|---|
| Gateway | Tous services publics | routes `/api/v1` | Routage, auth, périmètre | `502/503/504` normalisés |
| Opportunity Service | Customer Service | `GET /internal/v1/customers/{id}` | Profil et segmentation | Pas de génération sans profil cohérent |
| Opportunity Service | Analytics Service | `GET /internal/v1/metrics` | Métriques calculées | Opportunité non générée si métriques stales/incomplètes |
| Opportunity Service | Signal Service | `GET /internal/v1/signals` | Signaux actifs et preuves | Pas de décision sans signaux nécessaires |
| Opportunity Service | Product Service | `GET /internal/v1/customers/{id}/product-gaps`, `/products` | Gaps et recommandations | Recommandation sans produit interdite |
| Signal Service | Analytics Service | `GET /internal/v1/metrics` | Détection des événements | Détection différée en cas d’indisponibilité |
| Analytics Service | Transaction Service | `GET /internal/v1/transactions` | Agrégation des mouvements | `DEPENDENCY_UNAVAILABLE` ou job en retry |
| Analytics Service | Account Service | `GET /internal/v1/accounts/{id}/balances` | Solde et utilisation | Métrique marquée incomplète |
| Banking Integration | Transaction Service | `POST /internal/v1/imports/transactions` | Import normalisé gouverné | Manifeste `RETRYABLE_FAILED` ou `PARTIAL`; jamais de faux `COMPLETED` |
| Banking Integration | Mock/BOA adapters | interfaces adapter | Données Core, paiements, Trade, CRM | Timeout et circuit breaker |
| Action Service | Opportunity Service | `GET /internal/v1/opportunities/{id}` | Validation de l’existence et état | `404` ou `409` |
| Action Service | Customer Service | `GET /internal/v1/customers/{id}` | Validation du périmètre client | `404` hors périmètre |
| Tous services | Audit | événement/audit interne | Traçabilité | Audit asynchrone avec file de reprise |

### 12.2 Flux de calcul MVP

Le flux nominal est :

```text
Banking Integration
  → Transaction Service
  → Analytics Service
  → Signal Service
  → Opportunity Service
  → API Gateway
  → RM
  → Action Service
  → Outcome / Audit
```

Les appels de lecture entre services peuvent être synchrones pour le MVP. Les imports, recalculs et générations de masse retournent `202` et un `jobId`; leur progression est exposée par un endpoint interne de job ou par événements. Les réponses métier ne doivent jamais bloquer indéfiniment sur une dépendance bancaire.

### 12.3 Contrat de fraîcheur

Les réponses analytiques indiquent `asOf`, `calculationVersion` et une information de fraîcheur. Une opportunité porte `generatedAt` et les versions du moteur/règle. Un service consommateur doit refuser ou marquer comme stale une donnée dont la fraîcheur dépasse le seuil configuré; ce seuil est une configuration de service, non une décision frontend.

## 13. Versioning et compatibilité

La version majeure de l’API publique est dans le chemin : `/api/v1`. Une évolution compatible ajoute des champs optionnels, de nouveaux enum documentés comme extensibles et de nouvelles routes. Elle ne renomme ni ne supprime un champ existant.

Une rupture de contrat crée `/api/v2`, un document OpenAPI distinct et une période de coexistence. Le Gateway peut publier un header `Deprecation` et `Sunset` au minimum 90 jours avant retrait d’une version publique, sauf exigence de sécurité. Les URLs internes suivent la même règle, même si leur durée de vie peut être plus courte.

Les versions suivantes sont indépendantes et obligatoires pour la traçabilité :

- `apiVersion` : version de chemin et contrat HTTP ;
- `engineVersion` : implémentation du moteur de génération ;
- `ruleVersion` : configuration des seuils et règles ;
- `calculationVersion` : version du calcul analytique ;
- `eventVersion` : schéma d’événement.

Une migration ne doit pas recalculer silencieusement les anciennes opportunités avec de nouvelles règles. Elle crée une nouvelle décision ou conserve l’historique et explique la différence.

## 14. Audit, confidentialité et observabilité

Chaque génération d’opportunité doit enregistrer : `opportunityId`, `engineVersion`, `ruleVersion`, timestamp, références d’inputs, signaux, métriques, confiance, priorité et résultat. Chaque action doit enregistrer `createdBy`, `createdAt`, `updatedBy`, `updatedAt`, ancienne valeur, nouvelle valeur et `correlationId` lorsque requis par la politique d’audit.

Les endpoints `/health`, `/ready` et `/metrics` distinguent la liveness de la readiness. `/ready` vérifie PostgreSQL et les dépendances indispensables, mais ne doit pas exposer de secret ni de détail de connexion. Les logs sont structurés et préparés pour OpenTelemetry. Les métriques recommandées incluent latence par route, taux d’erreur, appels dépendants, jobs en échec, fraîcheur des données et volume d’opportunités par type.

Le MVP utilise uniquement des données synthétiques. Les réponses ne doivent pas exposer de secrets, tokens, identifiants de connexion ni stack traces. La conception doit permettre que les données et les adapters restent dans l’infrastructure privée BOA; aucun appel LLM externe n’est autorisé avec des données client.

## 15. Critères d’acceptation du contrat

Le contrat est considéré respecté lorsque :

1. le Gateway expose le document OpenAPI agrégé et route les endpoints publics vers les services propriétaires ;
2. chaque service expose un document OpenAPI 3.0 versionné avec requêtes, réponses, exemples, erreurs et sécurité ;
3. une requête de liste ne peut pas charger sans limite les 500 PME ou des centaines de milliers de transactions ;
4. chaque requête authentifiée possède un `X-Correlation-ID` propagé dans les appels et logs ;
5. un RM ne peut ni lire hors portefeuille ni modifier les règles ;
6. l’explication d’une opportunité permet de remonter des produits recommandés aux signaux, métriques, seuils et versions ;
7. le type `FINANCIAL_STRESS_SIGNAL` n’est jamais présenté comme une décision ou un score de crédit ;
8. une action répétée avec la même `Idempotency-Key` ne crée pas de doublon ;
9. une erreur frontend ne contient aucune stack trace ;
10. les imports, recalculs et générations de masse sont corrélés, auditables et conçus pour évoluer vers un transport événementiel.

## Références

[1]: file:///home/ubuntu/upload/Pasted_content_100.txt "Requirements — BOA SME Opportunity Intelligence MVP"

## Décisions structurantes

- **Un seul point d’entrée public :** le frontend passe exclusivement par l’API Gateway; les bases et APIs internes ne sont jamais exposées.
- **Deux espaces de routes :** `/api/v1` pour les consommateurs publics et `/internal/v1` pour les appels de service à service, avec des mécanismes d’authentification distincts.
- **Pagination par curseur opaque :** elle évite les chargements massifs et reste stable pendant les évolutions des données.
- **RBAC et filtrage par périmètre :** les quatre rôles du requirements sont mappés à des scopes et à un portefeuille organisationnel; le rôle seul ne suffit pas.
- **Contrat d’erreur unique :** toutes les erreurs exposent un code métier stable et un `correlationId`, sans stack trace.
- **Décisions moteur versionnées :** `engineVersion`, `ruleVersion` et `calculationVersion` sont conservées avec chaque opportunité pour garantir l’audit et la reproductibilité.
- **Idempotence obligatoire pour les écritures sensibles :** les actions, imports et recalculs utilisent `Idempotency-Key` afin d’éviter les doublons lors des retries.
- **Anti-corruption layer bancaire :** `banking-integration-service` normalise les systèmes Core Banking, paiements, Trade Finance et CRM; les mocks sont interchangeables par injection de dépendances.
- **Séparation lecture/calcul/action :** transactions, analytics, signaux, opportunités, produits et actions possèdent des contrats et responsabilités distincts.
- **Événementiel préparé sans imposer un broker :** les événements métier portent un enveloppe versionnée et idempotente, même si le MVP peut démarrer avec un mécanisme simple.
- **Confidentialité par conception :** données synthétiques uniquement, aucun secret dans l’API, et aucune décision GenAI dans le moteur déterministe.
- **Compatibilité pilotée par OpenAPI :** chaque service publie son document; les changements incompatibles passent en `v2` avec coexistence et dépréciation explicite.

## Limitations explicites du MVP

Le document définit les contrats, mais ne fournit pas l’implémentation des microservices, les migrations PostgreSQL, les configurations Keycloak, les valeurs réelles de rate limiting ou le schéma complet de tous les composants OpenAPI. Ces éléments doivent être générés et testés dans les dépôts de services sans modifier les invariants contractuels ci-dessus. Les adaptateurs bancaires restent simulés dans le MVP et doivent être remplacés derrière les mêmes interfaces lors de l’intégration BOA.

## Next steps de mise en œuvre

Avant le développement, figer les schémas dans un registre de contrats, générer les interfaces clients/serveurs à partir d’OpenAPI, convenir des scopes dans Keycloak, définir les quotas par rôle, publier les exemples dans un environnement de contrat et automatiser des tests de compatibilité consumer/provider. Les tests d’intégration doivent couvrir le chemin `login → dashboard → opportunité → explication → action → contacted → converted`, ainsi que les cas de faux positifs et les scénarios hors périmètre RBAC.

---

*Document rédigé pour le MVP BOA SME Opportunity Intelligence. Toute évolution de contrat doit être soumise à revue d’architecture, de sécurité et de données.*

## Conventions canoniques finales

Les listes utilisent `data`, `meta.pageSize`, `meta.nextCursor`, `meta.hasMore`, `meta.totalCount` facultatif et `correlationId`. `confidence` est dans `0..1`, `priorityScore` dans `0..100`, et `priorityLevel` vaut `P1` à `P4`. Les actions sont `ACCEPT_OPPORTUNITY`, `DISMISS_OPPORTUNITY`, `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP`, `SCHEDULE_MEETING` et `MARK_CONVERTED`.

Le MVP utilise HTTP et outbox locale. Un broker est une évolution future, pas une dépendance. `opportunityStatus` appartient à Opportunity Service et `engagementStatus` à Action Service.


---

## 16. Contrats cibles — dashboards, features et propension

Ces routes sont des extensions futures. Elles conservent `/api/v1`, FastAPI/OpenAPI, Keycloak, curseurs opaques et erreurs normalisées. Elles ne sont pas requises par le MVP actuel avant acceptation ML.

### 16.1 Dashboards et portefeuilles

| Méthode | Route | Scope | Périmètre imposé |
|---|---|---|---|
| `GET` | `/api/v1/dashboards/me` | `dashboard:cc:read` | CC du sujet courant |
| `GET` | `/api/v1/branches/{branchId}/dashboard` | `dashboard:branch:read` | branche autorisée |
| `GET` | `/api/v1/branches/{branchId}/relationship-managers` | `dashboard:branch:read` | CC de la branche |
| `GET` | `/api/v1/relationship-managers/{id}/dashboard` | dashboard CC/agence | soi-même ou CC de la branche |
| `GET` | `/api/v1/portfolios/{portfolioId}` | `portfolios:read` | affectation active ou branche |
| `GET` | `/api/v1/portfolios/{portfolioId}/customers` | portefeuille + client | filtre serveur obligatoire |

Le CC ne peut pas élargir son périmètre par paramètre. Le responsable d’agence est en lecture/pilotage par défaut ; agir au nom d’un CC exige `actions:write:branch`. Un admin moteur sans scope client explicite ne reçoit pas le détail PME.

### 16.2 Features, modèles et inférence

Les scopes cibles séparent lecture, écriture, approbation et promotion : `features:*`, `models:*`, `ml-monitoring:read`, `ml-inference:execute`, `fusion:*` et `training-datasets:read`. Aucun scope ML n’accorde automatiquement `customers:read`.

```text
GET  /api/v1/admin/features
GET  /api/v1/admin/feature-sets
POST /api/v1/admin/feature-sets
POST /api/v1/admin/feature-sets/{id}/approve
POST /internal/v1/feature-snapshots/build
GET  /internal/v1/feature-snapshots/{snapshotId}

GET  /api/v1/admin/models
GET  /api/v1/admin/models/{modelId}/versions/{version}
POST /api/v1/admin/models/{modelId}/versions/{version}/approve
POST /api/v1/admin/models/{modelId}/versions/{version}/promote
POST /internal/v1/ml/predict
POST /internal/v1/ml/predict-batch
```

Le build de snapshots reçoit clients, `asOf`, feature set et watermark avec `Idempotency-Key`. Une prédiction retourne au minimum `scoreId`, client, type, `targetOutcome`, horizon, `propensityScore`, interprétation, modèle/version, feature set/version, snapshot, dates, qualité, explication, version de contrat et corrélation. Le score n’existe que si la qualité est `VALID` et reste dans `[0,1]`.

Les erreurs cibles sont `FEATURE_SNAPSHOT_STALE`, `FEATURE_SET_INCOMPATIBLE`, `MODEL_NOT_APPROVED`, `MODEL_ARTIFACT_INVALID`, `PREDICTION_INVALID` et `ML_FALLBACK_APPLIED`. `creditScore`, `riskScore`, `defaultProbability`, `creditDecision` et équivalents sont interdits.

### 16.3 Fusion, explication et monitoring

```text
GET  /api/v1/admin/fusion-policies
POST /api/v1/admin/fusion-policies
POST /api/v1/admin/fusion-policies/{id}/approve
POST /api/v1/admin/fusion-policies/{id}/activate
POST /api/v1/admin/fusion-policies/{id}/rollback

GET  /api/v1/admin/ml/monitoring/models/{modelId}
GET  /api/v1/admin/ml/monitoring/models/{modelId}/drift
GET  /api/v1/admin/ml/monitoring/models/{modelId}/performance
POST /internal/v1/ml/monitoring/recompute
```

La politique contient mode, type, poids, gates, fallback, version, checksum et approbations. En `ML_SHADOW`, le bloc ML d’explication est réservé au monitoring/audit et ne change pas le classement opérationnel. En `HYBRID_RERANK`, seules les candidates règles sont réordonnées. `HYBRID_CANDIDATE` est refusé dans le MVP initial.

Le monitoring indique population, référence, fenêtre, méthode, seuils, statut `OK/WARNING/BLOCKING`, versions et maturité des outcomes. Les APIs dataset exposent des manifestes gouvernés, pas un export brut au navigateur. `SIMULATED` et `NOT_REPORTED` sont exclus par défaut.

### 16.4 LLM et limites

Aucune route, clé, URL, dépendance ou fallback LLM n’existe. Un futur port narratif est séparé et non décisionnel. Le premier incrément autorisé est batch, CPU-only et `ML_SHADOW`; rerank exige l’acceptation formelle [2] [3].

## Références de l’extension

[2]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[3]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[4]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"

## 17. Contrats implémentés — cycle de vie Opportunity

### 17.1 États et horodatages

Une opportunité utilise les états `OPEN`, `ACCEPTED`, `CONTACTED`, `CONVERTED`, `DISMISSED`, `DEFERRED` et `EXPIRED`. Les trois premiers sont actifs. Les quatre derniers sont terminaux pour l’instance concernée. La réponse `Opportunity` expose `statusUpdatedAt`, `statusReason`, `expiresAt`, `cooldownUntil` et `lastActionAt`.

Le graphe autorise `OPEN → ACCEPTED`, `OPEN → CONTACTED`, `ACCEPTED → CONTACTED`, puis `CONTACTED → CONVERTED`. Les états actifs peuvent évoluer vers `DISMISSED`, `DEFERRED` ou `EXPIRED`. Une transition hors graphe retourne `409 INVALID_OPPORTUNITY_TRANSITION`. Un timestamp sans fuseau, un cooldown antérieur à la transition ou un cooldown fourni pour un état actif retourne `422 VALIDATION_ERROR`.

### 17.2 Transition et maintenance

L’endpoint interne suivant est réservé aux rôles administratifs et aux comptes de service :

```http
POST /internal/v1/opportunities/{opportunityId}/transition
Content-Type: application/json
Idempotency-Key: action-command-defer-001

{
  "status": "DEFERRED",
  "reason": "À revoir après la campagne annuelle",
  "occurredAt": "2026-09-19T14:41:04Z",
  "cooldownUntil": "2026-10-30T09:00:00Z",
  "actorSubjectId": "rm-01"
}
```

La maintenance contrôlée appelle `POST /internal/v1/opportunities/maintenance/expire`. Elle passe en `EXPIRED` les opportunités actives dont `expiresAt` est atteint. Chaque transition enregistre l’acteur, le service autorisant, le `X-Correlation-ID`, l’état avant, l’état après et le motif dans `audit.audit_logs`. Le header `Idempotency-Key` déduplique une commande Action→Opportunity ; sa réutilisation avec un contenu différent retourne `409 IDEMPOTENCY_KEY_REUSED`.

### 17.3 Actions commerciales et projection

`POST /api/v1/opportunities/{opportunityId}/actions` accepte l’action `DEFER_OPPORTUNITY`. Elle exige un `dueAt` futur avec fuseau. Action Service persiste d’abord une commande locale `PENDING`, puis utilise son compte de service pour projeter `DEFERRED` dans Opportunity Service. Après succès, l’action devient `COMPLETED`, la commande devient `APPLIED` et l’outcome structuré `REVIEW_LATER` est persisté dans la même transaction locale. En cas d’échec distant, la commande reste `FAILED` avec son code d’erreur ; rejouer le même payload et la même clé reprend la commande sans créer une seconde action. Les réponses exposent `transitionStatus` et `transitionError`.

Les outcomes `CONTACTED`, `MEETING_SCHEDULED` et `OFFER_CREATED` projettent l’état `CONTACTED`. Les outcomes `CONVERTED`, `REJECTED` et `NOT_RELEVANT` projettent respectivement `CONVERTED` et `DISMISSED`. Créer une action planifiée `CONTACT_CUSTOMER` ou `SCHEDULE_MEETING` ne marque pas le client comme contacté ; seule la persistance de l’outcome le fait. Rejouer le même outcome sur la même action est idempotent. Remplacer un outcome déjà enregistré retourne `409 OUTCOME_CONFLICT`. Une seconde action terminale de même type retourne `409 DUPLICATE_ACTION`.

Les listes filtrées par `opportunityId` ou `customerId` et `PATCH /actions/{actionId}` valident la ressource auprès d’Opportunity Service ou Customer Service avec le jeton utilisateur. Un identifiant connu ne permet donc pas de modifier ou lire une action hors portefeuille.

### 17.4 Génération, historique et cooldown

`POST /internal/v1/opportunities/generate` exige une profondeur calendaire d’historique transactionnel d’au moins 90 jours. Le service lit `historyDays` et `observedFrom` produits par Analytics. Une lignée historique absente ou insuffisante retourne `422 INSUFFICIENT_TRANSACTION_HISTORY` ; un recalcul historique explicite est alors nécessaire.

Pour chaque candidat, le moteur classe la décision en `CREATED`, `REFRESHED` ou `SUPPRESSED`. Une opportunité active de même client et de même type est rafraîchie, sans doublon. Une opportunité terminale dont le cooldown est encore actif supprime la réémission. La décision est enregistrée sous `OPPORTUNITY_GENERATION_CREATED`, `OPPORTUNITY_GENERATION_REFRESHED` ou `OPPORTUNITY_GENERATION_SUPPRESSED`, avec l’identifiant de l’opportunité active ou terminale, la date de fin de cooldown, la règle, le moteur et le mode de fallback. PostgreSQL revendique le client avant tout appel aval, puis chaque clé `(customerId, opportunityType)`, par des advisory locks transactionnels non bloquants. Une exécution concurrente reçoit `409 GENERATION_IN_PROGRESS` au lieu d’attendre dans le worker ou de créer un doublon. Feature Store revendique aussi `(customerId, asOf, featureSetVersion)` et retourne `409 FEATURE_MATERIALIZATION_IN_PROGRESS` en cas de concurrence directe. L’expiration utilise `FOR UPDATE SKIP LOCKED` afin qu’une ligne ne soit traitée que par un worker.

### 17.5 Politique lifecycle versionnée

Chaque version Rule Studio contient :

```json
{
  "lifecycle": {
    "validityDays": 90,
    "dismissedCooldownDays": 30,
    "convertedCooldownDays": 180,
    "deferredCooldownDays": 30,
    "expiredCooldownDays": 7
  }
}
```

Ces paramètres sont visibles et modifiables dans Rule Studio. Le Rule Engine les propage avec la recommandation. Opportunity Service les conserve dans la règle technique et les applique lors de la création, de l’expiration et des transitions terminales. Les anciennes versions dépourvues de ce bloc reçoivent les valeurs par défaut à la lecture, sans réécriture de leur historique.

### 17.6 Isolation objet côté service

Les routes de liste, détail et explication d’Opportunity Service appliquent le périmètre du principal, indépendamment du Gateway et de l’interface. Un `RELATIONSHIP_MANAGER` est limité aux affectations actives dont le `relationshipManagerId` figure dans son jeton. Un `BRANCH_MANAGER` est limité aux affectations actives de ses agences. Un paramètre `relationshipManagerId` ne peut qu’affiner ce périmètre ; il ne peut jamais l’élargir. Une lecture directe hors périmètre retourne `404` afin de ne pas révéler l’existence de la ressource. Un rôle commercial sans périmètre reçoit `403 PORTFOLIO_SCOPE_MISSING`.

## Références du cycle de vie

[7]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités — cycle de vie pilote"
[8]: ./lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md "Rapport de validation du lot 2"

## 18. Contrats implémentés — synchronisation portefeuille gouvernée

### 18.1 Écriture datée et idempotente

La route publique d’administration est `POST /api/v1/admin/portfolio-assignments/sync`. Le Gateway exige le rôle `ADMIN`, transmet `Idempotency-Key` et `X-Correlation-ID`, puis appelle `POST /internal/v1/portfolio-assignments/sync`. La route interne accepte un administrateur ou le compte de service dont le `client_id` est exactement `banking-integration-service`; un autre compte `SERVICE` reçoit `403 FORBIDDEN`.

```http
POST /api/v1/admin/portfolio-assignments/sync
Authorization: Bearer <token-admin>
Idempotency-Key: portfolio-sync-20260919-001
Content-Type: application/json

{
  "contractVersion": "1.0",
  "sourceSystem": "CRM_PORTFOLIO",
  "batchRef": "batch-20260919-001",
  "sourceWatermark": "2026-09-19T16:00:00Z",
  "assignments": [
    {
      "sourceEventId": "evt-SME-00427-001",
      "customerId": "SME-00427",
      "portfolioId": "PORTFOLIO-BR-05-PILOT",
      "relationshipManagerId": "rm-25",
      "relationshipManagerName": "Chargé PME 25",
      "branchId": "BR-05",
      "assignmentType": "PRIMARY",
      "isPrimary": true,
      "validFrom": "2026-10-15T08:00:00Z",
      "validTo": null,
      "reason": "Réaffectation validée"
    }
  ]
}
```

Un succès retourne `202` avec `jobId`, `received`, `applied`, `unchanged`, `replayedEvents` et le résultat de chaque événement. La transaction contenant affectation, reçu, événement source, audit et outbox est commitée avant la réponse. Le rejeu immédiat du même lot et de la même clé retourne le même `jobId` avec `replayed=true`, sans nouvelle affectation ni nouvel audit.

La clé `(sourceSystem, sourceEventId)` déduplique les événements entre lots. La réutilisation d’une clé HTTP ou d’un lot source avec un contenu différent retourne `409 IDEMPOTENCY_KEY_REUSED`; la réutilisation d’un événement avec un autre contenu retourne `409 SOURCE_EVENT_REUSED`. Des advisory locks transactionnels non bloquants revendiquent le lot, chaque événement source et chaque client avant mutation. Une concurrence reçoit respectivement `409 PORTFOLIO_SYNC_IN_PROGRESS`, `409 SOURCE_EVENT_IN_PROGRESS` ou `409 CUSTOMER_ASSIGNMENT_IN_PROGRESS`, jamais un doublon silencieux. Un événement antérieur au dernier intervalle connu reçoit `409 OUT_OF_ORDER_ASSIGNMENT`; un intervalle déjà terminé reçoit `409 HISTORICAL_RECONCILIATION_REQUIRED`. Une date sans fuseau, une période inversée ou un type autre que `PRIMARY` reçoit `422`.

Le flux d’affectation ne modifie jamais le référentiel d’un CC existant. Si le `relationshipManagerId` existe dans une autre agence, la requête reçoit `409 RELATIONSHIP_MANAGER_BRANCH_CONFLICT`. Une réaffirmation strictement identique de la cible et des deux bornes est classée `NO_CHANGE`; toute divergence de `validFrom` ou `validTo` sur l’intervalle existant reçoit `409 ASSIGNMENT_INTERVAL_CONFLICT`.

### 18.2 Historique et date de référence

`GET /api/v1/admin/portfolio-assignments?customerId=SME-00427` retourne l’historique complet. Le paramètre optionnel `asOf` sélectionne l’intervalle qui contient cet instant selon la convention demi-ouverte `[validFrom, validTo)`. La contrainte PostgreSQL `ex_portfolio_assignments_no_overlap` interdit deux intervalles superposés pour un même client. Customer, Portfolio et Opportunity utilisent la même définition temporelle : `validFrom <= maintenant` et `validTo` absent ou strictement postérieur à maintenant.

Chaque affectation expose `portfolioId`, `relationshipManagerId`, `branchId`, `assignmentType`, `isPrimary`, `validFrom`, `validTo`, `sourceSystem`, `sourceEventId`, `sourceWatermark`, `actor` et `reason`. Le MVP pilote n’autorise que l’affectation `PRIMARY`; les délégations et affectations secondaires restent hors contrat.

### 18.3 Provenance et audit

Chaque événement accepté écrit `customer.portfolio_sync_events`, puis une entrée `audit.audit_logs` avec état avant/après, source, événement, lot, watermark, hash canonique SHA-256 et corrélation. Une modification métier produit aussi `integration.outbox_messages` avec `PORTFOLIO_ASSIGNMENT_CHANGED`. `customer.portfolio_sync_receipts` conserve la réponse rejouable du lot. Depuis la migration `0012_portfolio_sync_governance`, un trigger PostgreSQL refuse tout `UPDATE` ou `DELETE` de `audit.audit_logs`; cette garantie append-only locale ne remplace pas une politique WORM/SIEM à définir avant production.

## Références de la synchronisation portefeuille

[9]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
[10]: ./lots/LOT-03-SYNCHRONISATION-PORTEFEUILLE.md "Rapport de validation du lot 3"

## 19. Contrats implémentés — exports Excel

### 19.1 Opportunités filtrées

`GET /api/v1/exports/opportunities.xlsx` retourne un classeur au type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. La route accepte `customerId`, `type` ou `opportunityType`, `minConfidence`, `maxConfidence`, `priorityLevel`, `sector`, `customerSegment`, `relationshipManagerId`, `horizon`, `fromDate`, `toDate`, `status` et `sort`. Les paramètres de pagination `pageSize` et `cursor` sont refusés, car le fichier porte le résultat complet dans la limite du pilote.

Opportunity Service applique les mêmes prédicats SQL que la liste paginée. Il limite un chargé de clientèle à ses affectations actives et un responsable d’agence à ses agences. Un filtre `relationshipManagerId` affine ce périmètre sans l’élargir. Le classeur contient les scores de confiance et de priorité, les raisons, les produits, le cycle de vie, les versions du moteur et de la règle, la politique de scoring ainsi que le mode de fallback.

### 19.2 Portefeuille PME

`GET /api/v1/exports/portfolio.xlsx` est réservé aux rôles `RELATIONSHIP_MANAGER` et `BRANCH_MANAGER`. Sans paramètre, il exporte le portefeuille autorisé courant. Le paramètre facultatif `relationshipManagerId` permet au responsable d’agence de sélectionner un CC de son agence. Une cible hors périmètre retourne `404`.

La feuille `Portefeuille PME` expose l’identité synthétique de la PME, le secteur, le segment, le CC, l’agence, la propension POC, la priorité combinée, les opportunités ouvertes et les actions à venir. Ces colonnes servent au pilotage commercial et ne constituent aucune décision de crédit.

### 19.3 Réponse, sécurité et audit

Le Gateway utilise un proxy binaire dédié. Il n’interprète pas le classeur comme du JSON et n’accepte que le type MIME XLSX attendu. La réponse contient `Content-Disposition`, `Cache-Control: no-store`, `X-Correlation-ID` et `X-Content-SHA256`.

Les chaînes qui pourraient être interprétées comme une formule Excel sont neutralisées. Un export synchrone est limité à 10 000 lignes. Au-delà, le service retourne `413 EXPORT_LIMIT_EXCEEDED` sans produire de fichier partiel. Chaque succès est inscrit dans `audit.audit_logs` avec acteur, ressource, corrélation, nombre de lignes et empreinte SHA-256. Aucun fichier n’est conservé côté serveur.

## Référence des exports Excel

[11]: ./lots/LOT-04-EXPORTS-EXCEL.md "Rapport de validation du lot 4 — exports Excel"

## 20. Contrats implémentés — catalogue de libellés

### 20.1 Lecture runtime

`GET /api/v1/labels` est accessible aux rôles autorisés à utiliser le produit. La réponse contient la locale, un dictionnaire `code → libellé` optimisé pour l’interface et les métadonnées de chaque entrée. Le frontend charge ce dictionnaire après l’initialisation de l’authentification. Si le service est temporairement indisponible, il conserve son dictionnaire français embarqué.

Le catalogue change uniquement le texte affiché. Il ne modifie jamais les codes stables tels que `OPEN`, `P1`, `TRADE_FINANCE` ou `CONTACT_CUSTOMER`. Les règles, filtres, historiques, exports et intégrations continuent d’échanger ces codes.

### 20.2 Version administrée

`PUT /api/v1/admin/labels/{namespace}/{code}` exige le rôle `ADMIN`. La charge utile contient `label`, `active`, `expectedVersion` et une `justification` de huit caractères au minimum. La version attendue est comparée sous verrou SQL. Une version obsolète retourne `409 LABEL_VERSION_CONFLICT` au lieu d’écraser la modification d’un autre administrateur. Une modification réelle incrémente `current_version`, met à jour l’entrée courante et ajoute une ligne immuable dans `config.label_catalog_versions`. Le rejeu du même texte et du même état est sans effet lorsque sa version attendue est courante.

`GET /api/v1/admin/labels/{namespace}/{code}/versions` retourne l’historique en ordre décroissant. La migration `0013_label_catalog` installe des triggers PostgreSQL qui refusent `UPDATE`, `DELETE` et `TRUNCATE` sur l’historique. Comme le dictionnaire runtime est indexé par code, `(code, locale)` est unique en base, y compris entre namespaces. Le pilote fournit vingt libellés initiaux répartis entre types d’opportunité, actions, statuts, priorités et horizons.

### 20.3 Interface Back Office

La page `/back-office/libelles` est réservée à l’administrateur. Elle affiche les codes immuables, le texte courant, la version, l’état actif et la justification. Toute modification passe par un formulaire qui exige une justification. Le parcours E2E modifie puis restaure un libellé et vérifie les deux incréments de version.

## Référence du catalogue de libellés

[12]: ./lots/LOT-05-LIBELLES-ADMINISTRABLES.md "Rapport de validation du lot 5 — libellés administrables"


## 21. Contrats implémentés — notifications email

### 21.1 Rappels liés aux actions

Lorsqu’un CC crée une action planifiée `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP` ou `SCHEDULE_MEETING` avec une adresse email issue de son jeton OIDC vérifié, Action Service écrit `ACTION_NOTIFICATION_REQUESTED` dans `integration.outbox_messages` au sein de la transaction métier. Le worker Notification matérialise cet événement une seule fois, puis le livre via le relais SMTP configuré. Une action sans adresse vérifiée reste créée, mais ne produit pas d’email.

Le corps du rappel contient le type d’action, l’échéance et la référence de l’opportunité. Il n’embarque ni donnée transactionnelle détaillée, ni score financier, ni recommandation de crédit. Le texte rappelle que l’opportunité est une aide commerciale et ne constitue aucune décision de crédit.

### 21.2 Synthèse quotidienne par CC

`PUT /api/v1/admin/notifications/digest-subscriptions/{relationshipManagerId}` exige `ADMIN` et configure `recipientEmail`, un fuseau IANA, une heure locale de livraison entre 0 et 23, et l’état actif. `GET /api/v1/admin/notifications/digest-subscriptions` retourne le paramétrage courant. La page `/back-office/notifications` expose ces opérations sans accès direct à la base.

À chaque cycle, le worker sélectionne les abonnements dus, obtient par OAuth2 `client_credentials` les seuls KPI agrégés du portefeuille autorisé auprès de Portfolio Service, puis produit au plus une synthèse par `(CC, date locale)`. Son jeton ne porte que `NOTIFICATION_DIGEST_READER`, et chaque demande est en plus liée au CC par une signature HMAC avec un secret distinct du secret OAuth. Ce secret est obligatoire au démarrage et ne possède aucune valeur par défaut. Le rôle générique `SERVICE` ne peut pas appeler cette route. La synthèse contient le nombre de clients, les priorités P1, les opportunités ouvertes et les actions à échéance sous sept jours. Aucun nom de PME ni détail de compte n’est inclus. `POST /api/v1/admin/notifications/digests/generate?force=true` permet une exécution contrôlée et auditée par l’administrateur ; la déduplication quotidienne reste active et seuls les administrateurs peuvent appeler ce déclenchement ou le dispatch manuel.

### 21.3 Livraison et résilience

`GET /api/v1/admin/notifications` expose les statuts `PENDING`, `SENDING`, `RETRY`, `SENT`, `DELIVERY_UNCERTAIN` et `DEAD_LETTER`, le compteur de tentatives, la prochaine tentative, le Message-ID du fournisseur et une erreur expurgée. Un envoi resté `SENDING` après interruption passe à `DELIVERY_UNCERTAIN` et n’est jamais réexpédié automatiquement ; l’administrateur doit d’abord rapprocher son Message-ID stable avec le relais. `POST /api/v1/admin/notifications/dispatch` force un cycle de livraison et `POST /api/v1/admin/notifications/{notificationId}/retry` réarme explicitement une dead-letter ou une issue incertaine réconciliée.

Le connecteur est configuré par `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `SMTP_SSL` et `SMTP_FROM`. Une authentification SMTP sans `STARTTLS` ou TLS implicite est refusée sans exception. Seul Mailpit local, anonyme et isolé, utilise un transport non chiffré ; aucun email n’est envoyé à Internet. En cas d’échec certain, le worker applique un délai exponentiel borné et abandonne après cinq tentatives par défaut. Chaque tentative est ajoutée à `notification.notification_delivery_attempts`; les triggers PostgreSQL refusent `UPDATE`, `DELETE` et `TRUNCATE` de cet historique. La migration `0014_email_notifications` crée les tables, index, contraintes et champs de quarantaine d’outbox. Le rôle runtime n’est pas propriétaire du schéma, ne peut ni y créer ni supprimer de table, et ne reçoit que `SELECT`/`INSERT`/`UPDATE` selon les besoins de chaque table. Sur `integration.outbox_messages`, PostgreSQL limite en plus l’accès aux seules lignes `ACTION_NOTIFICATION_REQUESTED` et l’écriture aux quatre colonnes de consommation ; le payload, le type et l’agrégat restent non modifiables.

## Référence des notifications

[13]: ./lots/LOT-06-NOTIFICATIONS-EMAIL.md "Rapport de validation du lot 6 — notifications email"
