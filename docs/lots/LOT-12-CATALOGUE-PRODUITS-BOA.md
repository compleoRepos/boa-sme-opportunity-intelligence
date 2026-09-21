# Lot 12 — Catalogue produit public BOA et garde-fous Rule Studio

**Date :** 20 septembre 2026

**Branche :** `feat/pilot-readiness`

**Périmètre :** intégration sélective du kit UX, catalogue indicatif, Product Service, règles, migration et preuves

**Statut migration locale :** **PASS**

**Statut catalogue/API/chaîne métier :** **PASS**

**Statut release :** **BLOCKED_IMAGE_CVES**

**AWS :** **HORS PÉRIMÈTRE — aucune action de déploiement ou de configuration**

## 1. Résultat exécutif

Le lot intègre un référentiel indicatif de **28 produits visibles sur les pages publiques de BANK OF AFRICA**, répartis en **7 familles internes**. Cette source exécutable commune alimente le seed synthétique, le mock bancaire, le Product Service, l’interface catalogue, l’éditeur Rule Studio et l’hydratation des recommandations Opportunity.[1]

Le catalogue ne constitue pas un référentiel commercial BOA validé. Les familles, audiences, critères, montants, durées, tarifs et disponibilités demeurent **HYPOTHÈSE À VALIDER AVEC BOA**. Les informations structurées servent à une démonstration locale sur données synthétiques et ne sont pas évaluées comme décision d’éligibilité. Le produit ne prend aucune décision de crédit.

Le correctif ferme également un défaut P1 : une règle Rule Studio historique pouvait référencer un ancien code générique que l’Opportunity Engine ignorait silencieusement, produisant une recommandation vide. La migration met à jour uniquement les configurations synthétiques connues créées par `demo-data-generator`, avec rollback et checksum exacts. Les règles utilisateur ou BOA ne sont pas réécrites. Les nouvelles écritures avec code inconnu sont refusées en `422`; une ancienne règle publiée obsolète rencontrée à l’exécution provoque un `409` fail-closed au lieu d’une persistance partielle.[2][3]

## 2. Statuts vérifiables

| Capacité | Statut | Preuve ou limite |
|---|---|---|
| Référentiel 28 produits / 7 familles | **IMPLÉMENTÉ** | source unique `backend/src/boa_oi/catalog.py`; détail et provenance dans la documentation catalogue[1] |
| Provenance publique | **DOCUMENTÉE / À REVALIDER** | 28 URL `https://www.bankofafrica.ma/...`; revue ponctuelle du 20 septembre 2026, sans garantie de disponibilité ou d’applicabilité future[1] |
| Catalogue contractuel BOA | **NON IMPLÉMENTÉ** | aucun référentiel contractuel ni validation produit BOA n’a été fourni |
| Product Service `family`, `description`, `sourceUrl` | **IMPLÉMENTÉ** | migration `0018`, modèles et contrat API[2][4] |
| Product Service readiness | **FAIL-CLOSED** | `/ready=503` si les 28 produits gouvernés ne sont pas actifs et cohérents ; le seed est une étape de déploiement obligatoire |
| Filtre et tri `family` | **IMPLÉMENTÉ / TESTÉ** | filtre SQL serveur réel ; `UNKNOWN_FILTER` n’est plus produit pour `family` |
| Isolation des routes client produit | **IMPLÉMENTÉ / TESTÉ** | Gateway puis Product Service vérifient le scope via Customer Service ; un CC ne peut pas contourner le périmètre par appel interne |
| Lacune par famille | **IMPLÉMENTÉ** | une famille est couverte dès qu’un produit est détenu ; les recommandations restent des produits précis |
| Rule Studio — nouveaux codes inconnus | **REFUSÉS** | `422 RULE_VALIDATION_FAILED`; contrôle à la création, modification et validation[4] |
| Rule Studio — ancienne règle publiée inconnue | **FAIL-CLOSED** | `409 UNKNOWN_RULE_PRODUCT_CODES`; aucune recommandation vide ou partielle persistée[4] |
| Produit connu absent ou inactif lors de la génération | **FAIL-CLOSED** | `409 UNAVAILABLE_RULE_PRODUCT_CODES` avant persistance |
| Import produit ou détention hors référentiel | **REFUSÉ** | code inconnu, divergence famille/URL, produit absent ou inactif : `422` avant toute écriture ; aucune extension implicite du catalogue pilote |
| Migration des règles techniques synthétiques | **PASS** | quatre mappings précis, bornés à `created_by='demo-data-generator'` et `version='1'`[3] |
| Migration Rule Studio synthétique | **PASS** | `SYNTHETIC_GROWTH_REVIEW:v1`, action dénormalisée et checksum recalculés ; rollback exact[3] |
| Préservation des règles utilisateur | **PASS** | fixture contrôlée inchangée sur upgrade et downgrade[3] |
| Migration PostgreSQL vierge `0001→0018` | **PASS** | base temporaire Docker isolée[3] |
| Migration `0017→0018→0017→0018` | **PASS** | colonnes catalogue, largeur `rule_version` 80/30 et données synthétiques contrôlées[3] |
| Priorité commerciale | **RULES_ONLY** | `rules_weight=1`, `ml_weight=0`; le ML reste `POC_SHADOW` |
| Décision de crédit | **ABSENTE** | signaux et recommandations à examiner ; aucune décision d’octroi, notation de risque ou probabilité de défaut |
| Déploiement AWS | **NON EXÉCUTÉ / HORS PÉRIMÈTRE** | exigence explicite ; aucune ressource, OIDC AWS ou Terraform appliqué |

## 3. Catalogue et familles

| Famille interne | Produits actifs |
|---|---:|
| `INVESTMENT_FINANCING` | 6 |
| `WORKING_CAPITAL_FACILITY` | 5 |
| `OVERDRAFT` | 2 |
| `TRADE_FINANCE` | 6 |
| `CASH_MANAGEMENT` | 6 |
| `TERM_DEPOSIT` | 2 |
| `LIQUIDITY_INVESTMENT` | 1 |
| **Total** | **28** |

La famille est une taxonomie interne de raisonnement, non une classification BOA approuvée. Pour le témoin synthétique `SME-00035` au `2026-09-30`, le protocole contrôle six lacunes `TRADE_FINANCE` et des recommandations précises telles que `BOA_CREDIT_DOCUMENTAIRE`, `BOA_FINANCEMENT_IMPORTATIONS` et `BOA_PREFINANCEMENT_EXPORT`. Ce témoin ne mesure aucune adéquation commerciale réelle.[2]

## 4. Migration et gouvernance des règles

La migration additive `0018_product_catalog` ajoute `family`, `description` et `source_url` à `product.products`, puis élargit `opportunity.opportunities.rule_version` et `opportunity.decision_audit.rule_version` de 30 à 80 caractères. Comme `0001_initial` construit historiquement ses tables depuis la metadata ORM courante, il retire explicitement ces éléments futurs et restaure la largeur 30 afin qu’une base vierge traverse réellement la même séquence.[3][5]

Le catalogue n’est volontairement pas inséré comme donnée commerciale par Alembic. La séquence de déploiement exécute le seed gouverné idempotent après migration. Product Service refuse ensuite la readiness si l’ensemble actif ne correspond pas exactement aux 28 codes, familles et URL de la source exécutée. Opportunity échoue également avant persistance si un produit configuré est absent ou inactif. Une migration seule ne peut donc pas donner un état faussement exploitable.

Deux périmètres synthétiques sont migrés : les quatre `opportunity.opportunity_rules` techniques de version `1`, et la règle Rule Studio déterministe `SYNTHETIC_GROWTH_REVIEW:v1`. La seconde mise à jour synchronise `rule.rule_versions.configuration_json`, son checksum canonique et `rule.rule_actions.product_codes_json`. Le downgrade ne restaure les anciens codes que si la valeur précise attendue est encore présente, ce qui évite d’écraser une modification ultérieure.

Une règle contrôlée par un utilisateur reste inchangée. Cette préservation est intentionnelle : le dépôt ne peut pas décider de traduire une configuration BOA future sans validation métier. La protection résiduelle est fail-closed à l’écriture et à la consommation.[3]

## 5. Chaîne métier prouvée

Le protocole [`validate-product-catalog.sh`](../../scripts/validate-product-catalog.sh) démarre ou reconstruit les services concernés, obtient un jeton de service court, puis exécute les contrôles suivants :

1. lecture de 28 produits actifs via Gateway, métadonnées et sources présentes ;
2. filtre serveur `family=TRADE_FINANCE`, exactement six résultats ;
3. calcul des lacunes produit de `SME-00035` ;
4. présence ou recalcul des métriques Analytics, puis recalcul des Signals ;
5. génération Opportunity avec règles de poids `1` et ML de poids `0` ;
6. recommandations Trade Finance portant exclusivement des codes précis actifs ;
7. absence de règle active avec ancien code générique ou code absent du catalogue ;
8. refus API d’une nouvelle règle Rule Studio avec code inconnu ;
9. readiness Product Service sur le catalogue exact ;
10. version Alembic `0018_product_catalog` et largeur `rule_version=80`.

Le résultat JSON final porte un digest SHA-256 des sources pertinentes. Il ne constitue ni une mesure de performance, ni une validation produit BOA, ni une preuve de production.[2]

Le run final `product-catalog-20260921T000906Z-3020325`, terminé le 21 septembre 2026 à 00:11:37 UTC, prouve 28 produits actifs, 7 familles, 6 produits et 6 lacunes Trade Finance pour `SME-00035`, le rejet d’une détention vers un code inconnu, une génération `COMPLETED`, `rulesWeight=1` et `mlWeight=0`. Le run migration `product-catalog-migration-20260921T000034Z`, terminé le 21 septembre 2026 à 00:00:34 UTC, prouve les quatre cycles vierge/existant/downgrade/ré-upgrade. Les preuves JSON et la capture sont couvertes par le manifeste SHA-256 vérifié.[2][3][9][10]

La première relance finale a également révélé une course de visibilité entre les endpoints synchrones : Analytics pouvait annoncer `COMPLETED` alors que le commit de sa dépendance SQLAlchemy n’était pas encore observable par Signals/Opportunity. Pour un lot tardif, `SME-00451` a donc été refusé à juste titre comme historique insuffisant malgré des snapshots ensuite visibles. Analytics, Signals et Opportunity effectuent désormais leur commit avant de renvoyer `COMPLETED`. La relance suivante a confirmé cette correction puis mis en évidence l’expiration possible du jeton court entre Analytics, Signals et Opportunity lorsqu’une étape dure longtemps. `run-pipeline.sh` obtient désormais un jeton frais avant chaque appel interne, et non seulement avant chaque lot. Aucun délai arbitraire, retry masquant ou affaiblissement d’autorisation n’est ajouté.

## 6. Interface et démonstration

L’écran `/produits` présente le caractère **indicatif** du référentiel, groupe les produits par famille, expose les codes stables et lie chaque carte à sa page publique. Le sélecteur Rule Studio utilise les mêmes produits et familles. Le scénario Playwright dédié vérifie le titre prudent, 28 cartes, 7 sections, les 6 produits Trade Finance et les 28 liens vers le domaine public BOA. Une capture réelle 1440×900 de la stack locale synthétique est conservée avec les preuves du lot.[9]

Le correctif de pourcentage du panneau de simulation et le script optionnel [`record-demo.cjs`](../../scripts/record-demo.cjs) ont été portés séparément depuis le kit UX. Le script vidéo cible uniquement la stack locale synthétique et ne remplace ni les E2E ni les preuves JSON.[6]

## 7. Porte locale finale

| Contrôle | Résultat |
|---|---:|
| Ruff format et lint | **PASS** |
| mypy | **PASS** |
| pytest backend | **PASS**, 259 tests ; commande autonome `APP_ENV=test PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings` |
| TypeScript | **PASS** |
| Vitest | **PASS**, 27 tests / 7 fichiers |
| Vite build | **PASS** |
| validation Compose/Keycloak/ShellCheck | **PASS** |
| migration isolée | **PASS**[3] |
| pipeline Docker 500 PME | **PASS**, 20 lots de 25, tous `COMPLETED`, 500 clients `POC_SHADOW`, priorité rules-only |
| Playwright | **PASS**, 20/20 en 3,7 minutes, dont catalogue et contournement CC par `customerId`; cas, statuts et durées versionnés[11] |
| protocole catalogue post-E2E | **PASS**, run `product-catalog-20260921T000906Z-3020325`[2] |
| FAQ comité | **PASS**, 30 questions |
| scénario de démonstration | **PASS**, 5 actes |
| manifestes SHA-256 catalogue | **PASS**, quatre fichiers vérifiés depuis la racine par `sha256sum -c docs/evidence/catalog/SHA256SUMS.txt`[10] |

## 8. CI distante et release

Le run GitHub Actions `35538673248` du lot 11 n’est pas PASS : il s’est terminé **CANCELLED** lorsque le job `compose-e2e-and-operations` a atteint sa limite de 60 minutes pendant Playwright. Les validations infrastructure, backend, frontend, sécurité et builds Docker avaient passé ; les étapes rollback, backup et readiness n’ont pas été exécutées dans ce run. Le timeout du job est porté à 120 minutes, borne ferme cohérente avec la durée réellement observée, sans ignorer les échecs.

Cette correction ne lève pas le statut release **`BLOCKED_IMAGE_CVES`** du lot 11. La sécurité locale a bien exécuté les scans, mais les images externes contiennent encore des vulnérabilités `HIGH`/`CRITICAL`. Aucun statut `READY` ou capacité de production n’est revendiqué.[7]

## 9. Contre-revue indépendante P0/P1

Les deux passes de contre-revue indépendante n’ont trouvé aucun P0. Elles ont néanmoins signalé des P1 avant clôture : scope client non réappliqué dans Product Service, catalogue potentiellement non matérialisé après migration, filtrage silencieux d’un produit actif manquant, branche de reranking non-shadow encore présente, import produit divergent, détention importée sans validation de son produit et artefacts antérieurs au worktree final.

Les correctifs rendent Product Service non ready sans seed exact, réappliquent le scope objet côté service, refusent les produits et détentions inconnus, absents, inactifs ou divergents avant toute écriture, échouent avant persistance sur produit absent/inactif et suppriment toute voie de calcul hybride : le helper refuse désormais tout mode autre que `POC_SHADOW` ou tout poids différent de règles `1` / ML `0`. Les statuts synchrones `COMPLETED` sont commit-before-response. Les preuves JSON sont régénérées après ces modifications. La génération batch Opportunity reste réservée aux rôles globaux `ADMIN`/`SERVICE`; un CC ou un responsable d’agence reçoit `403` et ne peut pas l’utiliser pour contourner son portefeuille.

## 10. Limites non négociables

Toutes les données clients, transactions, détentions et outcomes de ce lot sont synthétiques. Les pages publiques ne fournissent pas une politique d’éligibilité exécutable ni une validation commerciale BOA. Les nombres du protocole décrivent une fixture locale, pas une population bancaire.

Le ML est classique, CPU-only, sans LLM ni GPU. Il reste `POC_SHADOW` et n’influence ni l’ordre, ni l’éligibilité, ni la recommandation. Le produit reste une aide commerciale explicable et ne prend aucune décision de crédit. La production, les données BOA, les adaptateurs SI réels, l’homologation sécurité et toute cible d’infrastructure sont **NON IMPLÉMENTÉS / À VALIDER AVEC BOA**.

## Références

[1]: ../catalogue-produits.md "Référentiel indicatif et 28 sources publiques"
[2]: ../evidence/catalog/RESULTATS-CATALOGUE-PRODUITS.json "Preuve catalogue, filtres, lacunes et chaîne métier"
[3]: ../evidence/catalog/RESULTATS-MIGRATION-CATALOGUE.json "Preuve migration PostgreSQL vierge, existante et rollback"
[4]: ../api.md "Contrats Product Service, Rule Studio et erreurs fail-closed"
[5]: ../data-model.md "Modèle relationnel et migration 0018"
[6]: ../demo-scenario.md "Scénario de démonstration en cinq actes"
[7]: ./LOT-11-INDUSTRIALISATION-EXPLOITATION.md "Industrialisation, sécurité et blocage release"
[8]: https://github.com/compleoRepos/btp-suivi-projets/actions/runs/35538673248 "Run CI distant annulé par timeout"
[9]: ../evidence/catalog/CATALOGUE-PRODUITS-1440x900.png "Capture réelle du catalogue produit à 1440×900"
[10]: ../evidence/catalog/SHA256SUMS.txt "Manifestes SHA-256 vérifiés du lot catalogue"
[11]: ../evidence/catalog/RESULTATS-PLAYWRIGHT-CATALOGUE.json "Résultats détaillés des vingt E2E Playwright"
