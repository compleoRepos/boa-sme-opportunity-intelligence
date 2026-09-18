# Rule Engine & Rule Studio — acceptation exécutable

**Produit :** BOA SME Opportunity Intelligence  
**Module :** Rule Engine & Rule Studio  
**Version du document :** 1.0.0  
**Statut actuel :** `NOT_RUN` pour les dix-sept critères  
**Auteur :** Manus AI  
**Spécification normative :** [`rule-studio.md`](./rule-studio.md) [1]

> Ce document est une checklist de preuve. Il ne déclare aucune fonctionnalité `PASS`. Une spécification, une présence de fichier ou une revue statique ne constitue pas un run. Un critère passe uniquement si les preuves backend, API et PostgreSQL demandées sont produites par une exécution horodatée.

## 1. Protocole de verdict

Les seuls statuts autorisés sont :

| Statut | Signification |
|---|---|
| `NOT_RUN` | aucune exécution admissible n’a été fournie ; statut initial de chaque critère |
| `PASS` | toutes les assertions bloquantes ont réussi et les artefacts exigés sont disponibles |
| `FAIL` | au moins une assertion bloquante a échoué ou une preuve contredit le résultat attendu |
| `BLOCKED` | l’environnement ou une dépendance empêche l’exécution ; le blocage est documenté |
| `NOT_APPLICABLE` | autorisé uniquement pour une sous-preuve conditionnelle, jamais pour l’un des dix-sept critères obligatoires |

Un critère ne peut pas être `PASS` si une preuve obligatoire manque, si un test a été ignoré, si l’UI utilise une fixture locale, si PostgreSQL est remplacé par un repository mock, ou si le rapport n’identifie pas le build et la version de règle. Les dix-sept critères sont obligatoires et cumulatifs.

## 2. Enveloppe de preuve du run

Chaque run d’acceptation doit produire un manifeste contenant :

```json
{
  "runId": "rule-studio-acceptance-<UTC>",
  "startedAt": "RFC3339 UTC",
  "completedAt": "RFC3339 UTC",
  "gitCommit": "commit ou worktree hash identifié",
  "workingTreeDirty": true,
  "serviceImages": {},
  "postgresVersion": "version observée",
  "seedId": "seed observé",
  "ruleEngineVersion": "version observée",
  "analyticsVersion": "version observée",
  "environment": {
    "cpu": "ressources allouées",
    "memory": "ressources allouées"
  },
  "correlationId": "identifiant du parcours",
  "criteria": [
    {"id":"RS-AC-01","status":"NOT_RUN","evidence":[]}
  ]
}
```

Le rapport conserve au minimum : logs Docker Compose, readiness, résultats de migrations, appels HTTP redigés, réponses JSON, extraits SQL en lecture seule, captures Rule Studio, résultats de tests, métriques de performance et `EXPLAIN (ANALYZE, BUFFERS)`. Les secrets et tokens sont masqués.

## 3. Préconditions bloquantes

Avant d’évaluer RS-AC-01, le run doit prouver que :

1. PostgreSQL réel est prêt et sa version est enregistrée ;
2. `rule-management-service`, `rule-engine-service` et `rule-simulation-service` sont `ready` ;
3. les migrations des huit tables sont appliquées sur une base vide ;
4. le Gateway et l’identité OIDC sont actifs pour `BUSINESS_ANALYST`, `RULE_APPROVER` et `ADMIN` avec au moins deux sujets humains distincts ;
5. Analytics contient des métriques historiques pré-calculées provenant du pipeline de données ;
6. Customer et Product exposent les référentiels nécessaires ;
7. le frontend n’a aucun fallback de données métier statiques ;
8. le run commence avec un identifiant de règle de test absent ou un namespace isolé.

Si l’une de ces préconditions échoue, les critères concernés sont `BLOCKED` ou `FAIL`, jamais `PASS`.

## 4. Checklist exacte des dix-sept critères d’acceptation

Les libellés des dix-sept critères reprennent exactement les capacités exigées par le cahier du module [2]. Les identifiants et preuves ci-dessous les rendent exécutables.

### RS-AC-01 — créer une règle

**Capacité exacte :** « créer une règle ».

**Précondition :** utilisateur `BUSINESS_ANALYST` authentifié ; `ruleId` absent.

**Procédure :** créer une règle depuis le Rule Studio avec nom, description et périmètre, puis interroger `GET /api/v1/rules/{ruleId}`.

**Assertions bloquantes :** la création retourne `201`; la version 1 est `DRAFT`; `rules` et `rule_versions` contiennent une ligne cohérente ; `rule_audit_logs` contient `CREATED` avec le même sujet et le même `correlationId`; aucune opportunité n’est créée.

**Preuves obligatoires :** capture UI, requête/réponse API, extrait SQL des deux tables et de l’audit.

**Statut initial :** `NOT_RUN`.

### RS-AC-02 — sélectionner ses métriques

**Capacité exacte :** « sélectionner ses métriques ».

**Précondition :** règle `DRAFT` ; registre Analytics disponible.

**Procédure :** sélectionner au moins `INFLOW_GROWTH`, `SUPPLIER_PAYMENT_GROWTH` et `TRANSACTION_VOLUME_GROWTH` dans les composants no-code.

**Assertions bloquantes :** seules des métriques actives et typées du registre sont proposées ; les `nodeId` sont uniques ; les choix sont persistés dans `definition_json` et matérialisés dans `rule_conditions`; une métrique inconnue soumise directement à l’API retourne `422 METRIC_NOT_REGISTERED`.

**Preuves obligatoires :** capture des sélecteurs, réponse GET, SQL `rule_conditions`, test négatif API.

**Statut initial :** `NOT_RUN`.

### RS-AC-03 — sélectionner ses opérateurs

**Capacité exacte :** « sélectionner ses opérateurs ».

**Précondition :** métriques sélectionnées.

**Procédure :** construire des cas couvrant `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`, `EQUALS`, `NOT_EQUALS`, `BETWEEN`, `IN`, `NOT_IN`, `INCREASE_BY`, `DECREASE_BY` et `PERSISTENT_FOR`; construire des groupes `AND`, `OR`, `NOT` imbriqués.

**Assertions bloquantes :** les douze opérateurs de comparaison/persistance et trois opérateurs logiques sont acceptés selon leur contrat ; `NOT` a exactement un enfant ; les incompatibilités type/opérateur sont refusées ; un arbre imbriqué produit la table de vérité documentée, y compris `UNKNOWN`.

**Preuves obligatoires :** résultats de tests paramétrés, payloads de contrat, traces d’évaluation de l’arbre imbriqué.

**Statut initial :** `NOT_RUN`.

### RS-AC-04 — définir ses seuils

**Capacité exacte :** « définir ses seuils ».

**Précondition :** conditions valides.

**Procédure :** saisir des seuils numériques, un intervalle, un ensemble et une persistance ; valider les unités et frontières.

**Assertions bloquantes :** `25 %` est sérialisé en `0.25`; les comparaisons strictes et inclusives sont distinguées à la frontière ; `BETWEEN` refuse `lower > upper`; les unités incompatibles sont rejetées ; aucun seuil métier n’est requis comme constante du frontend ou du moteur.

**Preuves obligatoires :** payload GET, tests de frontière, erreur de validation, inspection de configuration active.

**Statut initial :** `NOT_RUN`.

### RS-AC-05 — sélectionner l’opportunité

**Capacité exacte :** « sélectionner l’opportunité ».

**Précondition :** Product Service et registre d’opportunités disponibles.

**Procédure :** sélectionner `opportunityType`, produits référencés et horizon.

**Assertions bloquantes :** le type et les `productRefs` sont résolus par les services propriétaires ; `rule_actions` contient uniquement des références et non une copie du produit ; une référence inactive/inconnue retourne `422 PRODUCT_REFERENCE_INVALID` ; l’explication affiche les libellés obtenus par API.

**Preuves obligatoires :** appel Product, payload règle, SQL `rule_actions`, test négatif.

**Statut initial :** `NOT_RUN`.

### RS-AC-06 — enregistrer la règle

**Capacité exacte :** « enregistrer la règle ».

**Précondition :** règle v1 existante et ETag connu.

**Procédure :** enregistrer une modification via `PUT` avec `If-Match`, puis tenter une écriture concurrente avec un ETag obsolète.

**Assertions bloquantes :** une nouvelle version est créée au lieu d’écraser l’ancienne ; l’ancienne définition et son checksum restent inchangés ; la création multi-table et l’audit sont atomiques ; l’ETag obsolète retourne `412 RULE_VERSION_CONFLICT`; un échec injecté annule toutes les écritures.

**Preuves obligatoires :** réponses API, SQL comparant les versions/checksums, test de concurrence et preuve de rollback transactionnel.

**Statut initial :** `NOT_RUN`.

### RS-AC-07 — lancer une simulation

**Capacité exacte :** « lancer une simulation ».

**Précondition :** version `VALIDATED`; métriques historiques réelles en PostgreSQL.

**Procédure :** appeler `/simulate`, observer `QUEUED`, `RUNNING`, puis `SUCCEEDED` et interroger le résultat.

**Assertions bloquantes :** le job est asynchrone et idempotent ; il évalue le checksum demandé ; le résultat porte watermark, versions Analytics/Engine et compteurs ; `rule_simulations` est la source du résultat ; seule une réussite fait passer la version à `SIMULATED`; aucun taux de conversion n’est inventé.

**Preuves obligatoires :** chronologie API, ligne SQL de simulation, logs corrélés Management→Simulation→Analytics→Engine.

**Statut initial :** `NOT_RUN`.

### RS-AC-08 — voir combien de PME correspondent

**Capacité exacte :** « voir combien de PME correspondent ».

**Précondition :** simulation `SUCCEEDED`.

**Procédure :** afficher population, matches, taux et niveaux de confiance.

**Assertions bloquantes :** `matched = high + medium + low`; `matched <= population`; `matchRate` correspond au quotient ; les valeurs UI égalent la réponse API et la ligne PostgreSQL ; aucune valeur d’exemple statique n’est utilisée.

**Preuves obligatoires :** capture UI, réponse API, requête SQL, assertion arithmétique du test.

**Statut initial :** `NOT_RUN`.

### RS-AC-09 — voir des exemples de clients

**Capacité exacte :** « voir des exemples de clients ».

**Précondition :** simulation avec au moins un match.

**Procédure :** ouvrir la preview.

**Assertions bloquantes :** les vingt premiers clients au maximum exposent Customer ID, entreprise, signaux, valeurs, confiance et opportunité ; l’ordre est déterministe ; chaque valeur renvoie au même watermark de métrique ; un sujet hors périmètre ne voit ni nom ni client ; aucune transaction brute n’est exposée.

**Preuves obligatoires :** capture preview, réponse API, références de snapshots, test d’accès hors périmètre.

**Statut initial :** `NOT_RUN`.

### RS-AC-10 — tester la règle sur une PME

**Capacité exacte :** « tester la règle sur une PME ».

**Précondition :** client de test autorisé avec métriques connues.

**Procédure :** utiliser `TEST RULE` et sélectionner la PME ; exécuter aussi un cas non-match et un cas `UNKNOWN`.

**Assertions bloquantes :** chaque condition affiche actual, opérateur, attendu et résultat ; la racine et les groupes sont expliqués ; le type d’opportunité et la confiance sont cohérents ; `ruleId`, `ruleVersion`, `engineVersion` et `metricSnapshotId` sont présents ; les trois états logiques sont corrects.

**Preuves obligatoires :** captures des trois cas, réponses API, comparaison aux métriques PostgreSQL.

**Statut initial :** `NOT_RUN`.

### RS-AC-11 — soumettre la règle

**Capacité exacte :** « soumettre la règle ».

**Précondition :** version `SIMULATED` avec simulation qualifiante du même checksum.

**Procédure :** soumettre comme `BUSINESS_ANALYST`; tenter aussi depuis `DRAFT` ou avec un checksum modifié.

**Assertions bloquantes :** succès `SIMULATED→SUBMITTED`; sujet et heure sont persistés ; audit `SUBMITTED`; soumission prématurée retourne `409 SIMULATION_REQUIRED` ou `RULE_STATE_CONFLICT`; idempotence sans double audit métier.

**Preuves obligatoires :** réponse API, SQL version/audit, tests négatifs.

**Statut initial :** `NOT_RUN`.

### RS-AC-12 — la faire approuver par un autre rôle

**Capacité exacte :** « la faire approuver par un autre rôle ».

**Précondition :** version `SUBMITTED`; sujets Analyst et Approver distincts.

**Procédure :** tenter l’auto-approbation, tenter avec un rôle insuffisant, puis approuver avec un autre `RULE_APPROVER`.

**Assertions bloquantes :** auto-approbation refusée `403 SELF_APPROVAL_FORBIDDEN`, y compris pour `ADMIN`; Analyst sans scope refusé ; approbation distincte passe à `APPROVED`; `rule_approvals` contient sujet, rôle, checksum et corrélation ; audit append-only.

**Preuves obligatoires :** trois appels API, claims redigés, SQL approvals/audit.

**Statut initial :** `NOT_RUN`.

### RS-AC-13 — la publier

**Capacité exacte :** « la publier ».

**Précondition :** version `APPROVED`; dernière simulation qualifiante ; références valides.

**Procédure :** publier avec `Idempotency-Key`, observer `PUBLISHED→ACTIVE`, puis demander une évaluation production.

**Assertions bloquantes :** publication sans approbation est refusée ; seule la version `ACTIVE` apparaît dans le bundle Engine ; l’activation est atomique ; il n’existe qu’une version active par règle ; une évaluation production renvoie la version publiée et une version DRAFT est refusée ; un warning de règle trop large est accusé réception mais ne bloque pas automatiquement.

**Preuves obligatoires :** chronologie API, bundle/ETag, SQL versions/règle, test de production.

**Statut initial :** `NOT_RUN`.

### RS-AC-14 — voir sa version

**Capacité exacte :** « voir sa version ».

**Précondition :** règle avec plusieurs versions, dont une active.

**Procédure :** consulter la liste, le détail et la réponse d’évaluation/opportunité.

**Assertions bloquantes :** l’UI distingue `latestVersion` et `activeVersion`; le détail expose version et checksum ; chaque résultat du moteur et chaque opportunité expose `ruleId`, `ruleVersion`, `engineVersion`; aucun recalcul ne réécrit la version historique.

**Preuves obligatoires :** captures UI, réponses API, SQL règle/opportunité et audit.

**Statut initial :** `NOT_RUN`.

### RS-AC-15 — voir son historique

**Capacité exacte :** « voir son historique ».

**Précondition :** parcours de transitions déjà exécuté.

**Procédure :** ouvrir versions et audit, puis comparer aux tables.

**Assertions bloquantes :** toutes les versions et actions sont présentes dans l’ordre ; auteur, rôle, horodatage, avant/après, motif et corrélation sont disponibles selon l’autorisation ; aucune ligne d’audit n’a été modifiée ou supprimée ; la lecture hors rôle est refusée et auditée.

**Preuves obligatoires :** capture historique, API paginée, SQL versions/audit, test d’immutabilité.

**Statut initial :** `NOT_RUN`.

### RS-AC-16 — désactiver la règle

**Capacité exacte :** « désactiver la règle ».

**Précondition :** version `ACTIVE`.

**Procédure :** désactiver avec motif, rafraîchir le bundle Engine et réévaluer le client.

**Assertions bloquantes :** transition `ACTIVE→DISABLED`; motif obligatoire ; `rules.active_version_id` est mis à jour conformément à la politique ; la version disparaît du bundle actif et ne produit plus de nouvelle opportunité ; les opportunités historiques restent intactes ; audit `DISABLED`.

**Preuves obligatoires :** réponse API, bundle avant/après, SQL versions/audit/opportunités.

**Statut initial :** `NOT_RUN`.

### RS-AC-17 — restaurer une version précédente

**Capacité exacte :** « restaurer une version précédente ».

**Précondition :** au moins deux versions, cible historiquement approuvée/publiée, version courante active ou désactivée.

**Procédure :** appeler `/rollback` vers la cible avec motif ; tenter aussi une cible jamais approuvée.

**Assertions bloquantes :** cible invalide refusée ; rollback atomique avec une seule version active ; cible redevient `ACTIVE`, version remplacée devient `DISABLED`; audit `ROLLED_BACK` contient source, cible, motif et sujets ; Engine charge le checksum cible ; opportunités historiques conservent leurs versions d’origine.

**Preuves obligatoires :** appels positif/négatif, SQL avant/après, bundle Engine, audit et opportunités.

**Statut initial :** `NOT_RUN`.

## 5. Contrôles transverses obligatoires

Les contrôles suivants ne créent pas un dix-huitième critère. Ils sont des portes communes : un échec invalide tous les critères touchés.

### 5.1 Sécurité LLM

Le test doit démontrer que le LLM ne peut produire qu’une `StructuredRuleProposal`. Aucun credential PostgreSQL ou bancaire ne lui est accessible. Les appels `approve`, `publish`, `disable` et `rollback` avec son identité retournent `403`. Une proposition contenant SQL, code ou une instruction de contournement est rejetée ou neutralisée. L’import explicite par un utilisateur autorisé crée seulement une règle `DRAFT` et l’audit `LLM_PROPOSAL_IMPORTED`.

### 5.2 Performance batch

Une simulation sur plusieurs milliers de PME doit utiliser les métriques pré-calculées. Le rapport conserve `EXPLAIN (ANALYZE, BUFFERS)`, nombre de requêtes SQL, CPU, mémoire et durée. Toute requête SQL par condition/client ou tout recalcul depuis les transactions brutes est un `FAIL`. Les cibles chiffrées de [`rule-studio.md`](./rule-studio.md) sont évaluées seulement après mesure et restent `NOT_RUN` avant celle-ci [1].

### 5.3 Simulation, impact et faux positifs

Le run doit vérifier preview à vingt clients, distributions par secteur/région/segment, moyenne par RM, warning de règle large et KPI `Accepted`, `Dismissed`, `Not Relevant`, `Contacted`, `Converted`. Si les outcomes historiques sont insuffisants, le résultat correct est `conversionRate=null` avec `conversionRateStatus=NOT_AVAILABLE`.

### 5.4 Contrats et persistance

Les OpenAPI public et internes doivent valider requêtes, réponses, erreurs, sécurité, idempotence et ETag. Les huit tables, contraintes, index et transactions critiques sont testés sur PostgreSQL réel. Les services autres que Management n’ont aucun droit SQL sur `rule_management`.

### 5.5 No-code et absence de données statiques

Le navigateur ne propose ni SQL ni code. Le test de réseau doit relier chaque écran à une API active. Une fixture locale ou une réponse interceptée qui fabrique les résultats invalide les critères RS-AC-01 à RS-AC-17 concernés.

## 6. Matrice synthétique de traçabilité

| ID | Capacité | API principale | Tables/preuves principales | Familles de tests |
|---|---|---|---|---|
| RS-AC-01 | créer | `POST /rules` | `rules`, `rule_versions`, audit | E2E, API, PostgreSQL |
| RS-AC-02 | métriques | `PUT /rules/{id}` | `rule_conditions` | UI, contrat, validation |
| RS-AC-03 | opérateurs | `validate`, `test` | conditions/trace | unitaires, contrat, métier |
| RS-AC-04 | seuils | `PUT`, `validate` | definition/checksum | frontières, validation |
| RS-AC-05 | opportunité | `PUT`, `validate` | `rule_actions` | intégration Product |
| RS-AC-06 | enregistrer | `PUT /rules/{id}` | versions, transaction | concurrence, PostgreSQL |
| RS-AC-07 | simulation | `POST /simulate` | `rule_simulations` | interservices, PostgreSQL |
| RS-AC-08 | compteur | `GET /simulations/{id}` | compteurs | API, UI, SQL |
| RS-AC-09 | exemples | `GET /preview` | preview/snapshots | E2E, sécurité |
| RS-AC-10 | tester PME | `POST /test` | trace evidence | métier, E2E |
| RS-AC-11 | soumettre | `POST /submit` | version, audit | état, idempotence |
| RS-AC-12 | approuver | `POST /approve` | approvals, audit | RBAC, séparation |
| RS-AC-13 | publier | `POST /publish` | version active/bundle | état, Engine, transaction |
| RS-AC-14 | version | `GET /rules/{id}` | version/opportunité | API, E2E, SQL |
| RS-AC-15 | historique | `GET /versions`, `/audit` | versions/audit | API, sécurité, immutabilité |
| RS-AC-16 | désactiver | `POST /disable` | active bundle/audit | état, Engine, SQL |
| RS-AC-17 | restaurer | `POST /rollback` | versions/audit/bundle | transaction, E2E |

## 7. Registre de résultat initial

Aucun run de code, de test, de migration, d’API, de navigateur ou de performance n’a été exécuté dans le cadre de la rédaction documentaire. Le registre initial est donc :

| ID | Statut | Preuve de run | Commentaire |
|---|---|---|---|
| RS-AC-01 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-02 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-03 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-04 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-05 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-06 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-07 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-08 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-09 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-10 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-11 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-12 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-13 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-14 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-15 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-16 | `NOT_RUN` | aucune | spécification seulement |
| RS-AC-17 | `NOT_RUN` | aucune | spécification seulement |

## 8. Règle de sortie

Le module est accepté uniquement lorsque les dix-sept lignes sont `PASS` dans un même run de release ou dans des runs compatibles qui partagent le même build immuable, les mêmes migrations et une traçabilité complète. Aucun résultat `BLOCKED`, `FAIL` ou `NOT_RUN` n’est admissible pour la release MVP.

## Références

[1]: ./rule-studio.md "Rule Engine & Rule Studio — spécification exécutable"
[2]: file:///home/ubuntu/upload/Pasted_content_100.txt "Cahier d’exigences — Module critique Rule Engine & Rule Studio"
[3]: ./test-plan.md "Plan de tests — BOA SME Opportunity Intelligence"
[4]: ./api.md "Contrats API-first — BOA SME Opportunity Intelligence"
[5]: ./data-model.md "Modèle relationnel PostgreSQL et pipeline de données synthétiques"
[6]: https://www.postgresql.org/docs/current/using-explain.html "PostgreSQL — Using EXPLAIN"
[7]: https://spec.openapis.org/oas/v3.0.3 "OpenAPI Specification 3.0.3"
