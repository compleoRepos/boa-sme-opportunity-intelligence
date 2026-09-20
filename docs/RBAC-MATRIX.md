# Matrice RBAC — BOA SME Opportunity Intelligence

**Statut du document :** inventaire statique du dépôt, destiné à la revue BOA. Il décrit les contrôles visibles dans le code et les tests présents ; il ne constitue pas une validation de sécurité en environnement BOA.

**Périmètre analysé :** `gateway_api.py`, `platform.py`, routes backend, realm Keycloak et routes frontend. Les liens ci-dessous sont relatifs au dépôt. Les mentions **HYPOTHÈSE À VALIDER AVEC BOA** signalent toute règle métier, volumétrie, coût, KPI, seuil ou exigence qui n’est pas démontrée par le code ou par un test identifié.

## 1. Décisions et limites non négociables

Le système décrit ici est un dispositif d’aide au pilotage commercial. **Aucune décision de crédit n’est prise par l’application.** Les opportunités, propensions, priorités, règles et explications ne doivent pas être interprétées comme une décision, une acceptation, un refus ou une limite de crédit. Cette limite est cohérente avec le texte de l’interface d’agence et avec le composant de résilience ML ([`BranchDashboardPage.tsx`](../frontend/src/features/branch/BranchDashboardPage.tsx), [`fallback-rules-only.md`](workstreams/fallback-rules-only.md)).

Le ML classique est **CPU-only** dans le POC et doit rester en mode **POC/shadow** tant que les labels BOA matures ne sont pas disponibles. Le dépôt contient des mécanismes de maturité des labels et un scorer local ; il ne fournit pas de preuve de labels BOA matures ni de performance métier BOA ([`mlops-governance.md`](workstreams/mlops-governance.md), [`ml_engine_api.py`](../backend/src/boa_oi/ml_engine_api.py), [`operations/api.py`](../backend/src/boa_oi/operations/api.py)). **Aucun LLM ni GPU n’est requis.** Le LLM est au mieux une capacité optionnelle hors chemin de décision, et la chaîne de secours documentée ne dépend ni d’un LLM ni d’un GPU ([`rule-studio.md`](rule-studio.md), [`fallback-rules-only.md`](workstreams/fallback-rules-only.md)).

Le document ne présente aucune donnée BOA, aucun résultat mesuré, aucun coût, aucune volumétrie de production, aucun KPI de performance et aucun seuil métier comme un fait. Les données du seed sont synthétiques et ne prouvent pas une distribution BOA. Toute cible non démontrée doit être formulée ainsi : **HYPOTHÈSE À VALIDER AVEC BOA**.

## 2. Légende de preuve

| Statut | Signification dans ce document |
|---|---|
| **IMPLÉMENTÉ** | Le contrôle, la route ou l’écran apparaît dans le code lu. Cela ne prouve pas son déploiement ni sa conformité BOA. |
| **PROUVÉ** | Un test identifié vérifie explicitement le comportement décrit. Cela ne signifie pas que toute la matrice est couverte. |
| **NON IMPLÉMENTÉ** | La capacité attendue n’a pas été trouvée dans le périmètre lu, ou le code montre qu’elle n’est pas disponible. |
| **À VALIDER** | Le code ou la documentation ne suffit pas à établir la règle métier, l’affectation BOA, le comportement en production ou la couverture de test. |

Une autorisation n’est jamais déduite de la seule UI. Les protections frontend sont une aide ergonomique ; l’autorité d’autorisation est le Gateway puis, lorsque le contrôle existe, le service backend et son scope objet.

## 3. Sources internes et modèle d’autorisation

| Élément | Constat | Statut |
|---|---|---|
| Principal OIDC | `platform.py` valide un bearer token, la signature, l’issuer, l’audience et les claims obligatoires `exp`, `iss`, `sub`, `aud`. Les rôles viennent de `realm_access` et, pour l’audience configurée, de `resource_access`. Les scopes `branchIds`, `relationshipManagerIds` et `customerScopes` viennent du claim `boa`. | **IMPLÉMENTÉ** — [`platform.py`](../backend/src/boa_oi/platform.py) |
| Mode développement | Quand `BOA_AUTH_DISABLED=true`, `X-Dev-Principal` peut fournir une persona locale. Le header est ignoré lorsque OIDC est actif. Sans persona, le mode local crée un principal de test très privilégié. | **IMPLÉMENTÉ**, risque à encadrer — [`platform.py`](../backend/src/boa_oi/platform.py), [`personas.ts`](../frontend/src/auth/personas.ts) |
| Refus d’authentification | Absence de bearer ou token invalide/expiré : `401`. | **IMPLÉMENTÉ** |
| Refus de rôle | Principal authentifié sans rôle requis : `403` avec `FORBIDDEN`. | **IMPLÉMENTÉ** |
| Isolation objet | Le Gateway vérifie `customer_id` pour les proxys qui portent cet identifiant et vérifie l’opportunité puis son client pour les routes d’action. Les services portfolio/opportunity appliquent des filtres de portefeuille ou d’agence et renvoient généralement `404` si l’objet n’est pas dans le périmètre. | **IMPLÉMENTÉ** pour les chemins observés ; couverture complète **À VALIDER** |
| Dissimilation objet | L’usage de `404` pour un objet hors scope est observé dans les services et tests. Il faut confirmer avec BOA si cette convention est obligatoire sur chaque objet et chaque route. | **À VALIDER** |
| UI | `ProtectedRoute`, `RoleRoute` et `RuleStudioRoute` masquent ou redirigent certains écrans. | **IMPLÉMENTÉ** comme UX, **NON SUFFISANT** comme contrôle de sécurité — [`ProtectedRoute.tsx`](../frontend/src/auth/ProtectedRoute.tsx), [`App.tsx`](../frontend/src/App.tsx) |

## 4. Rôles, personas et périmètres

### 4.1 Rôles Keycloak présents

Le realm `boa-sme-mvp` déclare les rôles `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN`, `DATA_ANALYST`, `SERVICE`, `NOTIFICATION_DIGEST_READER`, `BUSINESS_ANALYST` et `RULE_APPROVER` ([`realm.json`](../infrastructure/keycloak/realm.json)). Les comptes de démonstration humains sont `rm.demo`, `branch.demo`, `admin.demo`, `analyst.demo`, `business.analyst.demo` et `rule.approver.demo`. Le fichier de realm contient des secrets de développement : ils ne doivent pas être réutilisés dans un environnement BOA.

| Persona / rôle | Périmètre déduit du code | Capacités Gateway principales | Statut |
|---|---|---|---|
| Chargé de clientèle — `RELATIONSHIP_MANAGER` | Son ou ses `relationshipManagerIds`, et la branche associée dans les services portfolio/opportunity. Le périmètre exact BOA et l’affectation active ne sont pas fournis par Keycloak seul. | Lecture commerciale de son portefeuille ; dashboard personnel ; lecture des objets autorisés ; création et mise à jour d’actions ; export portfolio ; lecture Rule Studio selon les routes explicites, mais pas écriture de règle. | **IMPLÉMENTÉ** ; correspondance BOA **À VALIDER** |
| Responsable d’agence — `BRANCH_MANAGER` | Ses `branchIds`. Le service portfolio limite le dashboard d’agence et le drill-down aux branches autorisées. | Dashboard agence, drill-down CC, lecture commerciale, actions via `COMMERCIAL_ROLES`, export portfolio. Pas de mutation de règle ni d’administration. | **IMPLÉMENTÉ** ; capacité d’écriture d’action à confirmer avec BOA |
| Administrateur — `ADMIN` | Les routes Gateway lui accordent plusieurs accès globaux. Cela ne doit pas être interprété comme un accès automatique aux données client si le service aval exige un scope. | Administration labels, notifications, synchronisation de portefeuille, pipeline/recompute, règles legacy d’administration, gouvernance ML et opérations ; lecture et écriture Rule Studio ; actions commerciales ; plusieurs lectures globales. | **IMPLÉMENTÉ** ; principe « admin sans accès client détaillé par défaut » **À VALIDER** route par route |
| Analyste données — `DATA_ANALYST` | Périmètre analytique global au niveau Gateway ; le claim BOA et les services aval doivent encore être alignés sur le dataset autorisé. | Lecture analytique, signaux, comptes, transactions, produits, modèles et règles ; gouvernance ML ; readiness/monitoring ; matérialisation des outcomes. | **IMPLÉMENTÉ** ; périmètre de données BOA **À VALIDER** |
| Auteur de règle — `BUSINESS_ANALYST` | Pas de périmètre CC/agence dans les routes Rule Studio ; périmètre de gouvernance des règles. | Lecture, création, remplacement, duplication, validation, simulation, test et soumission de règles ; lecture scoring policy. | **IMPLÉMENTÉ** |
| Approbateur de règle — `RULE_APPROVER` | Pas de périmètre CC/agence dans les routes Rule Studio ; revue indépendante d’une règle soumise. | Lecture Rule Studio ; approbation, publication, désactivation et rollback ; accès de lecture/gouvernance scoring et ML selon route. | **IMPLÉMENTÉ** |
| `SERVICE` | Identité technique issue des comptes de service. Il est accepté seulement par les familles qui incluent explicitement `SERVICE`; il ne doit pas hériter automatiquement d’un rôle humain. | Appels techniques pour analytics, signaux, ML outcomes et routes de lecture/globales selon listes de rôles ; pas d’accès automatique aux routes commerciales limitées au RM/Branch Manager. | **IMPLÉMENTÉ** ; moindre privilège et allowlist interservice **À VALIDER** |
| `NOTIFICATION_DIGEST_READER` | Uniquement le digest signé pour un `relationship_manager_id`, avec secret HMAC configuré. | Accès interne au KPI de digest signé ; ce rôle n’est pas accepté par le Gateway public pour les dashboards. | **IMPLÉMENTÉ** côté service portfolio ; chaîne complète **À VALIDER** |
| LLM | Aucun rôle humain ou compte de service dédié requis dans le realm et aucune route publique LLM recensée par le Gateway. | Aucune autorisation de décision, d’écriture ou d’import autonome. | **NON IMPLÉMENTÉ** comme acteur d’autorisation ; principe optionnel documenté |

### 4.2 Personas frontend de développement

Les personas `cc`, `agence`, `approbateur` et `backoffice` sont uniquement activées avec `VITE_AUTH_DISABLED=true`. Elles servent à rejouer les scopes locaux, pas à représenter des comptes BOA réels. `backoffice` cumule `ADMIN`, `BUSINESS_ANALYST`, `RULE_APPROVER` et `DATA_ANALYST`; cette combinaison est utile à la démo mais ne doit pas être adoptée comme séparation de tâches BOA sans validation ([`personas.ts`](../frontend/src/auth/personas.ts)).

| Persona locale | Rôles | Scope local |
|---|---|---|
| `cc` | `RELATIONSHIP_MANAGER` | `relationshipManagerIds=["rm-01"]`, `branchIds=["BR-01"]` |
| `agence` | `BRANCH_MANAGER` | `branchIds=["BR-01"]` |
| `approbateur` | `RULE_APPROVER`, `DATA_ANALYST` | `branchIds=["ALL"]` |
| `backoffice` | `ADMIN`, `BUSINESS_ANALYST`, `RULE_APPROVER`, `DATA_ANALYST` | `branchIds=["ALL"]` |

## 5. Matrice des écrans frontend

Cette table décrit les gardes d’écran, puis les routes API auxquelles l’écran fait appel. Elle ne remplace pas la matrice Gateway.

| Écran / route frontend | Garde UI observée | Rôles d’interface | API ou capacité | Statut de couverture |
|---|---|---|---|---|
| `/`, dashboard CC | `ProtectedRoute`, puis `HomeRoute` | `RELATIONSHIP_MANAGER` | `/api/v1/dashboards/me`, objets clients/opportunités/actions | Écran **IMPLÉMENTÉ** ; combinaison complète de routes **À VALIDER** |
| `/`, dashboard agence | `ProtectedRoute`, puis `HomeRoute` | `BRANCH_MANAGER` | `/api/v1/dashboards/branch` | Dashboard **IMPLÉMENTÉ** ; scope branche **PROUVÉ** par tests portfolio ciblés |
| `/agence/cc/:relationshipManagerId` | `RoleRoute(['BRANCH_MANAGER'])` | `BRANCH_MANAGER` | `/api/v1/dashboards/relationship-managers/{id}`, export portfolio | Garde UI **IMPLÉMENTÉE** ; refus API et toutes combinaisons **À VALIDER** |
| `/clients`, `/clients/:customerId` | `ProtectedRoute` seulement | Tous les utilisateurs authentifiés côté UI | clients, comptes, transactions, métriques, signaux, opportunités, actions, produits | **IMPLÉMENTÉ** côté UI ; l’autorisation réelle est Gateway/service ; certaines routes et 404 **NON COUVERTES** par test identifié |
| `/opportunites`, détail opportunité | `ProtectedRoute` | Tous authentifiés côté UI | opportunités, explications, actions | **IMPLÉMENTÉ** ; la UI ne prouve aucun droit objet |
| `/signaux` | `ProtectedRoute` | Tous authentifiés côté UI | signaux | **IMPLÉMENTÉ** ; autorisation par rôle backend |
| `/actions` | `ProtectedRoute` | Tous authentifiés côté UI | actions et métriques | **IMPLÉMENTÉ** ; différence lecture/écriture contrôlée backend |
| `/produits` | `ProtectedRoute` | Tous authentifiés côté UI | produits et catalogue | **IMPLÉMENTÉ** ; la matrice API est l’autorité |
| `/back-office` et `/back-office/regles*` | `RuleStudioRoute` | `BUSINESS_ANALYST`, `RULE_APPROVER`, `ADMIN` | Rule Studio, versions, audit, simulation, cycle de vie | Séparation auteur/approbateur **IMPLÉMENTÉE** au Gateway et dans un E2E ciblé |
| `/back-office/seuils` | `RoleRoute(['ADMIN'])` | `ADMIN` | `/api/v1/admin/engine` | Écran **IMPLÉMENTÉ** ; test de refus UI/API exhaustif **NON IDENTIFIÉ** |
| `/back-office/modeles` | `RuleStudioRoute` | Auteur, approbateur, admin | modèles ML et gouvernance | **IMPLÉMENTÉ** ; labels/performance BOA **À VALIDER** |
| `/back-office/audit` | `RuleStudioRoute` | Auteur, approbateur, admin | audit Rule Studio | **IMPLÉMENTÉ** ; couverture objet et non-divulgation **À VALIDER** |
| `/back-office/libelles` | `RoleRoute(['ADMIN'])` | `ADMIN` | lecture/mise à jour labels | **IMPLÉMENTÉ** ; tests ciblés de catalogue présents |
| `/back-office/notifications` | `RoleRoute(['ADMIN'])` | `ADMIN` | notifications et digest subscriptions | **IMPLÉMENTÉ** ; tests de rôle du digest interne, couverture Gateway complète **À VALIDER** |
| `/login`, `/interdit`, `*` | Public UI, puis page de statut | Aucun rôle pour afficher la page | Aucun accès métier | **IMPLÉMENTÉ** |

## 6. Matrice exhaustive des endpoints publics du Gateway

Les groupes ci-dessous reprennent toutes les routes déclarées dans [`gateway_api.py`](../backend/src/boa_oi/gateway_api.py). `READ_ROLES = RELATIONSHIP_MANAGER, BRANCH_MANAGER, DATA_ANALYST, BUSINESS_ANALYST, RULE_APPROVER, ADMIN, SERVICE`; `GLOBAL_ANALYTICS_ROLES = DATA_ANALYST, ADMIN, SERVICE`; `COMMERCIAL_ROLES = RELATIONSHIP_MANAGER, BRANCH_MANAGER, ADMIN, SERVICE`; `ADMIN_ROLES = ADMIN, SERVICE`; `RULE_READ_ROLES = BUSINESS_ANALYST, RULE_APPROVER, DATA_ANALYST, ADMIN`; `RULE_AUTHOR_ROLES = BUSINESS_ANALYST, ADMIN`; `RULE_APPROVER_ROLES = RULE_APPROVER, ADMIN`.

### 6.1 Lecture commerciale, données client et exports

| Méthode et endpoint | Rôles Gateway | Scope objet attendu | Statut / test identifié |
|---|---|---|---|
| `GET /api/v1/dashboards/me` | `RELATIONSHIP_MANAGER` | Affectation active du CC | **IMPLÉMENTÉ** ; tests portfolio ciblés **PROUVÉ** |
| `GET /api/v1/dashboards/branch` | `BRANCH_MANAGER` | `branchIds` | **IMPLÉMENTÉ** ; tests portfolio ciblés **PROUVÉ** |
| `GET /api/v1/dashboards/relationship-managers/{relationship_manager_id}` | `BRANCH_MANAGER` | CC appartenant à une branche autorisée | **IMPLÉMENTÉ** ; accès hors agence **PROUVÉ** sur service ciblé, route Gateway complète **À VALIDER** |
| `GET /api/v1/customers/{customer_id}/propensity` | `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN` | Client dans le portefeuille autorisé ; admin ne doit pas être supposé global | **IMPLÉMENTÉ** ; périmètre admin **À VALIDER** |
| `GET /api/v1/customers/{customer_id}/activity` | `READ_ROLES` | Client autorisé par service transaction | **IMPLÉMENTÉ** ; test de chaque rôle et 404 non identifié |
| `GET /api/v1/customers`, `GET /api/v1/customers/{customer_id}` | `READ_ROLES` | Portefeuille/branche/dataset selon principal | **IMPLÉMENTÉ** ; isolation complète **À VALIDER** |
| `GET /api/v1/customers/{customer_id}/accounts` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; test Gateway absent dans l’inventaire ciblé |
| `GET /api/v1/customers/{customer_id}/products` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; couverture 401/403/404 **NON IDENTIFIÉE** |
| `GET /api/v1/customers/{customer_id}/transactions` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; couverture complète **NON IDENTIFIÉE** |
| `GET /api/v1/customers/{customer_id}/metrics` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; couverture complète **NON IDENTIFIÉE** |
| `GET /api/v1/customers/{customer_id}/signals` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; couverture complète **NON IDENTIFIÉE** |
| `GET /api/v1/customers/{customer_id}/opportunities` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; tests opportunity ciblés, matrice complète **À VALIDER** |
| `GET /api/v1/customers/{customer_id}/actions` | `READ_ROLES` | Client autorisé | **IMPLÉMENTÉ** ; tests d’action ciblés, matrice complète **À VALIDER** |
| `GET /api/v1/opportunities` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Liste globale analytique ; ne pas extrapoler un accès commercial global | **IMPLÉMENTÉ** ; tests Gateway de rôle non identifiés |
| `GET /api/v1/opportunities/{opportunity_id}` | `READ_ROLES` | Opportunité puis client dans le scope | **IMPLÉMENTÉ** ; 404 hors scope **PROUVÉ** côté opportunity |
| `GET /api/v1/opportunities/{opportunity_id}/explanation` | `READ_ROLES` | Même scope que l’opportunité | **IMPLÉMENTÉ** ; test d’isolation complet **NON IDENTIFIÉ** |
| `GET /api/v1/opportunities/{opportunity_id}/actions` | `READ_ROLES` | Même scope que l’opportunité | **IMPLÉMENTÉ** ; test complet **NON IDENTIFIÉ** |
| `GET /api/v1/actions` | `READ_ROLES` | Filtre et scope service action | **IMPLÉMENTÉ** ; couverture complète **À VALIDER** |
| `POST /api/v1/opportunities/{opportunity_id}/actions` | `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN`, `SERVICE` | Le Gateway relit d’abord l’opportunité avec le principal appelant ; le service Action revalide ensuite le scope objet. `Idempotency-Key` est obligatoire. | **IMPLÉMENTÉ** ; lifecycle, saga et isolation ciblés **PROUVÉS**, matrice complète 401/403/404 **À VALIDER** |
| `PATCH /api/v1/actions/{action_id}` | `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `ADMIN`, `SERVICE` | Le service Action contrôle l’accès à l’action, au client et à l’opportunité avant mutation. | **IMPLÉMENTÉ** ; reprise idempotente ciblée **PROUVÉE**, toutes combinaisons de rôles **À VALIDER** |
| `GET /api/v1/accounts`, `GET /api/v1/accounts/{account_id}`, `GET /api/v1/accounts/{account_id}/balances`, `GET /api/v1/accounts/{account_id}/transactions` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Périmètre analytique/global côté Gateway ; objet account à vérifier côté service | **IMPLÉMENTÉ** ; non-divulgation par compte **À VALIDER** |
| `GET /api/v1/transactions`, `GET /api/v1/transactions/{transaction_id}` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Périmètre analytique/global côté Gateway | **IMPLÉMENTÉ** ; tests de rôle/objet non identifiés |
| `GET /api/v1/analytics/metrics` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Agrégats analytiques | **IMPLÉMENTÉ** ; KPI BOA non démontrés |
| `GET /api/v1/signals`, `GET /api/v1/signals/{signal_id}` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Agrégats/signaux analytiques | **IMPLÉMENTÉ** ; tests Gateway non identifiés |
| `GET /api/v1/products`, `GET /api/v1/products/{product_id}` | `READ_ROLES` | Catalogue produit ; objet client non implicite | **IMPLÉMENTÉ** ; tests de matrice non identifiés |
| `GET /api/v1/metrics/dashboard` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Agrégats d’actions | **IMPLÉMENTÉ** ; périmètre BOA **À VALIDER** |
| `GET /api/v1/exports/opportunities.xlsx` | `READ_ROLES` | Les données exportées doivent conserver le scope aval | **IMPLÉMENTÉ** ; export et scope complet **À VALIDER** |
| `GET /api/v1/exports/portfolio.xlsx` | `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER` | Portefeuille CC ou branche, selon query et affectation active | **IMPLÉMENTÉ** ; hors-branche `404` **PROUVÉ** côté portfolio |

### 6.2 Rule Studio et séparation Rule author / Rule approver

| Méthode et endpoint | Rôles | Capacité | Séparation et statut |
|---|---|---|---|
| `GET /api/v1/rules`, `GET /api/v1/rules/{rule_id}` | `BUSINESS_ANALYST`, `RULE_APPROVER`, `DATA_ANALYST`, `ADMIN` | Lecture des règles | **IMPLÉMENTÉ** |
| `POST /api/v1/rules`, `PUT /api/v1/rules/{rule_id}` | `BUSINESS_ANALYST`, `ADMIN` | Création/remplacement | **IMPLÉMENTÉ** |
| `GET /api/v1/rules/{rule_id}/versions`, `/history`, `/audit`, `/simulations` | `RULE_READ_ROLES` | Versions, historique, audit, simulations | **IMPLÉMENTÉ** |
| `POST /api/v1/rules/{rule_id}/duplicate`, `/validate`, `/simulate`, `/submit` | `BUSINESS_ANALYST`, `ADMIN` | Préparation et soumission | **IMPLÉMENTÉ** |
| `POST /api/v1/rules/{rule_id}/test` | `RULE_READ_ROLES` | Test en lecture/exécution de règle | **IMPLÉMENTÉ** |
| `POST /api/v1/rules/{rule_id}/approve`, `/publish`, `/disable`, `/rollback` | `RULE_APPROVER`, `ADMIN` | Approbation et opérations de cycle de vie | **IMPLÉMENTÉ** |
| Auto-approbation de l’auteur | Le backend doit refuser l’auto-approbation ; l’E2E vérifie le refus sur le flux de gouvernance | Séparation des tâches | **PROUVÉ** dans [`governance.spec.ts`](../tests/e2e/governance.spec.ts) pour le flux testé ; tous les chemins Rule Studio **À VALIDER** |
| `PATCH /api/v1/admin/rules/{rule_id}` | `ADMIN`, `SERVICE` | Mutation legacy des règles d’opportunity | **IMPLÉMENTÉ** ; route distincte du workflow Rule Studio, séparation à clarifier avec BOA |

**Point de vigilance :** l’UI `back-office` mélange plusieurs rôles dans la persona `backoffice`, tandis que l’E2E utilise un auteur et un approbateur distincts. La séparation de tâches BOA, la possibilité pour un `ADMIN` d’être auteur et approbateur et l’interdiction de cumuler ces fonctions en production sont **À VALIDER AVEC BOA**.

### 6.3 Administration et opérations

| Méthode et endpoint | Rôles | Objet / effet | Statut |
|---|---|---|---|
| `GET /api/v1/admin/rules`, `GET /api/v1/admin/engine` | `ADMIN`, `SERVICE` | Règles legacy et configuration moteur | **IMPLÉMENTÉ** |
| `GET /api/v1/labels` | `READ_ROLES` | Catalogue de libellés | **IMPLÉMENTÉ** |
| `GET /api/v1/admin/labels/{namespace}/{code}/versions`, `PUT /api/v1/admin/labels/{namespace}/{code}` | `ADMIN` | Versions et mise à jour de labels | **IMPLÉMENTÉ** ; tests de catalogue **PROUVÉ** |
| `GET /api/v1/admin/notifications`, `GET /api/v1/admin/notifications/digest-subscriptions` | `ADMIN` | Supervision notifications et abonnements | **IMPLÉMENTÉ** |
| `PUT /api/v1/admin/notifications/digest-subscriptions/{relationship_manager_id}` | `ADMIN` | Modification d’un abonnement de CC | **IMPLÉMENTÉ** ; objet et non-divulgation **À VALIDER** |
| `POST /api/v1/admin/notifications/digests/generate` | `ADMIN` | Génération des synthèses dues | **IMPLÉMENTÉ** ; refus du rôle `SERVICE` générique **PROUVÉ** côté service, refus Gateway **À VALIDER** |
| `POST /api/v1/admin/notifications/dispatch` | `ADMIN` | Envoi des notifications prêtes | **IMPLÉMENTÉ** ; SMTP local et garde-fous ciblés **PROUVÉS**, refus Gateway exhaustif **NON IDENTIFIÉ** |
| `POST /api/v1/admin/notifications/{notification_id}/retry` | `ADMIN` | Réarmement explicite d’une livraison en échec ou incertaine | **IMPLÉMENTÉ** ; contrôle de rôle Gateway présent, matrice 401/403 **À VALIDER** |
| `GET /api/v1/admin/portfolio-assignments` | `ADMIN` | Historique des affectations | **IMPLÉMENTÉ** |
| `POST /api/v1/admin/portfolio-assignments/sync` | `ADMIN` | Synchronisation des affectations | **IMPLÉMENTÉ** ; idempotence/scope **À VALIDER** |
| `POST /api/v1/admin/pipeline`, `POST /api/v1/admin/recompute` | `ADMIN`, `SERVICE` | Recalcul analytics/signaux/opportunités | **IMPLÉMENTÉ** ; absence de décision de crédit maintenue |
| `GET/POST /api/v1/admin/scoring-policies[/{subpath}]` | `RULE_READ_ROLES` | Gouvernance de scoring policy | **IMPLÉMENTÉ** ; le code Gateway est large et délègue le détail au service |
| `GET/POST /api/v1/admin/ml/governance[/{subpath}]` | Gateway : `DATA_ANALYST`, `RULE_APPROVER`, `ADMIN`; service aval : auteur/évaluation/approbateur/release selon opération | Gouvernance ML | **IMPLÉMENTÉ** ; `evaluation/labels` et `evaluation/metrics` refusent les rôles commerciaux et exigent `DATA_ANALYST`/`ADMIN` (`SERVICE` interne seulement) |
| `POST /api/v1/admin/ml/outcomes/materialize` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Matérialisation d’outcomes | **IMPLÉMENTÉ** |
| `GET /api/v1/admin/ml/outcomes/snapshots`, `GET/POST /api/v1/admin/ml/datasets/manifests` | `DATA_ANALYST`, `ADMIN`, `SERVICE` | Labels candidats et manifests point-in-time | **IMPLÉMENTÉ** ; `RELATIONSHIP_MANAGER` refusé côté service |
| `GET /api/v1/admin/readiness` | `DATA_ANALYST`, `ADMIN` | Readiness de plateforme/ML | **IMPLÉMENTÉ** ; seuils de passage BOA **À VALIDER** |
| `GET/POST /api/v1/admin/monitoring/{subpath}` | `DATA_ANALYST`, `ADMIN` | Observations et monitoring | **IMPLÉMENTÉ** ; couverture d’autorisation **NON IDENTIFIÉE** |

## 7. Endpoints backend internes et comptes de service

Les services exposent des routes `/internal/v1/...` protégées par des rôles techniques ou métier. Le Gateway relaie l’autorisation et l’identité vers les services. La liste complète des routes backend est répartie dans [`customer_api.py`](../backend/src/boa_oi/customer_api.py), [`portfolio_api.py`](../backend/src/boa_oi/portfolio_api.py), [`opportunity_api.py`](../backend/src/boa_oi/opportunity_api.py), [`action_api.py`](../backend/src/boa_oi/action_api.py), [`analytics_api.py`](../backend/src/boa_oi/analytics_api.py), [`signal_api.py`](../backend/src/boa_oi/signal_api.py), [`transaction_api.py`](../backend/src/boa_oi/transaction_api.py), [`account_api.py`](../backend/src/boa_oi/account_api.py), [`product_api.py`](../backend/src/boa_oi/product_api.py), [`rule_management_api.py`](../backend/src/boa_oi/rule_management_api.py), [`rule_simulation_api.py`](../backend/src/boa_oi/rule_simulation_api.py), [`ml_engine_api.py`](../backend/src/boa_oi/ml_engine_api.py) et [`scoring_policy/routes.py`](../backend/src/boa_oi/scoring_policy/routes.py).

| Famille interne | Contrôle observé | Risque ou point ouvert |
|---|---|---|
| Customer, opportunity, action, portfolio | `current_principal`, rôles et filtres par `relationshipManagerIds` ou `branchIds`; objet absent du scope renvoyé en `404` dans les chemins testés. | La couverture systématique de chaque route et de chaque combinaison de rôle n’est pas démontrée. |
| Analytics, signals, feature store, ML | Rôles `DATA_ANALYST`, `ADMIN`, `SERVICE` selon l’opération ; score et matérialisation restent des fonctions techniques et de gouvernance. | Le périmètre analytique BOA, le dataset approuvé et le mode shadow sont **À VALIDER AVEC BOA**. |
| Rule management/simulation | Author/approver séparés par constantes et transitions. | Le contrôle d’auto-approbation doit être vérifié pour toutes les transitions, pas seulement l’E2E identifié. |
| Notification digest | `NOTIFICATION_DIGEST_READER` plus signature HMAC et `relationship_manager_id`; un `SERVICE` générique est refusé par le test ciblé. | Secret, rotation et attribution BOA **À VALIDER**. |
| Operations `/health`, `/ready`, `/metrics` | Créées par `create_service_app`; aucune dépendance de rôle dans `platform.py`. | Exposition réseau et authentification des métriques/health en déploiement **À VALIDER**. |

Le realm Keycloak déclare le client public `boa-sme-spa`, le client API `boa-sme-api`, puis des clients confidentiels avec comptes de service : `api-gateway`, `pipeline-runner`, `customer-service`, `account-service`, `transaction-service`, `banking-integration-service`, `analytics-service`, `signal-service`, `opportunity-service`, `product-service`, `action-service`, `rule-management-service`, `rule-engine-service`, `rule-simulation-service`, `feature-store-service`, `ml-engine-service`, `portfolio-service` et `notification-service`. Les comptes techniques portent principalement `SERVICE`; `notification-service` porte `NOTIFICATION_DIGEST_READER` ([`realm.json`](../infrastructure/keycloak/realm.json)). La séparation de secrets, la rotation, l’audience et les permissions effectives du client Keycloak sont **À VALIDER AVEC BOA**.

## 8. Réponses 401, 403 et 404

| Situation | Réponse attendue dans le code | Interprétation |
|---|---|---|
| Pas de bearer lorsque OIDC est actif | `401 AUTHENTICATION_REQUIRED` | L’identité n’est pas établie. |
| Token expiré | `401 TOKEN_EXPIRED` | Le client doit renouveler la session ou se reconnecter. |
| Signature, issuer, audience ou claims invalides | `401 AUTHENTICATION_REQUIRED` | Le token ne doit pas être accepté sur la seule base de l’UI. |
| Token valide mais rôle absent | `403 FORBIDDEN` | L’identité est connue, la capacité est refusée. |
| Scope de portefeuille absent pour un rôle commercial | `403 PORTFOLIO_SCOPE_MISSING` ou équivalent service | Un rôle sans scope objet ne donne pas accès par défaut. |
| Objet inconnu ou hors périmètre | `404 RESOURCE_NOT_FOUND` dans les services observés | Le dépôt utilise le 404 pour ne pas révéler un objet hors scope, mais la généralisation est **À VALIDER**. |
| Route frontend inconnue | Page `/` `NotFoundPage`; cela ne préjuge pas du status HTTP Gateway. | UI uniquement. |
| Réponse d’erreur | Payload avec `type`, `title`, `status`, `code`, `message`, `correlationId`, `timestamp`, `details`. | **IMPLÉMENTÉ** dans [`platform.py`](../backend/src/boa_oi/platform.py). |

Les tests ciblés montrent des `404` pour un client/opportunité/portefeuille hors périmètre et un `403` pour un digest avec mauvais rôle ou signature ([`test_portfolio_assignments.py`](../tests/unit/test_portfolio_assignments.py), [`test_opportunity_filters.py`](../tests/unit/test_opportunity_filters.py)). En revanche, une campagne exhaustive de chaque route Gateway avec absence de token, rôle incorrect, scope incorrect, objet inconnu et objet hors scope n’est pas présente dans le dépôt : **NON IMPLÉMENTÉ / À VALIDER**.

## 9. Routes et capacités non couvertes par un test identifié

La présence d’une route dans le code ne vaut pas preuve de test. À la lecture de l’inventaire `tests/`, les lacunes suivantes doivent être traitées avant une décision de passage :

1. La matrice complète Gateway n’est pas exécutée pour tous les rôles humains, `SERVICE` et `NOTIFICATION_DIGEST_READER`.
2. Les routes `accounts`, `transactions`, `signals`, `products`, `labels`, `notifications`, `monitoring`, `readiness`, `scoring-policies` et `ml/governance` n’ont pas chacune un triplet de tests `401/403/404` identifié.
3. Les routes de scope client `customers/{customer_id}/activity`, `metrics`, `signals`, `opportunities`, `actions`, `products`, `accounts` et `transactions` n’ont pas chacune une preuve d’isolation objet complète au niveau Gateway.
4. Les exports `opportunities.xlsx` et `portfolio.xlsx` n’ont pas une matrice complète par rôle, query, branche, CC et objet hors périmètre ; le test existant couvre surtout le flux portfolio ciblé.
5. La route legacy `PATCH /api/v1/admin/rules/{rule_id}` coexiste avec Rule Studio ; la gouvernance, l’audit et la séparation des tâches entre ces chemins ne sont pas prouvés ensemble.
6. L’auto-approbation est vérifiée dans des flux E2E de gouvernance, mais la preuve ne couvre pas nécessairement toutes les transitions Rule Studio et Scoring Policy.
7. Le mode `BOA_AUTH_DISABLED=true` crée un principal local très privilégié sans header persona ; ce chemin ne doit pas être confondu avec un test OIDC Keycloak.
8. Les routes de santé, readiness et métriques ne sont pas documentées ici comme endpoints publics Gateway ; leur exposition opérationnelle et leur authentification sont **À VALIDER AVEC BOA**.
9. Aucun test ne démontre une configuration Keycloak BOA réelle, une rotation de secrets, une audience de production, une révocation observée ou un comportement avec claims BOA signés par l’infrastructure BOA.
10. Aucun résultat de charge, de volumétrie de production ou de KPI de sécurité n’est produit par cette matrice. Toute valeur cible est **HYPOTHÈSE À VALIDER AVEC BOA**.

## 10. Plan de validation BOA requis

Avant toute mise en staging ou en production, BOA doit valider la liste des personas, les affectations CC/agence, le périmètre des analystes et administrateurs, la séparation Rule author/Rule approver, la présence éventuelle de rôles supplémentaires, le traitement des comptes de service, la politique `401/403/404`, l’exposition des endpoints opérationnels et la conservation de l’audit. Ces éléments ne sont pas démontrés par les seules routes frontend.

Une campagne reproductible doit exécuter la matrice sur chaque endpoint public Gateway et sur les services internes accessibles par les comptes techniques. Elle doit vérifier le refus sans token, le refus avec rôle insuffisant, le refus ou `404` pour un objet hors scope, l’accès autorisé avec scope correct, l’absence de fuite par pagination/export/filtre et la séparation de tâches sur chaque transition. Le nombre de cas, la durée, les seuils, le volume de données et le niveau de couverture sont **HYPOTHÈSE À VALIDER AVEC BOA**.

Le ML doit rester **CPU-only**, **POC/shadow**, sans décision de crédit et sans dépendance LLM/GPU tant que BOA n’a pas fourni des labels matures et validé les critères de gouvernance. Aucune performance, précision, coût ou seuil de production n’est affirmé dans ce document.

## Références

[1]: ../backend/src/boa_oi/gateway_api.py "Gateway API, routes publiques, rôles et proxys"
[2]: ../backend/src/boa_oi/platform.py "Authentification OIDC, principal, rôles, scopes et erreurs"
[3]: ../infrastructure/keycloak/realm.json "Realm Keycloak, clients, rôles et comptes de service"
[4]: ../frontend/src/App.tsx "Routage frontend et gardes d’écran"
[5]: ../frontend/src/auth/ProtectedRoute.tsx "Protections frontend par authentification et rôle"
[6]: ../frontend/src/auth/personas.ts "Personas de développement et scopes locaux"
[7]: ../frontend/src/api/hooks.ts "Hooks frontend et endpoints Gateway consommés"
[8]: ../frontend/src/api/ruleStudioHooks.ts "Hooks frontend Rule Studio et cycle de vie"
[9]: ../backend/src/boa_oi/portfolio_api.py "Dashboards, exports et scopes CC/agence"
[10]: ../backend/src/boa_oi/opportunity_api.py "Opportunités, scope objet et transitions"
[11]: ../backend/src/boa_oi/action_api.py "Actions commerciales et contrôles de rôle"
[12]: ../tests/unit/test_platform_auth_roles.py "Tests unitaires d’authentification et rôles"
[13]: ../tests/unit/test_portfolio_assignments.py "Tests de scopes portfolio, exports et digest"
[14]: ../tests/unit/test_opportunity_filters.py "Tests de filtrage et isolation des opportunités"
[15]: ../tests/e2e/governance.spec.ts "Tests E2E de gouvernance ML et séparation d’approbation"
[16]: workstreams/fallback-rules-only.md "Résilience ML CPU-only et secours rules-only"
[17]: workstreams/mlops-governance.md "Maturité des labels et gouvernance ML"
[18]: rule-studio.md "Rule Studio, workflow humain et LLM optionnel hors décision"
[19]: ../docs/test-plan.md "Plan de tests RBAC, isolation, intégration et E2E"
[20]: audit/workstreams/repository-docs.md "État des preuves de tests et artefacts présents"

*Document rédigé à partir de la lecture statique du dépôt. Aucun fichier applicatif n’a été modifié.*
