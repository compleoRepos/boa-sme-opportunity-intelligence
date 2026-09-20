# Workstream — Observation `POC_SHADOW` et priorité `RULES_ONLY`

**Statut courant : intégré et validé localement.** La migration `0017_ml_shadow_governance` remplace l’ancien comportement hybride documenté avant le 20 septembre 2026.

## Résumé

`ResilientMLClient` appelle le ML Engine avec timeout, retries bornés et circuit breaker en mémoire. Le mode nominal est `POC_SHADOW` : une réponse valide est persistée et auditée, mais `used_ml=false` indique qu’elle ne participe pas à la décision opérationnelle. Toute erreur terminale, indisponibilité, réponse invalide ou score obsolète produit également une priorité `RULES_ONLY`, sans score inventé ou réutilisé.

Le composant est CPU-only, sans LLM, sans GPU et sans cache de score. Il ne prend aucune décision de crédit.

## Contrat de résultat

En succès shadow, `MLScoreResult` expose le score courant, `mode=POC_SHADOW`, `used_ml=false`, `cause=None` et l’événement `ML_SCORE_OBSERVED_SHADOW`. En panne, il expose `mode=RULES_ONLY`, `used_ml=false`, `score=None`, une cause structurée et `ML_FALLBACK_APPLIED`.

Les causes comprennent notamment `RULES_ONLY_EXPLICIT`, `ML_TIMEOUT`, `ML_HTTP_5XX`, `ML_UNAVAILABLE`, `ML_SCORE_ABSENT`, `ML_SCORE_STALE` et `ML_CIRCUIT_OPEN`. Une panne de l’audit best-effort ne transforme jamais un échec en score valide.

## Intégration Opportunity

Opportunity Service calcule les candidates à partir des règles. Un score shadow éventuellement disponible est rangé sous `propensityShadow` avec ses versions et sa trace. La combinaison opérationnelle reste toujours :

```json
{
  "mode": "RULES_ONLY",
  "rulesWeight": 1.0,
  "mlWeight": 0.0,
  "shadowReadOnly": true
}
```

`rerank_with_propensity` conserve la candidate inchangée lorsque le mode est `POC_SHADOW`. La priorité persistée, le niveau et le classement du Portfolio restent indépendants de la valeur du score.

## Défense en profondeur

Le domaine de Scoring Policy refuse la transition `ACTIVE` si le poids ML est non nul. Le service persistant refuse également l’activation et le rollback vers une version hybride. PostgreSQL impose les mêmes invariants aux policies actives et aux opportunités. Une migration recalculée neutralise les priorités historiques qui contenaient une composante ML.

## Vérifications

Les tests couvrent le succès shadow, les pannes, la fraîcheur, le circuit breaker, l’invariance de priorité pour deux scores différents, le blocage d’une policy hybride et les contraintes PostgreSQL. `scripts/validate-ml-integration.sh` produit une preuve JSON de la policy rules-only, de l’absence d’influence et de l’environnement CPU-only.

## Limites

Le circuit breaker reste par processus. Les seuils de timeout et de retry sont techniques et doivent être validés pour une cible BOA. L’activation de tout reranking ML est **NON IMPLÉMENTÉE / BLOQUÉE** tant que les historiques BOA, le manifest point-in-time, la calibration, les critères d’acceptation et la validation indépendante ne sont pas disponibles. Les données locales/synthétiques ne constituent aucune performance ML de production.
