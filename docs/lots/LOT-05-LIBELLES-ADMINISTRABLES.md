# Lot 05 — Libellés fonctionnels administrables

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Auteur :** Manus AI
**Statut global :** **PASS local représentatif / BLOCKED AWS**

## Conclusion

Le produit dispose désormais d’un catalogue français administrable qui ne modifie jamais les codes métier. Les textes affichés peuvent évoluer sans changer les contrats d’API, les règles, les filtres, les exports ni les historiques [1] [2].

Chaque modification crée une version justifiée. L’historique est append-only au niveau PostgreSQL. La lecture est disponible pour les utilisateurs autorisés, tandis que l’écriture et la consultation détaillée des versions sont réservées au rôle `ADMIN`.

## Résultats de validation

| Contrôle | Statut | Résultat observé |
| --- | --- | --- |
| Séparation code/libellé | **PASS** | Les clés `OPEN`, `P1`, `TRADE_FINANCE` et autres restent inchangées ; seul le texte runtime est surchargé. |
| Catalogue initial | **PASS** | La migration crée 20 entrées françaises et leur version 1. |
| Versionnement | **PASS** | Une modification exige `expectedVersion`, incrémente la version et ajoute une ligne d’historique. Une version obsolète reçoit un conflit 409. |
| Immutabilité | **PASS** | Les triggers PostgreSQL interdisent `UPDATE`, `DELETE` et `TRUNCATE` sur `config.label_catalog_versions`. |
| Unicité runtime | **PASS** | `(code, locale)` est unique, ce qui interdit une collision entre deux namespaces dans le dictionnaire frontend. |
| RBAC | **PASS** | Les rôles métier lisent le catalogue. Seul `ADMIN` peut modifier un libellé ou consulter son historique détaillé. |
| Repli frontend | **PASS** | Le dictionnaire embarqué reste utilisé si le catalogue runtime n’est pas encore chargé. |
| Interface | **PASS** | `/back-office/libelles` affiche namespace, code, texte, version, état et justification. |
| Migration existante | **PASS** | `0012→0013`, 20 libellés et 20 créateurs renseignés. |
| Migration vierge | **PASS** | `0001→0013`, 20 libellés et 20 créateurs renseignés. |
| Protections PostgreSQL | **PASS** | `validate-label-catalog.sh` confirme le refus de `UPDATE`, `DELETE`, `TRUNCATE` et d’une collision de code. |
| Tests backend | **PASS** | `204 passed`, avec six avertissements historiques non bloquants. |
| Tests frontend | **PASS** | `20 passed`; typecheck et build de production réussis. |
| E2E navigateur | **PASS** | `10 passed`, dont modification et restauration du libellé `OPEN`. |
| Régression ML | **PASS** | La lignée, l’influence du score, les 500 vecteurs/scores et l’absence de dépendance LLM/GPU restent confirmées. |
| Exécution AWS | **BLOCKED** | Aucun accès AWS exécutable n’est disponible dans cette session. Aucun résultat cloud n’est revendiqué. |

## Preuve de versionnement

Le parcours Keycloak administrateur a modifié puis restauré le libellé `OPEN`. L’historique PostgreSQL a conservé chaque étape avec l’acteur et la justification. Une interruption de porte E2E a aussi été récupérée par une version supplémentaire, sans réécrire l’historique.

```text
v1  Ouvert                  migration-0013  Catalogue français initial du pilote
v2  À traiter — pilote      admin.demo      Validation E2E du catalogue versionné
v3  Ouvert                  admin.demo      Restauration après validation E2E
...
```

Le test final est réexécutable : il lit la version initiale, crée une version temporaire, puis restaure le texte d’origine dans la version suivante.

## Limites

Le pilote gère uniquement la locale `fr-FR`. Le catalogue initial couvre les termes les plus visibles. Un administrateur ne peut pas créer un nouveau code depuis l’interface : cette restriction protège les contrats métier. L’ajout d’un code reste une évolution applicative ou de migration.

La mise à jour est immédiatement visible après invalidation du cache React Query. Le dictionnaire local embarqué reste une mesure de résilience ; il ne constitue pas une deuxième source de gouvernance.

## Commandes reproductibles

```bash
ruff format --check backend/src database tests/unit
ruff check backend/src database tests/unit
mypy backend
PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings
shellcheck -x -e SC1091 scripts/*.sh
./scripts/validate.sh
./scripts/validate-label-catalog.sh
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
./scripts/validate-ml-integration.sh
```

## Références

[1]: ../../backend/src/boa_oi/rule_management_api.py "Rule Management — catalogue et versions de libellés"
[2]: ../../database/migrations/versions/0013_label_catalog.py "Migration du catalogue de libellés"
[3]: ../../frontend/src/features/backoffice/BackOfficePages.tsx "Écran administrateur des libellés"
[4]: ../../tests/e2e/labels.spec.ts "Parcours E2E de versionnement et restauration"
