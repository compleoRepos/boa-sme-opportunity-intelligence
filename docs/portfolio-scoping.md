# Périmètres agence, chargé de clientèle et portefeuille

**Produit :** BOA SME Opportunity Intelligence  
**Statut :** dashboards CC/agence et contrôles de périmètre MVP implémentés ; politiques ABAC avancées différées
**Responsable documentaire :** équipe produit pilote

> Dans ce document, **CC** désigne le chargé de clientèle PME. Le rôle technique existant reste `RELATIONSHIP_MANAGER`. Le responsable d’agence utilise `BRANCH_MANAGER`. Cette correspondance évite d’introduire un second rôle pour la même fonction.

## 1. Hiérarchie normative

La navigation et l’autorisation suivent la hiérarchie suivante :

```text
Agence
  → dashboard agence
  → CC de l’agence
  → dashboard CC
  → portefeuille actif du CC
  → client PME
  → opportunités, signaux, comptes, transactions et actions autorisés
```

**Customer Service** reste la source de vérité de l’agence, du CC, du portefeuille et des affectations temporelles. Keycloak porte les identités, rôles et scopes, mais une claim de token ne remplace pas la vérification d’une affectation active. Le Gateway applique un premier contrôle ; chaque service propriétaire réapplique le contrôle de périmètre.

## 2. Entités de périmètre

| Entité | Identifiant | Règle de propriété |
|---|---|---|
| `Branch` | `branchId` | unité organisationnelle ; ne possède pas les clients |
| `RelationshipManager` | `relationshipManagerId` lié au `sub` Keycloak | identité fonctionnelle du CC |
| `Portfolio` | `portfolioId` | regroupement durable ou temporel de clients sous responsabilité d’un CC |
| `PortfolioAssignment` | `assignmentId` | relation temporelle entre client, portefeuille, CC et agence |
| `Customer` | `customerId` | PME source de vérité Customer Service |

Une affectation contient `portfolioId`, `relationshipManagerId`, `branchId`, `validFrom`, `validTo`, `assignmentType`, `isPrimary`, `reason`, `actor`, `sourceSystem`, `sourceEventId`, `sourceWatermark` et `sourcePayloadHash`. Un client possède au plus une affectation primaire active à un instant donné. Le pilote refuse les chevauchements au niveau PostgreSQL. Une affectation secondaire, une équipe de couverture ou une délégation temporaire restent hors contrat.

## 3. Dashboards distincts

### 3.1 Dashboard CC

Le dashboard CC répond à « que dois-je traiter dans mon portefeuille ? ». Il ne peut retourner que les clients dont l’affectation autorisée est active pour le sujet courant. Les agrégats et listes utilisent le même filtre serveur ; un total ne doit jamais inclure un client absent de la liste pour raison de périmètre.

Les éléments minimaux sont : opportunités ouvertes par priorité, nouveaux signaux, actions échues ou à venir, taux d’engagement du portefeuille, fraîcheur des données et alertes de qualité. Le dashboard permet ensuite le drill-down vers le portefeuille, puis la fiche PME.

Le CC peut lire les preuves et effectuer les actions autorisées sur ses clients. Il ne peut ni demander un autre `relationshipManagerId`, ni élargir `branchId`, ni accéder au dashboard agence.

### 3.2 Dashboard agence

Le dashboard agence répond à « comment l’agence traite-t-elle ses portefeuilles ? ». Il agrège uniquement les CC et clients liés aux `branchIds` autorisés du responsable d’agence. Il présente les volumes par CC, type d’opportunité, priorité, statut d’engagement et fraîcheur. Les métriques sensibles sont agrégées et minimisées.

Le responsable d’agence peut descendre vers le dashboard d’un CC puis vers un client de son agence. **La lecture de l’agence n’accorde pas automatiquement le droit d’agir au nom du CC.** Les actions sur un client exigent le scope dédié `actions:write:branch` et une politique BOA explicite. À défaut, le rôle est en lecture et pilotage.

## 4. Matrice d’autorisation

| Capacité | `RELATIONSHIP_MANAGER` / CC | `BRANCH_MANAGER` | `DATA_ANALYST` | `ADMIN` |
|---|---:|---:|---:|---:|
| Lire son dashboard CC | Oui | Oui pour un CC de sa branche | Non | Non par défaut |
| Lire le dashboard agence | Non | Oui pour ses branches | Agrégats approuvés uniquement | Non par défaut |
| Lister le portefeuille | Le sien | Portefeuilles de sa branche | Données pseudonymisées si accordées | Métadonnées de configuration uniquement par défaut |
| Lire une fiche PME | Affectation active | Client d’une branche autorisée | Permission dédiée et finalité approuvée | Permission dédiée ; le rôle admin seul ne suffit pas |
| Lire transactions et preuves | Affectation active et scopes domaine | Branche et scopes domaine | Selon jeu de données approuvé | Non par défaut |
| Créer une action commerciale | Sur son portefeuille | Non par défaut ; scope `actions:write:branch` requis | Non | Non par défaut |
| Gérer règles, features, modèles | Non | Lecture de versions publiées | Selon fonction analytique | Scopes administratifs dédiés |
| Promouvoir un modèle | Non | Non | Non par défaut | Oui avec séparation des tâches |

Cette matrice affine le rôle `ADMIN` : l’administration technique ou du moteur n’accorde pas automatiquement l’accès aux données détaillées des clients. Une attribution explicite de scope et de périmètre est nécessaire.

## 5. Scopes et claims

Les scopes publics cibles sont :

```text
dashboard:cc:read
dashboard:branch:read
portfolios:read
customers:read
opportunities:read
signals:read
actions:read
actions:write
actions:write:branch
features:read
models:read
models:write
models:approve
ml-monitoring:read
audit:read
```

Le token Keycloak peut indiquer `branchIds` et le mode `customerScopes = assigned`, mais le backend résout le périmètre effectif auprès de Customer Service ou d’une projection signée et fraîche. Un `customerId`, `portfolioId`, `relationshipManagerId` ou `branchId` fourni par le client est toujours traité comme un **filtre demandé**, jamais comme une preuve d’accès.

La décision d’autorisation est l’intersection de :

```text
rôle ∩ scopes ∩ périmètre organisationnel ∩ affectation temporelle ∩ finalité de l’endpoint
```

Si révéler l’existence d’une ressource hors périmètre constitue une fuite, la réponse est `404 RESOURCE_NOT_FOUND`. Un scope absent sur une ressource connue dans le périmètre retourne `403 FORBIDDEN`.

## 6. Résolution de périmètre côté services

Pour chaque accès à une ressource client :

1. le Gateway valide le JWT et les scopes de premier niveau ;
2. le service cible valide le contexte de service et le contexte utilisateur signé ;
3. le service résout le `customerId` associé à la ressource ;
4. Customer Service ou une projection de périmètre confirme une affectation active à `asOf` ;
5. le service applique la finalité et le niveau de détail permis ;
6. l’accès autorisé ou refusé est audité avec la règle de périmètre utilisée.

Une projection de périmètre future devra porter `projectionVersion`, `sourceWatermark`, `generatedAt` et `validUntil`. Elle n’est pas implémentée dans le pilote : les services interrogent les affectations datées de Customer Service. Si une projection est ajoutée, son expiration devra refuser les écritures et ne devra jamais basculer vers un accès global.

## 7. Réaffectations, délégations et historique

Une réaffectation clôt l’ancienne ligne et crée une nouvelle affectation. Elle ne réécrit pas l’acteur historique d’une action, l’opportunité ou le score. Le nouveau CC voit les opportunités encore valides du client à partir de la date d’effet, selon les règles de confidentialité. L’ancien CC perd l’accès opérationnel après `validTo`, sauf permission d’audit explicitement accordée.

Une délégation temporaire possède une date de fin obligatoire, un motif et un approbateur. Elle n’est pas exprimée par un rôle global. Les traitements de masse utilisent l’affectation valable à l’`asOf` du lot afin qu’un rerun reste reproductible.

Les agrégats historiques d’agence sont rattachés à l’agence valable au moment de l’action ou de l’opportunité, selon la métrique documentée. Le dashboard doit indiquer s’il utilise la structure **courante** ou **historique**.

## 8. Contrats de lecture cibles

| Route | Vue | Périmètre imposé |
|---|---|---|
| `GET /api/v1/dashboards/me` | dashboard CC du sujet courant | aucun `relationshipManagerId` accepté |
| `GET /api/v1/branches/{branchId}/dashboard` | dashboard agence | `branchId` dans le périmètre effectif |
| `GET /api/v1/branches/{branchId}/relationship-managers` | liste des CC | branche autorisée |
| `GET /api/v1/relationship-managers/{id}/dashboard` | drill-down CC | soi-même ou responsable de l’agence |
| `GET /api/v1/portfolios/{portfolioId}` | résumé portefeuille | affectation active ou branche autorisée |
| `GET /api/v1/portfolios/{portfolioId}/customers` | clients paginés | périmètre serveur, curseur opaque |
| `GET /api/v1/customers/{customerId}` | client PME | contrôle par ressource |

Les réponses de dashboard portent `scope` avec `scopeType`, `scopeId`, `asOf`, `assignmentWatermark` et `partial`. Elles n’exposent jamais la liste des identifiants autorisés dans un token ou une erreur.

## 9. ML, outcomes et périmètre

Le ML Engine reçoit des lots déjà filtrés par l’orchestrateur. Il n’accorde pas d’accès utilisateur. Une prédiction porte `customerId`, mais seuls Opportunity Service et les dashboards autorisés peuvent l’exposer.

Le monitoring agence présente des agrégats de score et de performance. Les cellules trop petites ou identifiantes doivent être supprimées ou regroupées selon la politique BOA. Le CC voit l’explication d’un client de son portefeuille ; il ne voit ni artefact de modèle, ni dataset d’entraînement, ni statistiques de clients hors périmètre.

Les outcomes utilisés dans un dataset futur conservent le périmètre et la finalité approuvée, mais l’entraînement ne doit pas dépendre de l’accès interactif du CC. Il utilise un export gouverné, pseudonymisé, consenti ou couvert par une base de traitement approuvée, tel que défini dans [`ml-engine.md`](./ml-engine.md).

## 10. Audit et tests bloquants

L’audit enregistre le sujet, les rôles/scopes, le type de périmètre, l’identifiant demandé, la décision, la règle appliquée, le watermark d’affectation, l’endpoint et le `correlationId`. Les refus n’enregistrent pas plus de données client qu’il n’est nécessaire.

Les tests bloquants couvrent : accès CC à son client, accès CC à un client d’un autre portefeuille, accès responsable à sa branche et à une autre branche, réaffectation à date d’effet, lecture historique `asOf`, rejeu idempotent, événement source conflictuel, événement hors ordre, compte de service non autorisé et cohérence entre totaux et listes paginées. La délégation et la projection stale ne peuvent pas être déclarées PASS car elles restent hors périmètre du pilote.

## 11. Limites du MVP

Le MVP conserve une hiérarchie simple : un client, une affectation primaire active, un portefeuille principal et une agence. Les équipes multi-agences, portefeuilles matriciels, délégations complexes, contrôle géographique dynamique et politiques ABAC externes sont différés.

Les dashboards agence et CC sont servis par Portfolio Service et exposés uniquement via le Gateway. Le dashboard CC force l’identifiant de chargé issu du token, même lorsqu’un autre `relationshipManagerId` est fourni. Le dashboard agence limite ses agrégats et son drill-down aux `branchIds` autorisés. Customer Service et le Gateway renvoient `404` pour une ressource hors périmètre afin d’éviter d’en révéler l’existence. Les délégations complexes, le moteur ABAC externe, une projection signée et les scopes d’action agence restent hors du MVP.

## 12. Synchronisation gouvernée implémentée

La migration `0012_portfolio_sync_governance` ajoute les identifiants durables de portefeuille, la provenance source, les reçus rejouables et le journal des événements. La route administrative `POST /api/v1/admin/portfolio-assignments/sync` exige une clé d’idempotence et un lot de contrat `1.0`. La route interne correspondante accepte uniquement un administrateur ou le compte de service `banking-integration-service`; le rôle générique `SERVICE` ne suffit pas.

Les événements sont triés par date d’effet et identifiant source. Une date d’effet future clôt l’affectation courante à cette date tout en la laissant active jusque-là. Les trois services Customer, Portfolio et Opportunity appliquent `validFrom <= now < validTo`, avec `validTo` ouvert lorsque nul. Les lectures d’administration acceptent `asOf` et restituent la structure valable à l’instant demandé.

Le pilote adopte une politique explicite pour les événements hors ordre : un événement antérieur au dernier intervalle connu est refusé par `409 OUT_OF_ORDER_ASSIGNMENT`. La correction d’un historique ancien exige donc un processus de réconciliation administré ; elle n’est jamais appliquée silencieusement. Cette décision est réversible après validation du contrat source réel par BOA.

## Références

[1]: ../architecture/architecture.md "Architecture exécutable — BOA SME Opportunity Intelligence"
[2]: ./api.md "Contrats API-first"
[3]: ./data-model.md "Modèle relationnel PostgreSQL et pipeline de données"
[4]: ./security.md "Sécurité — BOA SME Opportunity Intelligence"
[5]: ./ml-engine.md "ML Engine CPU-ready"
