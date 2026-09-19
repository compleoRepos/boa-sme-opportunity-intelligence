# Workstream — Fallback explicite `HYBRID_ML` / `RULES_ONLY`

> **Statut courant : intégré et validé sur Docker.** Les sections d’intégration ci-dessous conservent la décision de conception initiale. Les preuves finales sont dans [`../finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

## Résumé

Le composant `boa_oi.resilience` fournit un client ML générique, asynchrone et **CPU-only**. Il ne réalise pas d’inférence et ne dépend ni d’un LLM, ni d’un GPU, ni d’un cache de scores. Le client appelle un transport injecté avec un timeout configurable, un nombre maximal de retries borné à cinq, et un circuit breaker en mémoire. Toute erreur terminale, réponse HTTP 5xx, indisponibilité réseau, timeout, score absent ou score obsolète produit un résultat `RULES_ONLY` avec `score=None`. Un score précédent n’est jamais conservé ni réutilisé.

Le contrat est porté par `ResilientMLClient`, `MLScoreResult`, `FallbackCause`, `AuditEvent`, `CircuitBreaker`, `FallbackMode` et `CircuitState`. Le mode nominal explicite est `HYBRID_ML`; le mode `RULES_ONLY` peut être demandé directement et n’appelle alors pas le transport ML.

## Fichiers livrés et vérification

| Fichier | Rôle |
|---|---|
| `backend/src/boa_oi/resilience/ml_client.py` | Client générique, cause structurée, événements d’audit, retries, timeout, fraîcheur et circuit breaker mémoire. |
| `backend/src/boa_oi/resilience/__init__.py` | Exports publics du composant. |
| `tests/unit/test_resilience.py` | Huit tests unitaires couvrant ML OK, timeout, 500, indisponibilité, score absent, score obsolète, `RULES_ONLY` explicite, ouverture et récupération du circuit. |

Validation exécutée : `pytest -q tests/unit/test_resilience.py` — **8 tests réussis**; compilation Python — **réussie**; Ruff sur les fichiers livrés — **réussi**.

## Contrat de résultat

`await client.score(request, mode="HYBRID_ML", as_of=..., max_score_age=...)` renvoie toujours un `MLScoreResult`. En succès, `used_ml=True`, `mode=HYBRID_ML`, `score` est un nombre fini dans `[0, 1]`, `cause=None`, et l’événement `ML_SCORE_ACCEPTED` est envoyé au sink d’audit. En fallback, `used_ml=False`, `mode=RULES_ONLY`, `score=None`, `response=None`, et `cause` est un `FallbackCause` sérialisable par `as_dict()`.

Les causes structurées actuellement produites sont `RULES_ONLY_EXPLICIT`, `ML_TIMEOUT`, `ML_HTTP_5XX`, `ML_UNAVAILABLE`, `ML_SCORE_ABSENT`, `ML_SCORE_STALE` et `ML_CIRCUIT_OPEN`. Chaque cause expose au minimum `code`, `category`, `message`, `retryable`, `statusCode`, `attempts` et `details`. Chaque tentative terminale émet `ML_FALLBACK_APPLIED`; les événements portent le mode, l’état du circuit, le nombre de tentatives, la présence du score et la cause. Le sink d’audit est best-effort : une panne d’audit ne peut pas empêcher le fallback déterministe.

La fraîcheur est contrôlée sur `scoredAt`/`generatedAt` avec `max_score_age` (300 secondes par défaut) et, lorsqu’il est fourni, sur `asOf` par rapport à la demande. Une date de scoring illisible est considérée comme invalide et donc obsolète. Le composant ignore volontairement tout score antérieur.

## Étapes exactes d’intégration dans `opportunity_api.py`

1. **Instancier une fois par processus**, au niveau du service et non dans la boucle client, un `ResilientMLClient` avec un transport adaptateur basé sur `service_request`. Le transport doit envoyer le même `correlation_id`, l’autorisation entrante et le payload actuel `{ "asOf": payload.asOf.isoformat() }` vers `ML_ENGINE_SERVICE_URL/internal/v1/ml/customers/{customer_id}/score`. Configurer le timeout plus court que le budget global du job et `max_retries` à une valeur petite (par exemple `1` ou `2`); ne pas faire de retry non borné dans `service_request`.

2. **Remplacer uniquement l’appel direct** situé dans `generate`, lignes actuelles 555–560, par `await resilient_ml.score(...)`. Le transport doit convertir la réponse de `service_request` en mapping; `service_request` transforme déjà un timeout en `Problem(504, DEPENDENCY_TIMEOUT)` et un 5xx en `Problem(502, DEPENDENCY_UNAVAILABLE)`, que l’adaptateur peut laisser remonter : le client les normalise en timeout/HTTP-unavailable et applique ses retries.

3. **Conserver séparées les règles et le score ML**. Appeler `rule_engine_candidates` et `engine.evaluate` comme aujourd’hui, puis ne faire `rerank_with_propensity` que si `result.used_ml` est vrai et `result.score` n’est pas `None`. En fallback, conserver exactement les candidates produites par les règles locales et Rule Engine; ne jamais appeler `rerank_with_propensity` avec une ancienne réponse ML.

4. **Représenter le fallback dans l’explication et l’audit**. Ajouter dans `explanation["combination"]` les champs `mode`, `fallbackCause` et `auditEvent`; en succès, conserver les métadonnées du score actuel. En fallback, indiquer explicitement `mode: RULES_ONLY`, `mlScore: None`, la cause sérialisée et l’événement `ML_FALLBACK_APPLIED`. Ne pas créer de score synthétique, moyenne sectorielle ou valeur par défaut.

5. **Brancher le sink d’audit vers l’outbox/audit existant**. `AuditEvent.as_dict()` est le payload. Dans le contexte SQL transactionnel de `generate`, créer l’`OutboxMessage` avec un `event_type` dédié, par exemple `ML_FALLBACK_APPLIED` ou `ML_SCORE_ACCEPTED`, `aggregate_type="ml-score-request"`, l’identifiant client comme agrégat, le `correlation_id` de la requête et le payload de l’événement. Si l’équipe choisit `AuditLog`, conserver `service_name`, `action`, `resource_type`, `resource_id`, `correlation_id`, `result` et `metadata_json` sans y mettre de secret.

6. **Éviter les effets de bord partiels**. Le résultat de fallback doit être calculé avant la fusion et l’écriture de l’opportunité. Le circuit breaker reste mémoire et par instance de processus; sa métrique doit être exposée séparément si le déploiement comporte plusieurs workers. La cohérence inter-worker ne doit pas être supposée.

## Étapes exactes d’intégration dans `http_clients.py`

1. Ajouter, si nécessaire, un petit adaptateur de transport générique qui appelle `service_request` et laisse passer son contrat `Problem`; ne pas dupliquer la logique d’authentification déjà présente.
2. Passer le timeout de la résilience au `service_request` via son argument `timeout`, en veillant à ne pas confondre le délai de chaque tentative avec le budget total du job.
3. Préserver `X-Correlation-ID`, `Authorization` entrant ou token technique et les paramètres d’idempotence; ne jamais enregistrer les headers sensibles dans `FallbackCause.details` ou les événements.
4. Maintenir la distinction : réseau/timeout et 5xx sont retryables; 4xx métier ne doit pas être retryé automatiquement et doit basculer directement en `RULES_ONLY` avec une cause HTTP structurée.

## Compatibilité avec les modèles et le ML existant

`ml_engine_api.py` expose le score à `POST /internal/v1/ml/customers/{customer_id}/score` et `ml.service.serialize_score` fournit `propensity`, `modelVersion`, `featureVersion`, `trainingDatasetVersion`, `deploymentMode`, `traceId`, `scoredAt` et `asOf`. Le composant valide uniquement la présence et les bornes du score ainsi que la fraîcheur; il laisse la gouvernance des versions et des features à la couche ML existante. `LogisticScorer` reste l’inférence CPU locale du service ML; le nouveau client est uniquement la frontière de résilience du consommateur.

Dans `opportunity_api.py`, `rerank_with_propensity` attend aujourd’hui le mapping brut et lit `propensity`, `modelVersion`, `featureVersion`, `trainingDatasetVersion`, `deploymentMode` et `traceId`. L’intégration doit donc transmettre le mapping brut uniquement après validation réussie, et ajouter les métadonnées de résilience à l’explication sans modifier le score ML. Les modèles SQL `PropensityScoreRecord` et `DecisionAudit` n’ont pas à être modifiés pour ce workstream; l’événement de fallback doit être append-only via audit/outbox, sans réutiliser un enregistrement `PropensityScoreRecord` ancien.

## Politique de sécurité et de défaillance

Le mode `HYBRID_ML` signifie « tenter le ML puis basculer explicitement vers les règles si le score courant n’est pas utilisable », et non « toujours combiner avec un score disponible en base ». `RULES_ONLY` est le seul résultat opérationnel de secours. Le composant n’écrit aucune donnée bancaire, n’exécute aucune décision de crédit et ne contient aucune dépendance GPU/LLM.

Le circuit est `CLOSED` au démarrage, passe `OPEN` après le nombre configuré d’échecs terminalisés, bloque les appels pendant `recovery_timeout`, puis autorise un seul probe `HALF_OPEN`. Un probe réussi ferme le circuit; un probe échoué le rouvre. Les réponses avec score absent ou obsolète comptent comme échec de dépendance pour protéger le service contre des réponses nominales mais inutilisables.

## Risques et limites à traiter avant production

- Le circuit breaker est intentionnellement en mémoire : plusieurs workers ou pods ont des états indépendants. Une métrique et une alerte par instance sont nécessaires; un breaker distribué n’est pas inclus.
- Le timeout est appliqué autour du transport async. Les appels synchrones lourds ne doivent pas être injectés directement; ils doivent être déportés ou encapsulés dans un executor.
- La politique de retry doit être calibrée avec le budget de génération et le volume batch. Les retries ne sont sûrs que pour des appels ML idempotents.
- `max_score_age` doit être validé contre le SLA métier et le champ `asOf`; la valeur 300 secondes est un défaut technique, pas une approbation de gouvernance.
- L’écriture de l’événement d’audit dans l’intégration doit être transactionnelle et idempotente. Le sink fourni est best-effort pour préserver le fallback, donc l’outbox persistant est recommandé pour une traçabilité réglementaire.
- Aucun changement UI n’est requis ou inclus. Le frontend peut ignorer les nouveaux champs jusqu’à une évolution contractuelle séparée.
