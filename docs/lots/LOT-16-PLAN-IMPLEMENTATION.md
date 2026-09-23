# Lot 16 — Plan séquencé d’implémentation de la Financial Intelligence API B2B

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
**Statut du document : instantané historique du plan initial, non preuve de livraison**
**Dépôt audité :** `boa-sme-financial-intelligence`
**Branche auditée :** `feat/financial-intelligence-api`
**Référence de base initialement auditée :** `9368101eb81cb79595b3317f0938bc2ac9c9b5fd`
**Données autorisées pour le lot :** synthétiques et gouvernées uniquement

> **Conclusion de cadrage historique.** À la référence de base initialement auditée, le Lot 16 n’était pas implémenté. La branche pointait alors sur le même commit que sa base et aucun module, route, migration, contrat, test ou document Financial Intelligence identifiable n’avait été livré. Le présent fichier conserve la séquence de construction initiale ; l’état réalisé et ses preuves sont décrits dans `LOT-16-FINANCIAL-INTELLIGENCE-API.md`. Ce plan ne constitue pas une déclaration de conformité, de disponibilité en production ou de décision bancaire.

## 1. Légende des statuts

Le plan emploie les statuts suivants afin de séparer les acquis vérifiables des travaux à entreprendre et des décisions externes.

| Statut | Signification dans ce plan |
|---|---|
| **IMPLEMENTÉ** | Présent dans le dépôt audité et réutilisable sans le confondre avec une livraison Lot 16. |
| **À IMPLEMENTER** | Travail de code, migration, test, documentation ou exploitation requis. |
| **HYPOTHÈSE À VALIDER AVEC BOA** | Décision métier, juridique, contractuelle, sécurité ou architecture d’entreprise qui ne peut pas être inventée par l’équipe. |
| **BLOCKED** | Ne peut pas être accepté ou démontré tant qu’un prérequis explicite n’est pas résolu. |

## 2. État existant et périmètre de départ

### 2.1 Actifs réutilisables — **IMPLEMENTÉ**

Le dépôt possède déjà une architecture FastAPI modulaire. `gateway_api.py` porte la frontière publique, les chemins `/api/v1`, la corrélation, le contrôle d’accès existant, le proxy HTTP et la normalisation des erreurs. `platform.py:create_service_app` permet d’exécuter des applications de service séparées. Les conventions `/internal/v1`, `X-Correlation-ID`, `Authorization`, `Idempotency-Key`, les timeouts et les erreurs `DEPENDENCY_TIMEOUT` et `DEPENDENCY_UNAVAILABLE` doivent être conservées.

Les domaines suivants sont déjà disponibles et doivent rester propriétaires de leurs données et règles : Customer, Account, Transaction, Analytics, Signal, Opportunity, Product, Action, Banking Integration, Rule Management, Rule Engine, Rule Simulation, Feature Store, ML Engine, Portfolio et Notification. Les modules Analytics, Signals, Feature Store, Opportunity, Portfolio et ML exposent des éléments réutilisables pour composer une vue FI, mais ils ne forment pas encore un contrat FI unifié.

Le dépôt contient également des invariants Lot 15 réutilisables. La visibilité multibancaire applique notamment `value_date <= as_of` et `status = BOOKED`, calcule la couverture de catégorisation, les fingerprints de transferts interbancaires et le ratio encaissements/CA déclaré. La migration `0020_multibank_visibility.py` apporte des snapshots, politiques, attributs de domiciliation et des éléments de registre de feature set. Ces données restent synthétiques et doivent conserver leur statut d’hypothèses tant qu’une validation BOA n’a pas eu lieu.

La gouvernance ML existante impose le mode `POC_SHADOW`, le fallback `RULES_ONLY`, `rules_weight = 1` et `ml_weight = 0` dans les chemins concernés. Cette gouvernance est un actif de garde-fou, mais elle ne prouve pas encore le contrat FI ; le Lot 16 devra ajouter ses propres tests et métadonnées explicites.

Le frontend dispose d’un shell, de guards, de composants d’état, de dashboards et d’un drill-down client. Il ne dispose pas d’une vue Financial Intelligence, d’un hook FI ni d’un contrat de données FI. Le frontend ne doit donc pas être présenté comme une implémentation existante du lot.

### 2.2 Absences critiques — **BLOCKED**

Aucun élément identifié ne matérialise le Lot 16 :

- aucune route `/api/v1/financial-intelligence` ;
- aucun service, package ou module `financial_intelligence` ;
- aucun schéma OpenAPI ou DTO versionné FI ;
- aucune table de snapshot ou de lineage FI ;
- aucune entité `Consumer`, `PortfolioCompany` ou `DataAccessGrant` ;
- aucune politique RLS dédiée à l’isolation Consumer/Fund ;
- aucun journal d’accès FI append-only ;
- aucun test contractuel, de non-fuite, de performance ou E2E FI ;
- aucune page frontend Portfolio Overview ou Company Drill-down FI ;
- aucune preuve de charge, d’observabilité ou d’artefact FI ;
- aucune validation BOA des responsabilités BIAN, des entitlements et des niveaux de service.

La suite de tests auditée n’est pas une preuve de qualité de livraison. Selon les exécutions rapportées, des configurations d’environnement/authentification provoquent des échecs et la collecte sans `PYTHONPATH=backend/src` peut résoudre un autre dépôt. Ces problèmes doivent être traités séparément du code FI.

### 2.3 Non-objectifs impératifs — **IMPLEMENTÉ À PRÉSERVER**

FI ne doit pas devenir propriétaire de l’identité client, des comptes, transactions, règles, signaux, features, opportunités, actions ou portefeuilles. FI ne doit pas recalculer ni modifier les règles de ses sources, créer une seconde entité Opportunity, déclencher une action commerciale ou prendre une décision de crédit.

FI ne doit pas exposer de transactions brutes, de contreparties, de remittance information, de secrets, de vecteurs de features non minimisés ou de données BOA réelles. Il ne doit appeler ni LLM ni GPU et ne doit pas activer un score ML. Il ne doit pas exposer `/internal/v1` au consommateur B2B.

## 3. Architecture cible sans God Service

### 3.1 Frontière et responsabilités — **À IMPLEMENTER**

La cible est une capability de lecture et de composition. Le Gateway reste l’unique frontière publique. Une application Financial Intelligence séparée reçoit un contexte de requête autorisé, compose des contrats sortants typés et renvoie un DTO anti-corruption FI. Elle ne partage pas les ORM des autres domaines et n’accède pas directement à PostgreSQL pour lire leurs tables.

| Composant | Responsabilité conservée |
|---|---|
| Gateway | Authentification, autorisation de façade, corrélation, limites de requête, routage public et erreurs normalisées. |
| Financial Intelligence | Orchestration bornée, cohérence `asOf`, projection agrégée, provenance, minimisation, état partiel explicite. |
| Customer/Account | Identité, relation et périmètre client autorisé. |
| Transaction | Faits transactionnels et statut métier ; aucune exposition brute par FI. |
| Analytics | Métriques point-in-time, fenêtres et versions de calcul. |
| Signal/Rule Engine | Détections déterministes, versions de règles et preuves. |
| Feature Store | Features versionnées, lineage, sources et checksum. |
| Opportunity | Génération, score, evidence et lifecycle des opportunités existantes. FI ne fait qu’en projeter une référence. |
| Portfolio | Affectations et vues scopeées déjà gouvernées. |
| ML Engine | Lineage et comparaison shadow ; aucune influence active dans FI. |

La façade FI appelle ces propriétaires via `service_request` ou une abstraction équivalente. Chaque appel transporte le `correlation_id`, l’identité technique autorisée, le contexte de tenant/Consumer/Fund, le `asOf`, un timeout et une version de contrat. Les retries sont bornés et ne s’appliquent qu’aux opérations idempotentes de lecture ou aux préparations explicitement idempotentes.

### 3.2 Séquence d’exécution — **À IMPLEMENTER**

1. Le Gateway valide le token OIDC, l’issuer, l’audience, la signature, les dates et les claims nécessaires.
2. La couche d’autorisation FI résout le Consumer, le Fund, le portfolio et le rôle à partir du serveur ; elle ne fait jamais confiance à un `consumerId`, `fundId` ou `customerId` soumis seul par le client.
3. FI valide le contrat de requête, l’`asOf`, la pagination, les filtres bornés et le budget de fan-out.
4. FI construit un contexte immuable contenant `traceId`, `asOf`, `calculationVersion`, `contractVersion`, `inputWatermark` attendu et les entitlements.
5. Les clients sortants interrogent les domaines propriétaires en parallèle dans une limite contrôlée. Chaque réponse est associée à sa source, sa version, son watermark et son état.
6. FI applique les règles de projection et de minimisation. Elle ne fabrique ni règle, ni score, ni opportunité.
7. Les dépendances indisponibles produisent soit une réponse partielle explicitement marquée, soit une erreur normalisée. FI ne remplace jamais une donnée manquante par une valeur inventée.
8. FI renvoie l’enveloppe versionnée, le `traceId`, l’état de fraîcheur, la provenance, la qualité et la gouvernance effective.
9. L’accès est journalisé dans un journal dédié, sans token ni payload financier complet.

### 3.3 Décisions bloquantes de conception — **BLOCKED / HYPOTHÈSE À VALIDER AVEC BOA**

Le périmètre exact de l’overview B2B, la liste des personas autorisées, les entitlements par Consumer et Fund, la convention de réponse partielle, le SLO de fraîcheur, les règles de rétention et la classification des champs doivent être validés avec BOA avant de figer l’API publique. Un mapping BIAN ne doit être présenté que comme correspondance candidate tant que l’architecture d’entreprise n’a pas validé les noms et responsabilités.

## 4. Modèle de données et persistance

### 4.1 Modèle logique minimal — **À IMPLEMENTER**

Le modèle doit séparer l’autorisation externe, les faits versionnés et l’audit d’accès.

| Objet | Contenu minimal | Contraintes principales |
|---|---|---|
| `Consumer` | organisation cliente autorisée, statut et identifiant stable | identifiant immuable, statut contrôlé, aucun accès implicite. |
| `Fund` ou frontière de tenant | identifiant de fonds/tenant et rattachement Consumer | rattachement unique, résolution serveur obligatoire. |
| `Portfolio` | portfolio scopeé par Consumer/Fund | aucune lecture cross-Consumer ou cross-Fund. |
| `PortfolioCompany` | association synthétique portfolio–company | unicité `(portfolio_id, company_id)` et compatibilité Consumer/Fund. |
| `DataAccessGrant` | action, subject/client, Consumer, Fund, purpose, dates, révocation et statut | `expires_at` obligatoire et futur à l’émission ; révocation prioritaire ; deny-by-default. |
| `FinancialIntelligenceSnapshot` | customer/portfolio, `asOf`, `contractVersion`, `calculationVersion`, watermark, provenance, checksum, qualité et projection minimale | clé idempotente versionnée ; pas de transaction brute ; append-only ou upsert strictement identique. |
| `FinancialIntelligenceLineage` | source, sourceRef, version, disponibilité, watermark et evidenceRef | chaque contribution doit être traçable sans stocker de donnée sensible inutile. |
| `AccessAuditLog` | subject, client, Consumer, Fund, ressource, scope, grant, purpose, décision, motif, corrélation, date et expiration observée | append-only, pas de secret, accès restreint aux auditeurs. |

Les noms SQL définitifs, le choix entre snapshot persistant et read model calculé à la demande, les clés de partitionnement et la politique de rétention sont **HYPOTHÈSES À VALIDER AVEC BOA**. Une table de snapshot ne doit être ajoutée que si elle apporte une cohérence, une réconciliation ou une exigence de performance démontrée ; elle ne doit pas dupliquer les masters des domaines.

### 4.2 Migration — **À IMPLEMENTER, puis BLOCKED jusqu’à revue**

Créer une migration Alembic ultérieure au head `0020`, par exemple `0021_financial_intelligence_authorization.py` ou une migration FI unique approuvée. Elle doit :

- créer les tables et clés étrangères du modèle retenu ;
- ajouter les timestamps timezone, les bornes temporelles, les statuts et les index d’expiration ;
- imposer les contraintes d’unicité Consumer/Fund/portfolio/company ;
- imposer `confidence` dans `[0,1]` lorsque ce champ est autorisé ;
- préserver `as_of`, `generated_at`, `calculation_version`, `contract_version`, `input_watermark`, `trace_id`, `source_refs` et `checksum` ;
- activer et forcer la RLS sur les tables FI si PostgreSQL est retenu pour l’isolation ;
- prévoir upgrade, downgrade, ré-exécution contrôlée et vérification d’un head unique ;
- ne jamais modifier silencieusement les contraintes métier de Lot 15.

La migration est **BLOCKED** tant que la politique RLS, les rôles SQL minimaux, le contexte de transaction et la matrice d’accès BOA ne sont pas revus. Le grant existant `SELECT` large de `portfolio_service` ne remplace pas cette politique et devra être réévalué pour la surface FI.

## 5. Contrats API versionnés

### 5.1 Surface initiale — **À IMPLEMENTER**

La surface publique minimale proposée est read-only et doit rester sous `/api/v1/financial-intelligence` :

- `GET /api/v1/financial-intelligence/portfolios/{portfolioId}/overview` ;
- `GET /api/v1/financial-intelligence/companies/{customerId}/summary?asOf=...` ;
- `GET /api/v1/financial-intelligence/companies/{customerId}/evidence/{evidenceId}` si une consultation d’evidence est nécessaire et autorisée.

L’usage de `customerId` est une clé de ressource, jamais une preuve d’autorisation. Une ressource hors périmètre doit être indistinguable d’une ressource inconnue selon la politique de non-fuite validée. Aucun endpoint write, recompute, action, export ou crédit ne doit être ajouté dans le premier lot sans décision séparée.

Chaque route doit définir dans OpenAPI son `operationId` unique, ses scopes requis, ses paramètres, sa pagination bornée, ses erreurs et ses exemples synthétiques. Aucun `/internal/v1` ne doit être publié par la façade.

### 5.2 Enveloppe commune — **À IMPLEMENTER**

Le contrat doit normaliser toutes les réponses :

```json
{
  "data": {},
  "meta": {
    "contractVersion": "fi.v1",
    "customerId": "synthetic-customer-001",
    "portfolioId": "synthetic-portfolio-001",
    "asOf": "2025-01-31",
    "generatedAt": "2025-02-01T10:00:00Z",
    "traceId": "corr-...",
    "source": ["analytics", "feature_store", "signal", "opportunity"],
    "version": "calculation-2025.01",
    "calculationVersion": "analytics-v1",
    "featureSetVersion": "features-v1",
    "ruleVersion": "rules-v1",
    "inputWatermark": "wm-...",
    "freshness": {"status": "FRESH", "observedAt": "2025-02-01T09:59:00Z"},
    "confidence": 0.0,
    "executionMode": "DETERMINISTIC_RULES",
    "mlMode": "POC_SHADOW",
    "rulesWeight": 1.0,
    "mlWeight": 0.0,
    "partial": false,
    "sourceStatus": []
  }
}
```

Les noms définitifs et les champs obligatoires sont **HYPOTHÈSE À VALIDER AVEC BOA**. `confidence` doit exprimer la qualité de couverture ou la fiabilité du calcul documenté, et non une probabilité commerciale ou une décision de crédit. Le contrat doit distinguer `0`, `null`, `UNKNOWN` et `INSUFFICIENT_HISTORY`.

### 5.3 Projections autorisées — **À IMPLEMENTER**

L’overview expose uniquement des agrégats, des compteurs non sensibles, des périodes, la qualité, la fraîcheur et des références. Le drill-down expose des faits financiers dérivés, des métriques, des signaux relationnels et des références d’opportunités existantes.

Une projection de visibilité peut contenir `level`, `estimatedShare`, `method`, `categorizationCoverage`, `fingerprintCounts` et `evidenceRefs`. Une projection de signal contient `signalRef`, `type`, `severity`, `status`, `value`, `threshold`, `asOf`, `ruleVersion` et `evidenceRefs`. Une projection d’opportunité contient uniquement `opportunityId`, `opportunityType`, `status`, `confidence`, `asOf`, les versions et les références d’evidence.

Les réponses FI ne doivent pas contenir de transaction, contrepartie, remittance, secret, vecteur brut ou champ permettant de reconstruire ces éléments. Cette minimisation doit être testée par schéma et par inspection de payload.

## 6. Sécurité : scopes, grants, isolation et audit

### 6.1 Authentification et scopes — **À IMPLEMENTER**

Le token doit être validé avec issuer autorisé, audience obligatoire, algorithme autorisé, signature valide, `exp`, `nbf`, `sub` et les claims de client nécessaires. L’email ne doit être utilisé que s’il est vérifié. Les rôles ne remplacent pas les scopes OAuth.

Les scopes minimaux proposés sont :

- `fi:portfolio:read` pour l’overview autorisé ;
- `fi:company:read` pour le drill-down autorisé ;
- `fi:signals:read` si les signaux sont exposés séparément ;
- `fi:portfolio:export` uniquement après décision BOA distincte ;
- `fi:grant:write`, `fi:grant:revoke` et `fi:audit:read` uniquement pour des surfaces d’administration séparées et non incluses dans l’API de lecture initiale.

L’absence de token donne `401`. Un token valide sans scope donne `403`. Une ressource hors périmètre doit donner une réponse uniforme, idéalement `404` selon la politique approuvée, sans révéler son existence, son count ou ses métadonnées.

### 6.2 Grants et décision d’accès — **À IMPLEMENTER**

Créer un module central d’autorisation qui vérifie, dans cet ordre, le token, le scope, le Consumer/Fund résolu côté serveur, l’appartenance de la ressource, le grant actif, le purpose et la fenêtre temporelle. `revoked_at` est prioritaire sur `expires_at`. Les grants ne sont pas renouvelés implicitement.

La décision doit être deny-by-default et réutilisée par chaque route. Elle doit refuser les incohérences token/tenant, les IDs devinables hors scope, les grants destinés à un autre subject/client et les combinaisons Consumer/Fund incompatibles. Le client ne peut jamais imposer son propre `consumer_id`, `fund_id`, RM ou branch scope.

### 6.3 RLS et privilèges SQL — **À IMPLEMENTER / BLOCKED**

Définir les rôles SQL minimaux, révoquer les accès inutiles et activer `ENABLE ROW LEVEL SECURITY` et `FORCE ROW LEVEL SECURITY` sur les tables FI. Le backend doit établir le contexte Consumer/Fund dans une transaction contrôlée et signée selon une convention validée. Les tests doivent couvrir owner, service account, bypass potentiel et `SELECT/INSERT/UPDATE/DELETE` cross-consumer/cross-fund.

Cette partie est **BLOCKED** sans décision BOA sur la topologie PostgreSQL, les rôles de service, la gestion du contexte et la séparation entre audit technique et audit métier.

### 6.4 Journal d’accès — **À IMPLEMENTER**

Chaque succès, refus, ressource inexistante, expiration, révocation et erreur doit produire un événement d’audit corrélé. Il contient au minimum `subject`, `client_id`, `consumer_id`, `fund_id`, `resource_type`, `resource_id` non sensible, scope demandé, décision, `reason_code`, `grant_id`, purpose, `correlation_id`, date et expiration observée.

Le journal est append-only et ne contient ni token, ni secret, ni payload financier complet. Sa lecture est réservée à un scope d’audit séparé. Sa rétention, son chiffrement, son accès et sa valeur probatoire sont **HYPOTHÈSES À VALIDER AVEC BOA**.

## 7. Indicateurs point-in-time, provenance et gouvernance

### 7.1 Contexte temporel — **À IMPLEMENTER**

Toutes les données de la réponse doivent utiliser le même `asOf` explicite et une convention UTC/date validée. Une transaction est éligible uniquement si son statut est `BOOKED`, si `valueDate <= asOf` et si la source était disponible au plus tard à `asOf`. Les statuts `PENDING`, `DECLINED` et `CANCELLED` sont exclus.

Les fenêtres 30, 90 et 365 jours doivent être inclusives, versionnées et testées aux frontières. Une source arrivée après `asOf` est exclue même si sa `valueDate` est antérieure. Les données absentes, l’historique insuffisant et le zéro observé doivent être rendus différemment.

Chaque contribution doit porter une source, une référence, une version, un watermark, une disponibilité et, lorsque pertinent, un checksum. Un `traceId` unique est propagé de la requête publique aux appels sortants, à l’audit et à la réponse.

### 7.2 Lot 15 et règles — **IMPLEMENTÉ À RÉUTILISER, CONTRAT FI À IMPLEMENTER**

Réutiliser les snapshots et politiques de visibilité multibancaire, les fingerprints de transferts interbancaires et le ratio encaissements/CA déclaré. FI ne doit pas recalculer les pénalités Opportunity ni modifier les seuils existants. Toute nouvelle présentation doit référencer la version du calcul existant.

Le résultat actif doit déclarer `executionMode=DETERMINISTIC_RULES`, `mlMode=POC_SHADOW`, `rulesWeight=1` et `mlWeight=0`. Un score shadow peut être conservé pour comparaison ou audit, mais ne doit jamais influencer le résultat, le tri, le statut ou une action. Aucun chemin LLM, GPU, apprentissage en ligne ou donnée réelle n’est accepté.

## 8. UX backend-first limitée à deux parcours

### 8.1 Portfolio Overview — **À IMPLEMENTER**

Le premier écran présente uniquement le périmètre autorisé, le nombre d’entreprises accessible, les métriques disponibles, l’`asOf`, la fraîcheur, la qualité, la provenance et les états de dépendance. Il ne présente pas une décision de crédit, une solvabilité, une action ou un score ML actif.

L’écran doit utiliser les composants existants de tokens, panneaux, KPI, badges, tableaux et états. Il doit afficher clairement `RULES_ONLY`, `rulesWeight=1`, `mlWeight=0`, `POC_SHADOW`, données synthétiques et avertissement d’usage lorsqu’ils sont pertinents. Une synthèse vide n’est jamais remplacée par une fixture ou une valeur statique.

### 8.2 Company Drill-down — **À IMPLEMENTER**

Le second écran présente les agrégats autorisés pour une société dans le périmètre du consommateur. Il montre la période, la devise si validée, l’`asOf`, la qualité, la provenance, les références de preuves et la distinction entre fait, signal relationnel et opportunité existante.

L’accès frontend ne remplace pas le contrôle serveur. Un deep-link hors périmètre doit aboutir à un état uniforme. Les états `loading`, `empty`, `forbidden`, `not found`, `not implemented`, `data unavailable`, erreur gateway et réponse partielle doivent être distincts et accessibles.

Le périmètre UX, les personas exacts, les libellés et les conventions de devise sont **HYPOTHÈSES À VALIDER AVEC BOA**. Tant que l’API n’est pas contractualisée, aucune page FI ne doit être présentée comme livrée.

## 9. Seed synthétique et gestion des données

### 9.1 Seed de démonstration — **À IMPLEMENTER**

Créer un seed isolé, reproductible et explicitement marqué `SYNTHETIC` ou `DEMO`. Il doit fournir au minimum deux Consumers, deux Funds distincts, plusieurs portfolios, des sociétés synthétiques, des grants valides/expirés/révoqués, des affectations temporelles et des sources avec watermarks différents.

Le seed doit couvrir :

- données `BOOKED` et données exclues ;
- frontières de dates `asOf` et fenêtres 30/90/365 jours ;
- source disponible après `asOf` ;
- absence de données et historique insuffisant ;
- données partielles et dépendance en timeout ;
- signals, features et opportunities référencés sans duplication ;
- Consumer/Fund A et B pour les tests de non-fuite ;
- poids rules/ML conformes au mode `POC_SHADOW`.

Le seed ne doit contenir aucune donnée BOA réelle, aucun secret et aucun identifiant ressemblant à une donnée de production. La provenance de chaque fixture doit être documentée.

### 9.2 Reproductibilité — **À IMPLEMENTER**

Figer la graine, la version du seed, le schéma et les commandes. Produire un manifeste avec commit, seed, environnement, versions d’outils et checksum des données générées. Le seed ne doit jamais être un fallback automatique de l’application.

## 10. Stratégie de tests

### 10.1 Préparation de l’environnement — **À IMPLEMENTER / BLOCKED**

Documenter l’invocation reproductible, notamment `PYTHONPATH=backend/src` et `APP_ENV=test`. Séparer explicitement le mode test du mode production. Ajouter un test de bootstrap qui refuse `BOA_AUTH_DISABLED=true` hors des environnements autorisés. Résoudre le conflit d’import qui peut charger un autre dépôt.

Cette étape est **BLOCKED** tant que la suite existante n’est pas suffisamment verte pour distinguer ses régressions historiques des défauts FI. Aucun contournement d’authentification ne doit être ajouté en production.

### 10.2 Unitaires et contrats — **À IMPLEMENTER**

Ajouter des tests pour les DTO Pydantic/OpenAPI, les erreurs, les limites de pagination, les filtres inconnus, les `operationId`, les codes `401/403/404/409/422/429/500/503`, la validation de confidence, l’absence de champs bruts et l’unicité de l’enveloppe.

Tester les fonctions pures de point-in-time, les fenêtres, Decimal, doublons, checksum, idempotence, états `UNKNOWN` et `INSUFFICIENT_HISTORY`, propagation du `traceId`, source status et calcul des poids effectifs.

### 10.3 Sécurité et isolation — **À IMPLEMENTER**

Tester JWT absent ou invalide, issuer, audience, algorithme, signature, `exp`, `nbf`, `azp/client_id`, rôles et scopes. Tester scopes absents, insuffisants, excédentaires et séparation lecture/administration.

Tester Consumer A/B et Fund A/B sur liste, détail et export futur. Vérifier l’absence de ligne, count, erreur ou métadonnée révélatrice hors périmètre. Tester grants non démarrés, actifs, expirés, révoqués, mauvais purpose, mauvais subject/client et révocation immédiate.

Tester RLS avec deux rôles PostgreSQL et `FORCE ROW LEVEL SECURITY`, l’absence de bypass owner/service et les privilèges minimaux. Tester l’injection SQL/filtres, SSRF via configuration downstream, payload amplification, mass assignment, secrets et stack traces.

### 10.4 Intégration et résilience — **À IMPLEMENTER**

Simuler chaque domaine propriétaire avec corrélation et auth. Tester `404`, `409`, `429`, `5xx`, timeout, réponse malformée, retry borné, circuit breaker ou équivalent, bulkhead, réponse partielle et absence de duplication de matérialisation.

Vérifier la cohérence `asOf`, `calculationVersion`, `featureSetVersion`, `ruleVersion` et `inputWatermark` entre sources. Vérifier que FI ne crée pas d’opportunity et ne change ni moteur, ni règle, ni lifecycle.

### 10.5 E2E, non-fuite et UX — **À IMPLEMENTER**

Ajouter `tests/e2e/financial-intelligence.spec.ts` pour l’authentification B2B, les deux parcours, la pagination, le deep-link, les réponses hors périmètre, les états d’erreur, la provenance, la gouvernance et la minimisation.

Tester les écrans à 320, 375, 768 et 1024 pixels, avec zoom 200 %, clavier, focus, landmarks, lecteurs d’écran, contrastes, tableaux scrollables et `prefers-reduced-motion`. Aucun test ne doit accepter une fixture statique lorsque l’API est absente.

### 10.6 Performance — **À IMPLEMENTER / BLOCKED**

Créer une campagne synthétique pour 10, 50, 100 et 500 portfolios. Mesurer cold/warm, concurrence, p50/p95/p99, throughput, taux d’erreur, taille de payload, nombre de requêtes SQL, appels downstream, saturation des pools, CPU, mémoire, queue et backpressure.

Les seuils proposés, par exemple p95 lecture inférieur ou égal à 500 ms et p99 inférieur ou égal à 1 s, sont des **HYPOTHÈSES À VALIDER AVEC BOA**. La preuve existante du pipeline séquentiel 500 et du load test 50k ne peut pas être substituée à cette campagne FI. La validation performance est **BLOCKED** sans dataset, concurrence et SLO approuvés.

## 11. Observabilité et exploitation

### 11.1 Instrumentation — **À IMPLEMENTER**

Ajouter des logs structurés et redacted avec `traceId`, route, Consumer/Fund non sensible, décision d’accès, statut, durée, dépendance, timeout, partialité et version. Ne jamais journaliser token, secret, transaction brute ou payload financier complet.

Ajouter des métriques RED : débit, taux d’erreur et durée par endpoint. Ajouter des métriques par dépendance : latence, timeout, retry, circuit state, partial response, appels et erreurs. Ajouter des traces distribuées avec propagation de corrélation et cardinalité maîtrisée.

Créer des dashboards et alertes pour SLO de latence, fraîcheur, erreurs, partialité, refus d’accès, taux de révocation, saturation DB/HTTP, drift de watermark et anomalies de checksum. Les budgets, la rétention et les seuils d’alerte sont **HYPOTHÈSES À VALIDER AVEC BOA**.

### 11.2 Exploitabilité — **À IMPLEMENTER**

Documenter les runbooks de dépendance indisponible, de révocation urgente, de rotation OIDC, de corruption de snapshot, de retard de fraîcheur, de dépassement de budget et de fuite potentielle. Définir RPO/RTO, rétention et responsabilités de garde. Aucun résultat partiel ne doit être présenté comme complet.

## 12. CI/CD, sécurité de release et artefacts

### 12.1 Pipeline — **À IMPLEMENTER**

Créer un job FI séparé en CI, avec étapes rapides et intégration distinctes : lint/type-check, unitaires, contrats OpenAPI, migration upgrade/downgrade, sécurité, intégration, E2E, performance synthétique et contrôle documentaire. Le job doit avoir un timeout borné inférieur au budget global du runner et publier ses diagnostics même en échec.

Le pipeline doit exiger les artefacts suivants : résultats de tests, couverture, OpenAPI figée, rapports de migration, résultats de charge, rapport sécurité, métriques d’observabilité de test et manifeste SHA-256 mentionnant commit, environnement, seed et versions d’outils.

### 12.2 Supply chain — **À IMPLEMENTER**

Compléter les scans existants par SBOM CycloneDX ou SPDX, scan d’image par digest, signature/attestation et seuil CVE documenté. Les exceptions doivent être approuvées et expirables. La présence de gitleaks, pip-audit, npm audit ou Trivy seule ne suffit pas à prouver une release FI sûre.

### 12.3 Gate de promotion — **BLOCKED**

Aucune promotion ne doit avoir lieu tant que les tests historiques sont rouges sans cause expliquée, que la matrice d’accès n’est pas prouvée, que les artefacts FI sont absents, que le threat model n’est pas approuvé ou que les SLO de charge et d’observabilité ne sont pas validés. La CI ne doit jamais interpréter un job annulé à la limite de temps comme un succès.

## 13. Documentation à produire

### 13.1 Documents requis — **À IMPLEMENTER**

Créer et maintenir :

- `docs/lots/LOT-16-FINANCIAL-INTELLIGENCE-API.md`, décrivant périmètre, non-objectifs, données synthétiques et état de livraison ;
- `docs/financial-intelligence-api.md`, contenant le contrat, les enveloppes, les erreurs, la pagination, `asOf`, la provenance et la compatibilité ;
- `docs/financial-intelligence-threat-model.md`, couvrant tenant confusion, enumeration, RLS, injection, SSRF, secrets, exports et journalisation ;
- `docs/financial-intelligence-capacity-plan.md`, couvrant p50/p95/p99, portfolios 10/50/100/500, appels, CPU, mémoire, DB et SLO ;
- `docs/ux-architecture.md` ou une section dédiée, définissant les deux parcours, les états et les libellés non-crédit ;
- un runbook d’exploitation et de révocation ;
- un mapping BIAN explicitement qualifié de candidat tant que BOA ne l’a pas validé.

Toutes les documentations doivent indiquer `SYNTHETIC/DEMO`, `RULES_ONLY`, `POC_SHADOW`, `rulesWeight=1`, `mlWeight=0`, l’absence de LLM/GPU et l’interdiction de conclure à une décision bancaire.

## 14. Séquence de réalisation proposée

### Phase 0 — Décisions et garde-fous — **BLOCKED tant que non approuvée**

Valider avec BOA le périmètre des deux parcours, les Consumers/Funds, les scopes, les grants, la politique de non-fuite, les SLO, la fraîcheur, la rétention, le statut juridique des signaux, la devise, les personas, le mapping d’entreprise et la politique RLS. Corriger en parallèle le bootstrap de tests et le conflit d’import.

**Sortie attendue :** ADR approuvées, matrice d’accès, dictionnaire de données interdites, SLO provisoires, threat model accepté et décision sur la persistance.

### Phase 1 — Contrats et package FI — **À IMPLEMENTER**

Créer `financial_intelligence/contracts.py`, les erreurs, les versions de contrat et l’OpenAPI. Définir l’enveloppe commune, `PointInTimeContext`, `SourceRef`, `SourceStatus`, `PolicyMetadata`, les projections minimisées, la pagination et les codes d’erreur.

**Sortie attendue :** contrat validable sans dépendance réelle, operation IDs uniques, schémas stricts et tests de contrat.

### Phase 2 — Autorisation et audit — **À IMPLEMENTER**

Créer `authorization.py`, `clients.py` et l’audit append-only. Implémenter les scopes, la résolution Consumer/Fund, la vérification grant, le deny-by-default, la décision uniforme hors périmètre et la propagation de corrélation.

**Sortie attendue :** tests JWT/scopes/grants, matrice A/B, logs d’accès corrélés et aucun accès cross-scope.

### Phase 3 — Migration et seed — **À IMPLEMENTER, puis revue**

Implémenter la migration approuvée, la RLS, les rôles SQL minimaux et le seed synthétique reproductible. Vérifier upgrade, downgrade, ré-upgrade et absence de données réelles.

**Sortie attendue :** migration idempotente et réversible, fixtures synthétiques A/B et preuves RLS.

### Phase 4 — Orchestration et projections — **À IMPLEMENTER**

Créer `service.py` et les clients sortants typés. Implémenter le contexte point-in-time, les budgets de fan-out, la résilience, la projection Analytics/Visibility/Signals/Features/Opportunities et la réponse partielle explicite.

**Sortie attendue :** cohérence de versions et watermark, absence de données brutes, invariants Lot 15 conservés, rules-only démontré.

### Phase 5 — Gateway et API publique — **À IMPLEMENTER**

Ajouter seulement les routes `/api/v1/financial-intelligence` dans le Gateway. Vérifier qu’aucune route interne n’est publiée, que les erreurs sont normalisées et que l’OpenAPI générée ne contient pas de doublon d’operation ID.

**Sortie attendue :** contract tests HTTP verts, auth et non-fuite démontrées.

### Phase 6 — UX backend-first — **À IMPLEMENTER**

Ajouter les deux écrans, leurs hooks et leurs états spécifiques seulement après stabilisation du contrat. Ne pas ajouter de page ML, d’action, de catalogue, d’export ou de décision de crédit.

**Sortie attendue :** responsive/accessibility, aucun fallback statique et affichage explicite de fraîcheur, provenance et gouvernance.

### Phase 7 — Résilience, performance et observabilité — **À IMPLEMENTER / BLOCKED par les SLO**

Ajouter métriques, traces, dashboards, alertes, benchmarks 10/50/100/500, tests de charge, limites de ressources, circuit breaker et runbooks. Valider les seuils avec BOA.

**Sortie attendue :** rapport de capacité reproductible, budgets downstream, comportement contrôlé sous saturation et artefacts complets.

### Phase 8 — Release gate — **BLOCKED jusqu’à preuve complète**

Exécuter la suite historique et FI avec l’environnement documenté. Vérifier migrations, sécurité, threat model, SBOM, signature, artefacts, documentation, rollback et absence de données réelles. Toute divergence est classée avant promotion.

**Sortie attendue :** décision Go/No-Go signée. En l’absence d’une preuve, le statut reste **BLOCKED**, jamais « production ready ».

## 15. Definition of Done

Le Lot 16 ne peut être déclaré terminé que si toutes les conditions suivantes sont satisfaites :

1. Le périmètre, les non-objectifs, les scopes, les grants, les SLO et les responsabilités sont approuvés par BOA.
2. Les routes publiques sont limitées à `/api/v1/financial-intelligence`, versionnées, documentées et sans endpoint write ou interne exposé.
3. Les DTO, erreurs, pagination, `asOf`, freshness, provenance, watermark, checksum et confidence sont contractuels et testés.
4. L’autorisation vérifie token, scope, Consumer, Fund, ressource et grant actif. L’accès est deny-by-default et ne révèle pas les ressources hors périmètre.
5. Les tests RLS, grants, révocation, expiration, logs append-only et ségrégation A/B sont verts.
6. Tous les agrégats respectent le point-in-time : `BOOKED`, `valueDate <= asOf`, source disponible à `asOf`, fenêtres versionnées et absence de mélange de watermarks.
7. FI ne lit pas directement les ORM des autres domaines, ne crée pas d’opportunity, ne change pas les règles et n’expose aucune donnée brute.
8. La réponse déclare explicitement `RULES_ONLY`, `POC_SHADOW`, `rulesWeight=1`, `mlWeight=0`, sans LLM ni GPU.
9. Les migrations upgrade/downgrade/ré-upgrade, la RLS et le seed synthétique sont reproductibles et vérifiés.
10. Les unitaires, contrats, intégration, sécurité, E2E, non-fuite, accessibilité et performance sont verts avec les artefacts attendus.
11. Les métriques, traces, logs redacted, dashboards, alertes et runbooks permettent d’expliquer une latence, une erreur, une réponse partielle ou un refus.
12. La CI publie un manifeste, un SBOM, les rapports et les preuves de commit, d’environnement et de seed.
13. Les risques restants, les limites de données synthétiques et les hypothèses BOA sont écrits et acceptés.
14. Une revue finale confirme que le lot n’est pas présenté comme production-ready tant que les exigences de production, conformité, exploitation et données BOA ne sont pas validées.

## 16. Risques et limites résiduels

| Risque ou limite | Statut | Réduction prévue |
|---|---|---|
| Le Lot 16 est absent du commit audité. | **BLOCKED** | Implémenter les phases 0 à 8 et conserver le statut non livré jusqu’aux preuves. |
| Les données sont synthétiques et ne prouvent pas la qualité BOA. | **HYPOTHÈSE À VALIDER AVEC BOA** | Obtenir contrats de sources, owners, qualité, réconciliation et environnement non productif approuvé. |
| Une façade pourrait devenir un God Service. | **À IMPLEMENTER** | Ownership explicite, clients typés, DTO anti-corruption, aucun ORM partagé et aucune règle locale propriétaire. |
| Une requête pourrait fuiter un autre Consumer/Fund. | **BLOCKED** | Scopes, grants, RLS FORCE, filtrage serveur, réponses uniformes et tests A/B. |
| `asOf` pourrait mélanger des données arrivées plus tard. | **À IMPLEMENTER** | Watermark, `sourceAvailableAt`, version de calcul, validation d’homogénéité et tests frontières. |
| Un score ML pourrait être interprété comme actif. | **À IMPLEMENTER** | Métadonnées obligatoires, assertion rules=1/ML=0, wording UX et release gate. |
| Les dépendances pourraient rendre la réponse lente ou partielle. | **À IMPLEMENTER** | Budgets, timeouts, retries bornés, circuit breaker, bulkheads, cache versionné et SLO approuvés. |
| Les logs ne permettraient pas de prouver qui a vu quoi. | **À IMPLEMENTER** | Journal d’accès append-only corrélé et redacted, avec contrôle d’accès auditeur. |
| La suite actuelle est affectée par l’environnement et des régressions. | **BLOCKED** | Bootstrap reproductible, isolation `PYTHONPATH`, correction/qualification des échecs et gate séparé. |
| Les scans seuls ne prouvent pas l’intégrité de release. | **À IMPLEMENTER** | SBOM, digest, signature, attestation, exceptions approuvées et threat model. |
| Le frontend pourrait présenter une fixture comme un résultat réel. | **À IMPLEMENTER** | Aucun fallback statique, état `NOT_IMPLEMENTED`, provenance visible et tests E2E d’indisponibilité. |

## 17. Références du dépôt

Les références ci-dessous sont des points de départ internes. Elles décrivent des capacités existantes ou des garde-fous antérieurs ; elles ne prouvent pas la livraison du Lot 16.

[1]: ../api.md "Contrats API et conventions d’erreurs existantes"
[2]: ../security.md "Intentions de sécurité et limites de données synthétiques"
[3]: ../../backend/src/boa_oi/gateway_api.py "Gateway public et conventions de routage"
[4]: ../../backend/src/boa_oi/platform.py "Application de service et validation d’authentification"
[5]: ../../backend/src/boa_oi/visibility.py "Calcul de visibilité point-in-time réutilisable"
[6]: ../../database/migrations/versions/0020_multibank_visibility.py "Migration Lot 15 de visibilité multibancaire"
[7]: ../../database/migrations/versions/0017_ml_shadow_governance.py "Gouvernance ML shadow et poids effectifs"
[8]: ../../tests/unit/test_ml_governance.py "Tests de gouvernance ML existants"
[9]: ../../tests/e2e/multibank-visibility.spec.ts "Tests E2E de visibilité multibancaire"

> **Limite de preuve.** Ces références concernent l’état antérieur audité. Tant que les livrables et tests décrits dans ce plan n’existent pas et ne sont pas exécutés avec succès, le Lot 16 reste **À IMPLEMENTER** ou **BLOCKED** selon le prérequis concerné.
