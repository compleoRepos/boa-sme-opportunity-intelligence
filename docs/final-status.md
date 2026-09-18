# Statut final — BOA SME Opportunity Intelligence

**Date du constat documentaire :** 2026-09-18

> Ce document est un gabarit factuel à finaliser après exécution de l’auto-validation. Il ne déclare pas une fonctionnalité comme réalisée sur la seule base d’un document ou de fichiers présents. Tout élément « à confirmer » doit recevoir une preuve de run, de test ou d’artefact.

## IMPLEMENTED

| Élément | Preuve requise | Constat |
|---|---|---|
| Stack Python 3.12/FastAPI déclarée | `backend/pyproject.toml`, build et `/health` | À confirmer par exécution |
| SQLAlchemy et Alembic | dépendances et migration sur base vide | À confirmer par exécution |
| Frontend React/TypeScript et Gateway | build et smoke navigateur | À confirmer par exécution |
| Seed sans opportunités préchargées | rapport de seed et comptage PostgreSQL | À confirmer par exécution |
| Règles, preuves et audit | tests métier et inspection de persistance | À confirmer par exécution |

## PARTIALLY IMPLEMENTED

À compléter lorsque le code existe mais que la preuve de bout en bout manque.

- Le dépôt contient un socle backend Python/FastAPI, des modèles et une migration initiale ; la séparation complète des services, les routes métier et le parcours complet doivent être prouvés par intégration.
- La documentation fixe HTTP + outbox, mais la persistance, la reprise et l’idempotence de l’outbox doivent être vérifiées sur l’environnement cible.
- L’interface et les contrats sont présents dans le dépôt ; leur branchement complet à des données recalculées et leur contrôle RBAC restent à mesurer.

## NOT IMPLEMENTED

À compléter après inventaire des exigences non couvertes. Ne pas inventer de résultat absent du dépôt ou des rapports.

- Rule Studio complet avec simulation, approbation, publication et rollback : à confirmer.
- Simulation historique avec taux de conversion réel : à confirmer ; aucune conversion ne doit être inventée.
- Déploiement de production haute disponibilité, sauvegarde testée, rotation de secrets et intégration bancaire réelle : hors preuve fournie ici.

## KNOWN LIMITATIONS

Le dataset est synthétique. Docker Compose local n’est pas une cible de haute disponibilité. L’historique saisonnier est limité par la période disponible. Les paramètres non validés par BOA doivent rester marqués `DEMO_DEFAULT` ou `PENDING_APPROVAL`. Aucun ML, appel LLM ou décision de crédit ne fait partie du MVP.

## TECHNICAL DEBT

Le registre doit préciser propriétaire, priorité, risque et date cible. Les sujets attendus sont la séparation physique éventuelle des bases, les projections Customer 360, la reprise des jobs, les tests de permission par service, la mesure de performance, l’outillage de migration et le durcissement des secrets.

## NEXT STEPS

1. Exécuter l’auto-validation avec une base vide et conserver le rapport.
2. Vérifier migrations, seed, pipeline HTTP, outboxes et idempotence.
3. Exécuter BR-001 à BR-012, FP-001 à FP-007, contrats, sécurité et smoke E2E.
4. Remplacer chaque « à confirmer » par `PASS`, `FAIL`, `SKIPPED_OPTIONAL` ou `NOT_APPLICABLE`, avec preuve.
5. Faire valider les paramètres métier et la cartographie BIAN-inspired sans présenter celle-ci comme une certification.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../docs/test-plan.md "Plan de tests"
[3]: ../architecture/data-flow.md "Flux de données"
