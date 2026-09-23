# Rapport de tests — Financial Intelligence

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Qualification

Les validations portent sur la branche `feat/financial-intelligence-api`, sur données synthétiques et sans connexion BOA. Elles prouvent le comportement du POC local ; elles ne constituent ni une homologation sécurité, ni une preuve de performance bancaire de production.

## Portes locales

| Contrôle | Résultat mesuré | Statut |
|---|---:|---|
| Ruff format et lint | backend, migrations, tests et scripts Python | **PASS** |
| mypy | `backend/src` | **PASS** |
| pytest | 334 tests, 9 avertissements | **PASS** |
| TypeScript | compilation stricte frontend | **PASS** |
| Vitest | 43 tests dans 12 fichiers | **PASS** |
| Vite | build de production | **PASS** |
| ShellCheck | scripts applicatifs et infrastructure | **PASS** |
| Docker Compose config | configuration résolue | **PASS** |

Les avertissements pytest proviennent notamment de scikit-learn sur les données de démonstration ; ils ne sont pas interprétés comme une validation de performance ML.

## Autorisation, non-fuite et contrat

Les tests backend couvrent la résolution du Consumer à partir du sujet et du client OIDC, l’intersection des scopes, les grants actifs/expirés/révoqués, les memberships point-in-time, l’isolation entre Funds, l’uniformité du `404`, le rejet de `consumerId`, l’audit append-only, l’identité technique aval, la minimisation des DTO, les réponses partielles et la conservation de la lineage règles/ML shadow. Ils refusent explicitement les rôles `ADMIN`/`SERVICE`, y compris combinés à `EXTERNAL_CONSUMER`, le client absent, le client incohérent, le scope joker et une autre finalité. Les non-régressions vérifient qu’un membership futur ne fuit pas, qu’un membership `INACTIVE` reste lisible avant `valid_until`, puis qu’il est refusé après cette borne. Elles prouvent aussi qu’un score futur ou expiré, une opportunité de priorité future ou expirée et un snapshot de visibilité futur sont exclus lorsqu’une date est fournie, qu’une opportunité expirée est également éliminée de la projection FI par défense en profondeur, qu’une ligne Signal/Opportunity hors fenêtre est éliminée localement, que `NOT_IMPLEMENTED` rend la réponse partielle, qu’une source Portfolio indisponible ne produit aucune fausse attestation ML et qu’un payload Portfolio mal typé, incomplet, non shadow ou influencé par le ML est refusé en `502 DEPENDENCY_INVALID_RESPONSE`.

Les six parcours Playwright FI utilisent Keycloak avec Authorization Code + PKCE. Ils couvrent l’absence de token, le refus du rôle `ADMIN`, le refus du client technique `SERVICE` obtenu en `client_credentials`, le catalogue et le drill-down Fonds A, la seconde page `offset`, le rejet du paramètre `cursor` non documenté, la tentative d’accès au Fonds B, l’isolation Fonds B, le grant expiré, le scope manquant, le point-in-time, la minimisation, la lineage, la gouvernance ML vérifiée, les statuts Signal/Opportunity non historisés et les captures desktop/mobile. Le résultat détaillé se trouve dans `docs/evidence/financial-intelligence/RESULTATS-E2E-FI.json`.

## Migrations et privilèges

La matrice PostgreSQL 16 vérifie le cycle administrateur complet, `0020→0021`, `0021→0020`, le ré-upgrade, le refus du downgrade destructif avec données, le moindre privilège runtime, le refus des mutations DML directes `UPDATE`, `DELETE` et `TRUNCATE` sur l’audit au runtime comme au propriétaire administratif, y compris après positionnement de l’ancien GUC de contournement, le refus en base d’un grant Consumer–Portfolio incohérent, d’un grant sans client, d’une finalité différente et d’un membership `INACTIVE` sans `valid_until`. Elle ne prétend pas résister à un DBA propriétaire qui altérerait les triggers ; séparation de rôles et WORM externe restent à mettre en œuvre pour la cible BOA. Le résultat détaillé se trouve dans `docs/evidence/financial-intelligence/RESULTATS-MIGRATIONS-FI.json`.

Les digests de provenance des preuves runtime, migration et sécurité sont réconciliés par `docs/evidence/financial-intelligence/SOURCE-MANIFEST-FI.json`. Ce manifeste liste le périmètre, chaque chemin et son SHA-256, l’algorithme d’agrégation et la révision fonctionnelle.

## Performance

Le benchmark effectue cinq mesures pour 10, 50, 100 et 500 PME, soit 20 requêtes mesurées, contrôle le nombre d’appels interservices et mesure le rendu dashboard. Les quatre seuils locaux sont **PASS** sur `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`; le P95 500 PME est de 125,042 s. Le service FI atteint 286,5 MiB sur 320 MiB, soit 89,53 % : la marge du profil local est faible, sans arrêt du conteneur pendant les 20 mesures. Le test confirme aussi la gouvernance fail-closed : `VERIFIED` pour 10 PME, `UNAVAILABLE` avec mode/poids nuls pour 50, 100 et 500 PME. Les P50/P95 et ressources sont documentés dans le plan de capacité et dans les artefacts JSON dédiés. Tous les seuils restent une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Limites

La CI GitHub n’est pas assimilée aux validations locales. Le test de charge est mono-nœud, mono-consommateur et préchauffé. Les tests n’utilisent aucune donnée bancaire réelle, aucun LLM et aucun GPU. La politique ML reste `POC_SHADOW`, avec une priorité opérationnelle `RULES_ONLY` et un poids ML maximal nul ; l’API n’atteste ces métadonnées que lorsque Portfolio les vérifie.
