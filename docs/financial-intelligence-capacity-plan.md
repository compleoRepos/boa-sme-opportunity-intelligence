# Plan de capacité — Financial Intelligence API

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Statut

Ce plan couvre uniquement une mesure technique sur stack Docker Compose locale et données synthétiques. Il ne constitue ni un SLO BOA, ni une capacité de production. Tous les seuils sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Charge mesurée

Le benchmark appelle le résumé portfolio sur quatre compositions synthétiques : 10, 50, 100 et 500 PME. Chaque société entraîne cinq lectures idempotentes vers Customer, Analytics, Signal, Opportunity et Portfolio. La réponse indique donc `downstreamCallCount = companyCount × 5`. Le service borne le traitement concurrent par `FI_PORTFOLIO_CONCURRENCY` entre 1 et 25 et refuse une composition supérieure à 500 PME.

Chaque taille est exécutée cinq fois sur une stack préchauffée. Les durées brutes, P50 et P95 sont conservées dans `docs/evidence/financial-intelligence/RESULTATS-PERFORMANCE-FI.json`. Le validateur ajoute un instantané `docker stats` des conteneurs FI, Gateway et domaines propriétaires. Cette mesure mono-nœud ne représente pas la concurrence de plusieurs consommateurs.

## Résultats mesurés sur `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`

| Portfolio | Appels aval par requête | P50 API | P95 API | Rendu dashboard | Verdict local |
|---:|---:|---:|---:|---:|---|
| 10 PME | 50 | 2,481 s | 3,912 s | 3,117 s | **PASS** |
| 50 PME | 250 | 12,435 s | 13,262 s | 12,868 s | **PASS** |
| 100 PME | 500 | 23,707 s | 25,060 s | 25,707 s | **PASS** |
| 500 PME | 2 500 | 123,860 s | 125,042 s | 120,209 s | **PASS** |

L’échantillonnage `docker stats` contient 1 694 observations sur sept services. Le pic CPU mesuré est de 60,43 % sur Opportunity. Le service Financial Intelligence atteint 286,5 MiB sur sa limite locale de 320 MiB, soit 89,53 %. Cette consommation laisse une marge locale faible et doit être surveillée, mais le conteneur n’a pas été tué et les 20 mesures ont terminé. Elle ne prouve aucune capacité de production, car aucune infrastructure de production ni charge multi-utilisateur n’a été testée. La preuve détaillée est conservée dans `RESULTATS-RESSOURCES-FI.json`.

Le portfolio 10 PME retourne `mlGovernanceStatus=VERIFIED`. Les portfolios 50, 100 et 500 retournent `UNAVAILABLE` et des champs mode/poids nuls dès qu’au moins une société ne peut pas attester sa gouvernance ML. Ce comportement fail-closed est attendu et le benchmark le vérifie ; il ne transforme pas l’indisponibilité en assertion `POC_SHADOW`.

## Seuils locaux de non-régression

| Taille | P95 maximal du gate local | Qualification |
|---:|---:|---|
| 10 PME | 30 s | **HYPOTHÈSE À VALIDER AVEC BOA** |
| 50 PME | 90 s | **HYPOTHÈSE À VALIDER AVEC BOA** |
| 100 PME | 180 s | **HYPOTHÈSE À VALIDER AVEC BOA** |
| 500 PME | 600 s | **HYPOTHÈSE À VALIDER AVEC BOA** |

Ces seuils détectent une régression grossière dans le POC ; ils ne sont pas des objectifs bancaires. Le benchmark échoue si une requête dépasse son budget ou si le nombre d’appels downstream diffère de la valeur annoncée.

## Leviers déjà implémentés

La composition utilise un semaphore borné, des timeouts par dépendance, une limite de 500 sociétés, une pagination du catalogue et des appels de lecture idempotents. Les proxys frontend et Gateway possèdent un budget dédié aux seules routes FI, borné à 600 secondes, afin que la composition maximale ne retombe pas sur leurs défauts génériques de 60 et 15 secondes ; cette valeur est un garde de démonstration et non un SLO. Les réponses partielles exposent les dépendances indisponibles au lieu de fabriquer des valeurs. Aucune donnée brute n’est mise en cache dans le navigateur.

## Travail requis avant production

La production reste **BLOCKED** jusqu’à une campagne multi-utilisateur couvrant cold/warm cache, P50/P95/P99, débit, saturation des pools HTTP/DB, backpressure, tailles de payload, CPU, mémoire, réseau, erreur, reprise et dégradation par dépendance. Les SLO, quotas Consumer, politiques de cache, budgets egress et dimensionnement doivent être validés avec BOA sur une infrastructure cible homologuée.
