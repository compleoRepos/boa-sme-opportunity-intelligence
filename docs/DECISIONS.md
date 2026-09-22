# Journal des décisions

## 19 septembre 2026 — Branche de départ du chantier pilote

**Question.** Le mandat indique que `feat/ux-premium-cockpit` doit être deux commits devant `main`, mais cette branche n’existe pas sur `origin`. Le bundle disponible expose uniquement le commit UX `3e43581`, déjà intégré à `main` par la pull request #2. `main` contient en outre les validations ML, la gouvernance et les correctifs postérieurs.

**Option retenue.** Créer localement `feat/ux-premium-cockpit` comme alias du `main` validé, puis créer `feat/pilot-readiness` depuis cet alias. Cette option conserve toute l’UX Claude sans perdre les validations ML et évite de réintroduire des régressions en repartant d’un commit ancien.

**Alternative si BOA décide autrement.** Rebaser les seuls commits du chantier pilote sur une future branche officielle `feat/ux-premium-cockpit`, puis rejouer toutes les migrations et portes de qualité avant fusion.

**Impact.** Aucun historique existant n’est réécrit. Le point de départ réel et le décalage avec le mandat sont traçables dans l’audit préalable.

## 19 septembre 2026 — Politique lifecycle initiale du pilote

**Question.** Le mandat exige une expiration, un cooldown et un traitement explicite du choix « à revoir », sans fournir les durées à appliquer par type d’opportunité.

**Option retenue.** Introduire l’état terminal `DEFERRED` et l’outcome `REVIEW_LATER`. Versionner cinq paramètres dans chaque règle : durée de validité et cooldown après rejet, conversion, report ou expiration. Les valeurs initiales sont 30 jours après rejet, 180 jours après conversion, 30 jours après report et 7 jours après expiration. La validité est de 90 jours pour financement d’investissement et Trade Finance, de 60 jours pour placement de trésorerie et de 30 jours pour le signal relationnel de tension financière.

**Statut des valeurs.** Ces durées sont des hypothèses de configuration du pilote, pas des résultats mesurés. Le comité métier peut les modifier dans Rule Studio ; toute modification crée une nouvelle version auditée.

**Règle de non-régression.** Une opportunité terminale n’est jamais rouverte. Un nouveau candidat du même client et du même type est supprimé jusqu’à `cooldownUntil`, puis peut créer une nouvelle instance. Une opportunité active est rafraîchie sans doublon.

**Résilience interservice.** Une transition terminale strictement identique est rejouable afin qu’Action Service puisse terminer sa transaction locale après une panne partielle. Un rejeu avec un autre cooldown est refusé par `409 OPPORTUNITY_TRANSITION_REPLAY_CONFLICT`.

## 19 septembre 2026 — Cohérence distribuée et concurrence du pilote

**Question.** Une revue indépendante a montré qu’un appel Opportunity exécuté avant le commit Action pouvait laisser un succès distant sans action locale. Elle a aussi relevé une course possible entre deux générations sur une clé métier absente.

**Option retenue.** Action Service persiste une commande locale `PENDING` avant tout appel distant. Opportunity Service déduplique son identifiant stable. Après réponse, Action passe la commande à `APPLIED` et écrit l’outcome, ou à `FAILED` avec code et compteur de tentatives. Le même appel idempotent reprend une commande inachevée. Pour la génération, `pg_try_advisory_xact_lock` revendique `(client, type)` sans bloquer le worker async; un concurrent reçoit `409 GENERATION_IN_PROGRESS`. L’expiration utilise `FOR UPDATE SKIP LOCKED`.

**Limite acceptée pour le pilote.** Il ne s’agit pas d’un commit distribué ACID et aucun dispatcher permanent ne reprend automatiquement les échecs. L’état durable rend cependant chaque succès partiel visible et reprenable. Un worker avec backoff et file morte est requis avant production à haute disponibilité.

## 19 septembre 2026 — Contrat de synchronisation portefeuille du pilote

**Question.** Le mandat exige une synchronisation contrôlée et datée, mais ne fournit pas encore le contrat du système source, les règles de correction rétroactive, les affectations secondaires ni les délégations.

**Option retenue.** Ajouter un contrat batch `1.0` séparé de l’import client. Chaque événement source contient un identifiant stable, le client, le portefeuille, le CC, l’agence, la date d’effet, le motif et le watermark du lot. Le pilote accepte uniquement une affectation `PRIMARY`, interdit les chevauchements en PostgreSQL et conserve un reçu rejouable, un journal d’événements, un audit avant/après et une outbox dans la même transaction.

**Politique d’autorisation.** La route publique est réservée à `ADMIN`. La route interne accepte `ADMIN` ou le compte dont le `client_id` est exactement `banking-integration-service`. Le rôle générique `SERVICE` n’accorde donc pas la capacité de synchronisation à tous les microservices. Le compte et les scopes définitifs devront être alignés avec l’IAM BOA.

**Politique temporelle.** Une affectation future clôt l’intervalle courant à sa date d’effet. Un événement antérieur au dernier intervalle est refusé par `409 OUT_OF_ORDER_ASSIGNMENT`; une réconciliation rétroactive administrée est différée jusqu’à validation des règles BOA. Les délégations, affectations secondaires, corrections multi-intervalles et suppressions source restent hors périmètre du pilote.

**Audit.** La migration `0012_portfolio_sync_governance` ajoute un trigger qui refuse `UPDATE` et `DELETE` sur `audit.audit_logs`. Cette protection append-only PostgreSQL n’est ni un stockage WORM, ni une intégration SIEM, ni une politique de rétention ; ces contrôles restent à définir avant production.

## 21 septembre 2026 — Simulation Studio ML serveur et non opérationnelle

**Question.** Le brief Studio ML demande une comparaison avant/après de la distribution des priorités, des montées/descentes et du top 10, sans permettre au navigateur d’inventer un échantillon.

**Option retenue.** La simulation est calculée côté serveur à partir des opportunités et scores shadow persistés, puis son résultat détaillé est inscrit dans l’audit append-only. Elle peut faire évoluer une version vers `SIMULATED`, mais ne modifie jamais les priorités opérationnelles persistées. Aucun échantillon client ou nombre fictif n’est accepté.

**Limite.** Les formules, seuils et populations restent **HYPOTHÈSE À VALIDER AVEC BOA**. La priorité demeure `RULES_ONLY` et le ML `POC_SHADOW`; l’activation G3 reste bloquée en l’absence de labels historiques BOA et de validation indépendante.

## 21 septembre 2026 — Visibilité des flux et multibancarisation

**Question.** La plateforme ne voyait initialement que les flux domiciliés chez BOA. Comment détecter une relation principale ou secondaire sans accès aux comptes d’une autre banque, sans inventer de données externes et sans confondre absence chez BOA et absence totale ?

**Option retenue.** Introduire un niveau de visibilité explicite `HIGH/PARTIAL/LOW/UNKNOWN` calculé avec une hiérarchie de méthodes : déclaration autorisée, ratio encaissements BOA sur chiffre d’affaires déclaré, empreintes transactionnelles agrégées, puis `UNKNOWN`. La donnée brute conservée reste interne ou déclarative ; aucune institution tierce n’est nommée. La méthode, la date et les faits sont persistés avec lignée.

**Prudence commerciale.** Product Service requalifie l’absence en `ABSENT_OR_ELSEWHERE` lorsque la visibilité est partielle ou faible. Opportunity retire `CASH_INVESTMENT` pour `LOW`, applique une pénalité à `PARTIAL`, désactive les règles sensibles et transforme `FLOW_DOMICILIATION` en recommandation `WIN_BACK`. La priorité opérationnelle reste `RULES_ONLY`.

**Gouvernance.** La règle `FLOW_DOMICILIATION_001` est seedée en `DRAFT`, simulée sur une population serveur, soumise par `business.analyst.demo`, approuvée par `rule.approver.demo`, publiée puis activée avec audit complet. L’auto-approbation et la modification par un CC hors portefeuille sont refusées. Les seuils 0,70/0,30, les pénalités, les empreintes minimales et le cooldown sont **HYPOTHÈSE À VALIDER AVEC BOA**.

**Activation des paramètres.** Une édition de seuil crée une version inactive de `analytics.flow_visibility_policies` et ne change donc pas le calcul courant. La publication de la version Rule Studio `FLOW_DOMICILIATION` par un approbateur distinct désactive l’ancienne politique et active la dernière version en attente dans la même transaction. Analytics et Opportunity ne lisent que la version active. Le cooldown est calculé à partir de cette version et rapproche exclusivement le champ structuré `action.opportunity_actions.opportunity_type`; aucun texte libre n’est utilisé comme preuve de domiciliation.

**Temporalité et rollback.** Les événements de relation bancaire sont append-only. La relation effective et le chiffre d’affaires effectif sont sélectionnés indépendamment à la date de coupe, et les transactions non `BOOKED` sont exclues des estimations. Le downgrade `0020 → 0019` est refusé tant que des données métier seraient détruites, y compris celles présentes directement dans les colonnes ajoutées aux tables historiques ; export ou suppression gouvernée est une précondition explicite.

## Références

[1]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[2]: ./api.md "Contrats API-first — BOA SME Opportunity Intelligence"
