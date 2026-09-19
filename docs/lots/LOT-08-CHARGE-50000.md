# Lot 08 — Validation de charge isolée sur 50 000 PME

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Verdict :** **PASS technique dans l’environnement Docker décrit ci-dessous**

## Conclusion

Le protocole reproductible a constitué une base PostgreSQL isolée contenant **50 000 clients PME synthétiques déterministes**, **50 000 affectations de portefeuille** et **50 000 opportunités**, puis a exécuté dix scénarios HTTP avec des limites CPU et mémoire explicites. Les deux health checks respectent leur cible p99 et les six parcours métier ciblés respectent leur cible p95. Les dix scénarios présentent un taux d’erreur HTTP de **0 %**. La recherche client scopée, qui constituait l’unique échec du run précédent, atteint **1 296,913 ms au p95** pour une cible stricte inférieure à **1 500 ms**, avec dix requêtes concurrentes et 0,35 CPU alloué au Customer Service.[1]

Ce résultat démontre que le protocole local défini pour ce lot est franchi. Il **ne constitue ni une homologation, ni un SLO, ni une certification de capacité de production, ni une validation AWS**. Les données sont synthétiques. Le protocole ne mesure pas le batch complet Analytics → Rules → Features → ML sur 50 000 PME et ne permet aucune revendication de performance ML ou commerciale. Toute extrapolation de capacité, de disponibilité, de coût ou de volumétrie BOA demeure une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Périmètre réellement mesuré

La fixture a été créée en **20,185 secondes** avec la graine déterministe `boa-sme-oi-load-50k-v1`. Elle contient 25 chargés de clientèle répartis sur cinq agences. La taille de la base était de **126 546 403 octets** après constitution et de **126 693 859 octets** à la fin des mesures. Le run final porte l’identifiant `load-50k-20260919T224716Z` et a été généré le 19 septembre 2026 à 22:47:16 UTC.[1] [2]

Les services applicatifs ont été démarrés dans des conteneurs dédiés avec les limites suivantes : Customer Service, 0,35 CPU et 320 Mio ; Opportunity Service, 0,75 CPU et 512 Mio ; Portfolio Service, 0,35 CPU et 320 Mio ; PostgreSQL, 1,25 CPU et 1 400 Mio. Le runner utilisait Python 3.12.7 sur Linux amd64. PostgreSQL 16.4 exposait 128 Mio de `shared_buffers` et une limite de 100 connexions.[1]

Le protocole ne charge pas 50 000 historiques bancaires complets. Il ne génère pas les signaux, features ou inférences ML pour les 50 000 PME. Il ne mesure pas AWS. Il n’exécute pas un test d’endurance de 30 à 60 minutes. Ces éléments restent hors périmètre de cette preuve.[1] [3]

## Résultats HTTP

| Scénario | Concurrence | Requêtes | Débit req/s | Percentile contrôlé | Latence mesurée | Cible | Erreur | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Health Customer | 5 | 50 | 579,481 | p99 | 64,998 ms | < 500 ms | 0 % | **PASS** |
| Health Opportunity | 5 | 50 | 564,634 | p99 | 16,394 ms | < 500 ms | 0 % | **PASS** |
| Opportunités admin, page de 25 | 10 | 200 | 84,521 | p95 | 234,921 ms | < 1 500 ms | 0 % | **PASS** |
| Opportunités CC scopées, page de 25 | 10 | 200 | 56,521 | p95 | 326,387 ms | < 1 500 ms | 0 % | **PASS** |
| Recherche client CC, page de 25 | 10 | 200 | 14,722 | p95 | 1 296,913 ms | < 1 500 ms | 0 % | **PASS** |
| Détail client CC | 5 | 100 | 35,589 | p95 | 282,434 ms | < 2 000 ms | 0 % | **PASS** |
| Détail opportunité CC | 5 | 100 | 93,346 | p95 | 83,800 ms | < 2 000 ms | 0 % | **PASS** |
| Explication opportunité CC | 5 | 100 | 80,920 | p95 | 92,557 ms | < 2 000 ms | 0 % | **PASS** |
| Dashboard CC, portefeuille de 2 000 PME | 2 | 20 | 0,680 | p95 informatif | 3 203,483 ms | Aucun seuil dans ce protocole | 0 % | **MESURÉ SANS SEUIL P95** |
| Dashboard agence, consolidation de 10 000 PME | 1 | 5 | 0,055 | p95 informatif | 18 906,396 ms | Aucun seuil dans ce protocole | 0 % | **MESURÉ SANS SEUIL P95** |

Les deux dashboards sont volontairement qualifiés **« mesurés sans seuil p95 »**. Leur statut technique dans le JSON signifie que le contrôle d’erreur HTTP est passé ; il ne doit pas être interprété comme une capacité de production. Le dashboard agence renvoie une agrégation de 4 943 octets, mais son temps observé proche de vingt secondes constitue un point de dimensionnement à traiter avant toute cible de production. Le dashboard CC renvoie environ 1,70 Mio pour 2 000 PME ; la pagination ou une projection plus compacte devra être évaluée avec BOA si ce volume correspond au pilote réel.

## Correction du défaut de recherche

Le run antérieur utilisait déjà les index trigrammes mais échouait encore à **2 405,998 ms au p95**. L’analyse a montré que la page par curseur exécutait en plus un `COUNT(*)` exact sur la requête scopée. Ce comptage ne participait ni à `hasMore`, ni à `nextCursor`, et le frontend ne le consommait pas. Il a été supprimé pour la liste clients ; le contrat existant autorise déjà `meta.totalCount` à être nul.[4] [5]

La pagination conserve `pageSize + 1`, le calcul de `hasMore`, le curseur suivant, les filtres et le scope backend CC/agence. Un test vérifie que la recherche d’un CC ne retourne que son propre portefeuille et que `meta.totalCount` vaut `null`.[6]

La migration 0015 installe `pg_trgm` si nécessaire et crée trois index GIN sur `customer_ref`, `legal_name` et `sector_code`.[7] Le plan final de recherche s’exécute en **6,815 ms** et utilise les trois index trigrammes. Le plan de page priorisée des opportunités s’exécute en **5,702 ms** avec `ix_opportunities_active_priority`. Le plan de scope d’un chargé de clientèle retourne 2 000 lignes en **11,157 ms** avec l’index d’affectation. Aucun deadlock n’a été observé pendant le run.[1]

## Validation des migrations

La migration a été validée sur deux bases PostgreSQL temporaires distinctes. Une base existante a été montée jusqu’à `0014_email_notifications`, puis migrée vers `0015_customer_search_performance`. Une base vierge a été migrée de `0001_initial` jusqu’à `0015_customer_search_performance`. Dans les deux cas, la révision finale, l’extension `pg_trgm` et les trois index attendus ont été contrôlés.

Le downgrade vers 0014 supprime les trois index mais conserve l’extension, afin de ne pas casser d’autres objets qui pourraient l’utiliser. Le ré-upgrade recrée correctement les trois index. Dans l’environnement de validation, `pg_trgm` est déclarée extension de confiance, mais sa création reste une opération de migration. **Les droits du compte de migration et la politique d’extensions de la base cible sont À VALIDER AVEC BOA** avant installation.

## Intégrité et reproductibilité

L’artefact JSON final est versionné avec une empreinte SHA-256 `07bc30b0f92ec1cb756ceb76e36edbca636b30f8c9c1a42c7f4fc891f7784e1f`.[1] [8] Il enregistre les volumes, limites de ressources, scénarios, percentiles cibles, débits, taux d’erreur, plans SQL et statistiques PostgreSQL.

Le champ `gitCommit` de l’artefact contient `3e3a9cf5356c3d78414c7da22629e7785c0918f8`, qui est le dernier commit disponible au démarrage du run. La mesure a été exécutée sur l’arbre de travail contenant la migration 0015, les scripts du banc et la suppression du comptage exact, puis ces fichiers et la preuve ont été préparés pour un commit atomique. Cette précision évite de présenter le parent Git comme s’il identifiait à lui seul le code mesuré.

La commande de reproduction est :

```bash
./scripts/validate-load-50k.sh
```

Elle crée une base dédiée, applique toutes les migrations, charge la fixture, démarre les trois services avec les limites documentées, exécute les mesures et copie le JSON hors du runner. Un trap préserve le code de sortie et supprime les conteneurs ainsi que la base dédiée sur succès comme sur échec, sauf demande explicite `LOAD_TEST_KEEP_DATABASE=true`. Le nettoyage final a été vérifié : aucun conteneur `boa-load-50k-*` et aucune base `boa_load_50k` ne subsistaient après le run.[2]

## Porte complète du lot

| Contrôle | Résultat |
|---|---|
| Ruff format et lint | **PASS — 132 fichiers formatés, aucune erreur** |
| mypy backend et banc de charge | **PASS — 78 fichiers backend et 1 script** |
| Tests unitaires backend | **PASS — 220 tests, 6 avertissements connus** |
| ShellCheck, Compose et Keycloak | **PASS** |
| Migration 0014 → 0015 | **PASS** |
| Migration vierge 0001 → 0015 | **PASS** |
| Downgrade 0015 → 0014 puis ré-upgrade | **PASS** |
| TypeScript | **PASS** |
| Tests frontend | **PASS — 25 tests** |
| Build Vite | **PASS** |
| Intégration Docker ML CPU-only | **PASS — 12 services sains, lineage, outcomes, scopes et absence LLM/GPU contrôlés** |
| E2E Playwright | **PASS — 19 scénarios** |
| Banc 50 000 PME | **PASS — 10 scénarios, 0 erreur HTTP** |

## Contre-revue indépendante

La contre-revue n’a trouvé aucun P0. Elle a initialement classé **P1** le nettoyage de la base, car le trap de sortie supprimait les conteneurs mais la base n’était supprimée que sur le chemin nominal. Le trap a été corrigé pour terminer les connexions et supprimer la base dédiée à chaque sortie, tout en préservant le code d’échec. Un arrêt forcé d’une exécution de contrôle a ensuite confirmé l’absence de base et de conteneur résiduels. Le constat P1 est **FERMÉ**.

La remarque P2 demandant de remplacer la formulation provisoire de contre-revue est également fermée par la présente section. La porte complète du dépôt a ensuite rendu un verdict **PASS** sur l’ensemble des contrôles ci-dessus.

## Statut bancaire du résultat

| Sujet | Statut exact |
|---|---|
| Banc reproductible et isolé | **IMPLÉMENTÉ** |
| Fixture 50 000 clients, affectations et opportunités | **PROUVÉ sur données synthétiques** |
| Seuils p99 des deux health checks et p95 des six parcours ciblés | **PASS dans l’environnement documenté** |
| Dashboards CC et agence | **MESURÉS SANS SEUIL P95 dans ce protocole** |
| Batch Rules → Features → ML sur 50 000 PME | **NON MESURÉ** |
| Endurance 30–60 minutes | **NON IMPLÉMENTÉE dans ce lot** |
| Données et labels historiques BOA | **NON DISPONIBLES / À VALIDER AVEC BOA** |
| Performance ML de production | **NON MESURÉE et non revendiquée** |
| Déploiement ou performance AWS | **BLOCKED tant qu’aucun accès autorisé n’est fourni** |
| Capacité et SLO de production | **HYPOTHÈSE À VALIDER AVEC BOA** |
| Décision de crédit | **HORS PÉRIMÈTRE** |

## Références

[1]: ../evidence/load/RESULTATS-CHARGE-50000.json "Résultats structurés du banc de charge 50 000 PME"
[2]: ../../scripts/validate-load-50k.sh "Orchestration Docker isolée du banc 50 000 PME"
[3]: ../test-plan.md "Plan de tests et critères initiaux de charge"
[4]: ../../backend/src/boa_oi/customer_api.py "API Customer et pagination backend scopée"
[5]: ../../frontend/src/api/types.ts "Contrat frontend de pagination"
[6]: ../../tests/unit/test_portfolio_api.py "Tests de scope CC et de pagination client"
[7]: ../../database/migrations/versions/0015_customer_search_performance.py "Migration des index trigrammes de recherche client"
[8]: ../evidence/load/SHA256SUMS.txt "Manifeste SHA-256 de la preuve de charge"
