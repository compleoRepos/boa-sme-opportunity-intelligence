# Audit en lecture seule — backend Opportunity Intelligence

**Dépôt audité :** `/home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence`
**Périmètre :** routes et contrats, filtres Opportunity, pipeline analytique, idempotence/incrémentalité, historique des rattachements, cycle de vie/cooldown/expiration, audit métier, actions/outcomes et tests.
**Mode :** lecture seule ; aucun fichier de code n’a été modifié. Les constats ci-dessous sont fondés sur le code, la documentation du dépôt et les commandes exécutées.

## Synthèse

Le backend possède une base fonctionnelle cohérente pour le MVP : les routes sont séparées par service, les contrats Pydantic/FastAPI couvrent les principaux cas d’usage, la génération Opportunity est déterministe et dédupliquée par clé, l’explication et la décision auditable sont persistées, et les actions disposent d’une idempotence par clé de requête ainsi que d’une table d’outcomes. La suite de tests passe lorsqu’elle est lancée avec le chemin Python du dépôt.

Les points les plus fragiles sont toutefois structurants. Plusieurs filtres annoncés comme acceptés par `GET /opportunities` sont silencieusement ignorés ; le contrôle de périmètre utilisateur n’est pas visible dans le service Opportunity ; le recalcul analytique relit et recalcule une fenêtre complète au lieu de consommer un watermark événementiel ; l’idempotency key du pipeline sert à fabriquer un `jobId` mais ne provoque pas de court-circuit d’exécution ; et le compteur de génération Opportunity est incrémenté même lorsqu’un `ON CONFLICT DO NOTHING` n’insère rien. Enfin, le cycle de vie Opportunity reste essentiellement déclaratif (`status` stocké et filtrable) : aucune transition métier, expiration, cooldown ou historique de rattachement Opportunity/RM n’est implémenté dans les modules audités.

## 1. Ce qui fonctionne

### Routes et contrats de base

Les services exposent des applications FastAPI distinctes et le gateway mappe les routes publiques vers les services internes. Le service Opportunity déclare les lectures de liste, de détail, d’explication, de liste par client, la génération interne et les routes d’administration des règles et du moteur (`backend/src/boa_oi/opportunity_api.py:253-297`, `:631-963`). Les actions disposent de listes globales, par Opportunity et par client, d’une création et d’une mise à jour (`backend/src/boa_oi/action_api.py:204-406`). Le gateway expose notamment les routes publiques d’actions et de détail Opportunity (`backend/src/boa_oi/gateway_api.py:163-168`, `:497-535`).

La pagination est encodée par curseur, avec `pageSize`, `nextCursor`, `hasMore`, liens et `correlationId` (`backend/src/boa_oi/opportunity_api.py:275-298`). Les filtres inconnus sont rejetés explicitement avec `400 UNKNOWN_FILTER` (`backend/src/boa_oi/opportunity_api.py:301-317`). Le tri Opportunity est borné à `priorityScore`, `confidence`, `generatedAt` et `opportunityType`, avec un identifiant comme tie-breaker (`backend/src/boa_oi/opportunity_api.py:228-242`).

### Modèle et génération Opportunity

Le modèle persistant impose une clé Opportunity unique, une clé de déduplication unique et des bornes SQL pour confiance et priorité (`backend/src/boa_oi/models/entities.py:321-366`). Les preuves sont également contraintes par position pour une Opportunity (`backend/src/boa_oi/models/entities.py:369-383`). Le moteur produit des candidats déterministes à partir du client, type, date d’observation, version du moteur et version de règle (`backend/src/boa_oi/opportunities/service.py:49-114`). Les gardes de qualité exigent notamment `data_quality == VALID`, une couverture minimale de règle, l’ajustement saisonnier et l’absence de drapeaux faux positifs (`backend/src/boa_oi/opportunities/strategies.py:27-41`).

La génération persiste l’explication, les versions, les poids, le mode de fallback, les preuves, la décision et un hash de décision ; la décision conserve métriques, signaux, composants de confiance/priorité, politique de scoring et cause de fallback (`backend/src/boa_oi/opportunity_api.py:813-943`, `backend/src/boa_oi/models/entities.py:469-486`). La documentation prévoit que les décisions historiques ne soient pas réinjectées et qu’un rerun identique soit idempotent par clé de déduplication ; la contrainte unique et l’`ON CONFLICT` fournissent une partie de ce comportement (`docs/data-model.md:230-242`).

### Pipeline analytique et métriques

Les fenêtres supportées sont contrôlées dans le service analytique ; le moteur calcule les métriques, la couverture, la qualité et les comparaisons historiques. Les tests unitaires couvrent les fenêtres `7D`, `30D`, `90D`, `180D`, `365D`, les exclusions de transactions, les variations, la faible baseline, la couverture partielle et la saisonnalité (`tests/unit/test_analytics.py:36-118`).

Les snapshots sont upsertés sur `(customer_id, as_of_date, window_days, calculation_version)` et le modèle possède une contrainte d’unicité correspondante (`backend/src/boa_oi/analytics_api.py:307-332`, `backend/src/boa_oi/models/entities.py:230-244`). Les endpoints de lecture permettent de filtrer par client, métrique et période (`backend/src/boa_oi/analytics_api.py:87-177`).

### Actions, outcomes et idempotence de création

Le contrat d’action borne les types d’action et d’outcome (`backend/src/boa_oi/action_api.py:30-67`). La création vérifie l’existence de l’Opportunity auprès du service Opportunity, vérifie la cohérence `customerId`, et applique une règle minimale empêchant `MARK_CONVERTED` sans engagement préalable (`backend/src/boa_oi/action_api.py:271-319`). La clé `Idempotency-Key` est persistée avec un hash du corps ; une réutilisation avec un corps différent renvoie `409 IDEMPOTENCY_KEY_REUSED` (`backend/src/boa_oi/action_api.py:274-289`). Les outcomes de création sont écrits dans `action.action_outcomes` (`backend/src/boa_oi/action_api.py:320-359`, `backend/src/boa_oi/models/entities.py:433-447`).

### Tests observés

La commande de référence exécutée avec le chemin du dépôt est :

```bash
PYTHONPATH=backend/src:. pytest -q
```

Résultat observé : **119 tests passés, 6 warnings**, en environ 8,5 secondes. La couverture inclut Opportunity, analytics, opérations, résilience, actions, règles, scoring, signaux, APIs et seed. La commande ciblée sans module seed a également passé 114 tests :

```bash
pytest -q tests/unit --ignore=tests/unit/test_models_seed_api.py
```

## 2. Ce qui est fragile

### Filtres Opportunity acceptés mais ignorés

`list_for()` annonce notamment `sector`, `customerSegment` et `relationshipManagerId` comme filtres autorisés (`backend/src/boa_oi/opportunity_api.py:185-194`), mais le corps n’applique effectivement que `customerId`, `type/opportunityType`, `minConfidence`, `maxConfidence`, `priorityLevel`, `horizon`, `status`, `fromDate` et `toDate` (`backend/src/boa_oi/opportunity_api.py:200-227`). Les trois filtres acceptés mais non utilisés ne provoquent donc pas d’erreur et peuvent donner une réponse non filtrée, ce qui est plus dangereux qu’un rejet explicite.

Le service Opportunity ne reçoit pas de `Principal` dans les endpoints de lecture ; la dépendance de rôle est présente, mais aucun filtrage par agence, portefeuille ou relationship manager n’est visible dans `list_opportunities`, `customer_opportunities`, `get_opportunity` ou `get_explanation` (`backend/src/boa_oi/opportunity_api.py:253-297`). Le filtrage de scope existe dans d’autres services, par exemple portefeuille (`backend/src/boa_oi/portfolio_api.py:54-96`), mais cette protection n’est pas démontrée pour les lectures Opportunity directes.

### Recalcul analytique non incrémental malgré un champ nommé watermark

`recompute_one()` relit les transactions et soldes sur environ 730 jours pour chaque client, puis recalcule l’historique de fenêtres et le snapshot courant (`backend/src/boa_oi/analytics_api.py:194-305`). Le champ `input_watermark` est construit avec le nombre de transactions et de soldes (`:317-319`, `:328-330`) ; ce n’est pas un watermark monotone d’événement, de date ou d’identifiant source. Aucun test ne montre un traitement « nouveaux événements seulement », un checkpoint consommé ou un skip lorsque le watermark est inchangé.

L’endpoint est déclaré `202 Accepted`, mais exécute la boucle de calcul avant de répondre avec `status: COMPLETED` (`backend/src/boa_oi/analytics_api.py:338-361`). L’`Idempotency-Key` sert uniquement à dériver un `jobId` déterministe ; aucun enregistrement de job ou mécanisme de réutilisation du résultat n’est consulté. Le comportement est donc déterministe et rejouable, mais pas un pipeline incrémental/asynchrone au sens opérationnel.

### Déduplication et résultat de génération Opportunity

La clé de déduplication est composée du client, du type, de `asOf` et de la version de règle (`backend/src/boa_oi/opportunity_api.py:842-847`). Elle protège le rerun exact mais permet une nouvelle ligne à chaque date d’observation ou version de règle, sans logique de suppression liée à une action déjà acceptée/rejetée. Surtout, l’écriture utilise `ON CONFLICT DO NOTHING`, puis `generated` est incrémenté sans vérifier si l’insertion a réellement créé une ligne (`backend/src/boa_oi/opportunity_api.py:849-901`, `:923-945`). Un rerun idempotent peut donc renvoyer un nombre d’Opportunities générées supérieur au nombre effectivement inséré.

Le contexte Opportunity classe la qualité comme `VALID` dès que la couverture minimale calculée sur les métriques 90D atteint `0,83` (`backend/src/boa_oi/opportunity_api.py` dans `context_for`, notamment la construction de `quality` et `data_quality`). Cette règle n’est pas équivalente à une preuve d’historique disponible d’au moins 90 jours. La documentation métier demande de bloquer la création lorsque l’historique minimal n’est pas disponible (`docs/business-rules.md:80`, `:313-354`) ; cette garantie n’est pas démontrée par le chemin de génération audité.

### Actions : workflow incomplet et dashboard borné

Le prérequis de conversion est utile, mais `UpdateAction.status` est un `str` libre et ne valide pas une machine d’états (`backend/src/boa_oi/action_api.py:53-67`, `:368-406`). Une mise à jour d’outcome force `COMPLETED` et ajoute un nouvel `ActionOutcome`; elle ne vérifie pas la transition précédente et la clé déterministe inclut l’heure courante (`:386-403`), ce qui autorise des répétitions d’un même outcome sans idempotence de mise à jour.

La création et la mise à jour d’action ne modifient pas `Opportunity.status`. Les actions constituent donc un journal parallèle, mais ne font pas progresser l’état de l’Opportunity. Le dashboard charge au maximum 1 000 Opportunities via une seule requête (`backend/src/boa_oi/action_api.py:414-423`) et calcule les ratios à partir de cette tranche, alors que les actions sont lues sans pagination (`:423-471`). Les indicateurs peuvent être incomplets au-delà de cette borne.

### Audit métier partiel

La décision analytique est bien structurée et persistée (`DecisionAudit`), et le fallback ML est écrit dans l’audit Opportunity (`backend/src/boa_oi/opportunity_api.py:903-943`). En revanche, la table générique `audit.audit_logs` existe (`backend/src/boa_oi/models/entities.py:449-467`) mais les routes d’action ne l’alimentent pas lors des créations, changements de statut, outcomes ou notes (`backend/src/boa_oi/action_api.py:271-406`). La traçabilité action/outcome repose sur les tables d’action, sans événement métier avant/après ni journal de transition explicite.

## 3. Ce qui manque

### Cycle de vie Opportunity

Le modèle contient `status` mais aucun `CheckConstraint` ou enum de domaine n’est visible pour les états Opportunity (`backend/src/boa_oi/models/entities.py:321-366`). Aucun endpoint de transition Opportunity n’apparaît dans `opportunity_api.py` : les routes sont lectures, génération, règles et informations moteur (`backend/src/boa_oi/opportunity_api.py:253-297`, `:631-963`). Il manque au minimum un contrat de transition, les acteurs, la date, la raison et les contrôles de concurrence.

### Cooldown et expiration

Aucun champ `cooldown`, `expires_at`, `expired_at`, `last_action_at` ou équivalent n’est présent dans le modèle Opportunity (`backend/src/boa_oi/models/entities.py:321-366`). Aucune route ou tâche d’expiration/cooldown n’est repérée dans les modules Opportunity, action ou modèles. La documentation expose pourtant `lastActionAt` dans l’exemple Opportunity (`docs/api.md:380-410`) et décrit des données d’affectation avec dates de validité et expiration de projection (`docs/data-model.md:291-293`). Ces éléments ne sont pas matérialisés dans le périmètre audité.

### Historique des rattachements

Le modèle Opportunity ne porte qu’un `customer_id`/`customer_ref`, et le modèle Action porte `assigned_to` sans table d’historique d’affectation (`backend/src/boa_oi/models/entities.py:336-342`, `:403-427`). La recherche ciblée ne trouve pas de modèle `OpportunityAssignment`, de période de validité, de route de rattachement ou d’événement de réaffectation dans le backend. Les affectations de portefeuille/client et les scopes RM existent dans d’autres parties du dépôt, mais elles ne fournissent pas un historique des rattachements d’une Opportunity et ne sont pas reliées aux lectures Opportunity auditées.

### Contrats et tests manquants

Il manque des tests négatifs explicites pour : les filtres acceptés mais ignorés (`sector`, `customerSegment`, `relationshipManagerId`), les scopes RM/agence sur `GET /opportunities`, les dates et décimaux malformés, les transitions de statut Opportunity, cooldown/expiration, changement de rattachement, rerun du pipeline avec même Idempotency-Key, conflit de déduplication et exactitude du compteur `generated`.

Le lancement brut depuis la racine :

```bash
pytest -q
```

échoue lors de la collecte de `tests/unit/test_models_seed_api.py` avec `ModuleNotFoundError: No module named 'database'`. Le module existe bien sous `./database`, et le lancement avec `PYTHONPATH=backend/src:.` passe les 119 tests. Cela indique une fragilité de configuration/reproductibilité de la commande de test par défaut, même si le code testé passe avec le chemin explicite.

La génération OpenAPI produit également six warnings d’Operation ID dupliqué dans `gateway_api.py` lors des tests (`scoring_policy_governance`, `ml_governance`, `monitoring_governance`), signalés par FastAPI. Ils ne font pas échouer les tests mais fragilisent la qualité du contrat OpenAPI généré.

## 4. Conclusion d’audit

**Fonctionnel aujourd’hui :** socle FastAPI multi-services, contrats principaux, pagination/correlation, règles Opportunity déterministes, preuves/explication/décision auditée, snapshots analytiques upsertés, actions idempotentes à la création, outcomes persistés et 119 tests passants avec la configuration Python explicite.

**Fragile :** filtres déclarés mais ignorés, scope Opportunity non démontré, recalcul analytique complet présenté comme job `202`, idempotence de pipeline incomplète, compteur de génération non corrélé aux insertions, seuil d’historique indirect, workflow d’action partiellement contrôlé, dashboard tronqué à 1 000 lignes et warnings OpenAPI.

**Manquant :** cycle de vie Opportunity réellement transitionnel, cooldown, expiration, last-action matérialisé, historique des rattachements Opportunity/RM, audit métier avant/après des actions et tests de non-régression correspondants.

Les nombres de tests et les résultats indiqués ici proviennent des commandes exécutées pendant l’audit ; aucun chiffre externe ou fourni par avance n’a été repris sans vérification.

## Preuves principales

| Sujet | Preuve |
|---|---|
| Routes et filtres | `backend/src/boa_oi/opportunity_api.py:185-242`, `:253-297` |
| Modèle Opportunity/déduplication | `backend/src/boa_oi/models/entities.py:321-366` |
| Génération et compteur | `backend/src/boa_oi/opportunity_api.py:813-943` |
| Pipeline analytique | `backend/src/boa_oi/analytics_api.py:194-335`, `:338-378` |
| Actions/outcomes | `backend/src/boa_oi/action_api.py:271-406`; `backend/src/boa_oi/models/entities.py:403-447` |
| Audit décision | `backend/src/boa_oi/models/entities.py:449-486`; `backend/src/boa_oi/opportunity_api.py:903-943` |
| Attentes métier/documentation | `docs/data-model.md:230-242`, `:291-293`; `docs/business-rules.md:80`, `:313-354`; `docs/api.md:380-410`, `:430-494` |
| Tests exécutés | `PYTHONPATH=backend/src:. pytest -q` → 119 passed, 6 warnings |
| Échec de commande par défaut | `pytest -q` → erreur de collecte `ModuleNotFoundError: No module named 'database'` |

---

**Verdict :** le backend est exploitable comme socle MVP déterministe et testé, mais il ne faut pas le considérer comme couvrant déjà un cycle de vie Opportunity complet ni un pipeline analytique incrémental gouverné. Les écarts les plus prioritaires sont la correction/rejet des filtres inopérants et des scopes, la matérialisation du lifecycle/cooldown/expiration/rattachement, puis la vraie sémantique de watermark/idempotence et l’audit des transitions métier.
