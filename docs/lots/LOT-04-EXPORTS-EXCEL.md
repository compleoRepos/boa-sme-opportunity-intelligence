# Lot 04 — Exports Excel sécurisés

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Auteur :** Manus AI
**Statut global :** **PASS local représentatif / BLOCKED AWS**

## Conclusion

Le produit génère désormais de vrais classeurs `.xlsx` côté backend. Les exports couvrent les opportunités filtrées et le portefeuille PME autorisé. Le navigateur ne reconstruit aucune donnée et ne décide jamais du périmètre : Opportunity Service et Portfolio Service appliquent les affectations actives du chargé de clientèle ou de l’agence avant de créer le fichier [1] [2].

Chaque classeur contient une feuille de données et une feuille `Métadonnées`. Cette dernière porte la version de schéma, l’acteur, le périmètre, la corrélation, le nombre de lignes et l’avertissement selon lequel les informations servent uniquement au pilotage commercial. Chaque succès est rapprochable d’une entrée append-only dans `audit.audit_logs` grâce à l’empreinte SHA-256 du fichier [3].

## Résultats de validation

| Contrôle | Statut | Résultat observé |
| --- | --- | --- |
| Génération XLSX réelle | **PASS** | Le classeur s’ouvre avec `openpyxl`; les feuilles sont `Portefeuille PME` et `Métadonnées`. |
| Scope CC côté backend | **PASS** | Le fichier E2E contient 20 PME et uniquement `relationshipManagerId=rm-01`. Une tentative `rm-02` reçoit `404`. |
| Scope agence côté backend | **PASS** | Les tests refusent l’export d’un CC situé hors agence. |
| Parité des filtres Opportunity | **PASS** | L’export réutilise la liste filtrée SQL. `pageSize` et `cursor` sont refusés sur la route d’export. |
| Plafond de volume | **PASS** | Le pilote refuse plus de 10 000 lignes au lieu de tronquer silencieusement. |
| Protection contre les formules Excel | **PASS** | Les textes commençant par `=`, `+`, `-` ou `@` sont neutralisés avant écriture. |
| Proxy Gateway binaire | **PASS** | Le Gateway transmet les octets XLSX, la corrélation, le nom de fichier et l’empreinte. Il refuse un type MIME inattendu. |
| Audit d’export | **PASS** | L’empreinte du fichier E2E correspond à une entrée `EXPORT_XLSX_SUCCEEDED` de Portfolio Service. |
| Interface utilisateur | **PASS** | Les dashboards CC/agence, le portefeuille d’un CC et la page Opportunités exposent un bouton avec état de chargement et message d’erreur corrélé. |
| Tests backend | **PASS** | `197 passed`, avec six avertissements historiques non bloquants. |
| Tests frontend | **PASS** | `18 passed`; typecheck et build de production réussis. |
| E2E navigateur | **PASS** | `9 passed`, dont téléchargement via Keycloak et contrôle de la signature ZIP du `.xlsx`. |
| Régression ML | **PASS** | 500 vecteurs, 500 scores, lignée, influence réelle sur la priorité et absence de dépendance LLM/GPU confirmés. |
| Exécution AWS | **BLOCKED** | Aucun accès AWS exécutable n’est configuré dans cette session. Les connecteurs disponibles sont documentaires et l’intégration GitHub ne permet pas de lire ou configurer les secrets Actions. Aucun résultat AWS n’est revendiqué. |

## Preuve E2E du classeur

Le parcours Playwright s’est authentifié avec le persona Keycloak `rm.demo`, a vérifié le refus d’un autre portefeuille, puis a téléchargé le fichier depuis le Gateway. Le fichier obtenu mesure **8 655 octets**. Son empreinte est `5010119583099a2fd2f368b85590dfe24fc1f19a8f1bc3541e34a9cec36649e9`.

L’ouverture du classeur a produit le résultat suivant :

```json
{
  "sheets": ["Portefeuille PME", "Métadonnées"],
  "rowCount": 20,
  "relationshipManagerIds": ["rm-01"],
  "metadataRowCount": 20,
  "disclaimer": "Pilotage commercial uniquement. Les signaux et priorités ne constituent aucune décision de crédit."
}
```

PostgreSQL contient une ligne append-only associée au même hash. Elle porte `service_name=portfolio-service`, `action=EXPORT_XLSX_SUCCEEDED`, `resource_type=PORTFOLIO_EXPORT`, `result=SUCCESS` et `rows=20`.

Une revue indépendante a demandé trois corrections P1 avant commit. Le plafond Portfolio est désormais contrôlé par une requête limitée à 10 001 lignes avant la construction du payload. Le filtre `q`, qui n’avait pas de prédicat SQL, est refusé au lieu d’être ignoré. Enfin, les identifiants d’export et d’audit sont aléatoires et indépendants de la corrélation fournie par le client. Une preuve PostgreSQL avec deux téléchargements partageant `corr-reused-export-proof` a produit **deux lignes d’audit et deux `resource_id` distincts**.

## Contrats et limites

Les routes publiques sont `GET /api/v1/exports/opportunities.xlsx` et `GET /api/v1/exports/portfolio.xlsx`. La première accepte les filtres métier documentés. La seconde accepte seulement `relationshipManagerId`, qui affine le périmètre d’un responsable d’agence sans pouvoir l’élargir.

Le plafond synchrone est fixé à **10 000 lignes**. Aucun fichier n’est stocké durablement par le produit. Le classeur contient des données commerciales synthétiques du pilote et non des décisions de crédit. Un export massif asynchrone, une rétention de fichiers et une diffusion externe restent hors périmètre.

## Commandes reproductibles

```bash
ruff format --check backend/src database tests/unit
ruff check backend/src database tests/unit
mypy backend
PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings
shellcheck -x -e SC1091 scripts/*.sh
./scripts/validate.sh
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
./scripts/validate-ml-integration.sh
```

## Références

[1]: ../../backend/src/boa_oi/opportunity_api.py "Opportunity Service — filtres, scope et export XLSX"
[2]: ../../backend/src/boa_oi/portfolio_api.py "Portfolio Service — périmètre actif et export XLSX"
[3]: ../../backend/src/boa_oi/export_xlsx.py "Générateur de classeurs XLSX sécurisés"
[4]: ../../tests/e2e/export-xlsx.spec.ts "Parcours E2E de téléchargement Excel"
