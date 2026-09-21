# Référentiel indicatif de produits BANK OF AFRICA

**Date de vérification des pages publiques :** 20 septembre 2026.
**Périmètre :** démonstration locale et pilote préparatoire ; aucun référentiel contractuel BOA n'a été fourni.

> **HYPOTHÈSE À VALIDER AVEC BOA.** Les familles internes, l'association aux segments, les critères d'éligibilité, les montants et les durées ne deviennent pas des règles commerciales ou de crédit par leur présence dans ce fichier. La source faisant foi reste la documentation validée par BOA. Le produit ne prend aucune décision de crédit.

La source exécutable unique est [`backend/src/boa_oi/catalog.py`](../backend/src/boa_oi/catalog.py). Le seed synthétique, l'adaptateur bancaire mock et les tests l'importent ; le Product Service expose `family`, `description` et `sourceUrl` après la migration [`0018_product_catalog`](../database/migrations/versions/0018_product_catalog.py). Les 28 URL ont été contrôlées comme accessibles et cohérentes avec le nom et la nature générale du produit. Ce constat ponctuel ne garantit ni disponibilité future des pages ni applicabilité contractuelle.

## Modèle de familles

Le moteur calcule une lacune par **famille** : la détention d'un produit d'une famille évite de présenter cette famille comme absente. Les règles recommandent ensuite des produits précis. L'ordonnancement commercial demeure `RULES_ONLY`; le score ML reste une observation `POC_SHADOW` sans influence.

| Famille interne | Libellé | Produits |
|---|---|---:|
| `INVESTMENT_FINANCING` | Financement de l'investissement | 6 |
| `WORKING_CAPITAL_FACILITY` | Financement du cycle d'exploitation | 5 |
| `OVERDRAFT` | Avances et découverts | 2 |
| `TRADE_FINANCE` | Opérations à l'international | 6 |
| `CASH_MANAGEMENT` | Gestion des flux et de la trésorerie | 6 |
| `TERM_DEPOSIT` | Placements à taux garanti | 2 |
| `LIQUIDITY_INVESTMENT` | Placements en OPCVM | 1 |

## Produits et provenance publique

| Famille | Produit | Code stable | Audience relevée | Description prudente | Source officielle |
|---|---|---|---|---|---|
| Financement de l'investissement | **Crédit MLTD Direct** | `BOA_CREDIT_MLTD_DIRECT` | `ENTERPRISE` | Crédit à moyen et long terme pour l'acquisition de terrains, locaux, fonds de commerce, constructions et équipements ; jusqu'à 70 % de l'investissement sur 7 à 12 ans selon le type de crédit. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/credit-moyen-et-long-terme/credit-mltd-direct) |
| Financement de l'investissement | **Financement des Entreprises by BANK OF AFRICA** | `BOA_FINANCEMENT_ENTREPRISES` | `SMALL`, `MEDIUM`, `ENTERPRISE`, `PROFESSIONAL` | Solutions et lignes de financement destinées au démarrage, au développement ou à l'extension des activités d'entreprise. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/credit-moyen-et-long-terme/financement-des-entreprises-bank-africa) |
| Financement de l'investissement | **Bail Entreprise** | `BOA_BAIL_ENTREPRISE` | `ENTERPRISE` | Crédit-bail mobilier et immobilier finançant jusqu'à 100 % du montant hors taxes (70 000 à 5 000 000 DH), sur 60 mois pour le mobilier et 120 mois pour l'immobilier, avec option de rachat en fin de contrat. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/leasing/bail-entreprise) |
| Financement de l'investissement | **Istitmar (Maroc PME)** | `BOA_ISTITMAR_MAROC_PME` | `SMALL` | Cofinancement des investissements des très petites et petites entreprises (chiffre d'affaires jusqu'à 200 MDH) avec une prime d'investissement de 20 à 30 % du coût du projet, octroyée par Maroc PME. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/financement/istitmar-maroc-pme) |
| Financement de l'investissement | **CAP Energie** | `BOA_CAP_ENERGIE` | `ENTERPRISE` | Financement de projets d'efficacité énergétique, d'énergies renouvelables, d'économie d'eau et de gestion durable des terres : crédit ou bail jusqu'à 100 % de l'investissement, assistance technique et subvention de 10 à 15 %, sur 10 à 12 ans. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/financement-de-lefficacite-energetique/cap-energie) |
| Financement de l'investissement | **Daman Istitmar** | `BOA_DAMAN_ISTITMAR` | `ENTERPRISE` | Financement de projets d'investissement adossé à un dispositif de garantie. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/credit-avec-garanties-dorganismes-etatique/daman-istitmar) |
| Financement du cycle d'exploitation | **Escompte Commercial Maroc** | `BOA_ESCOMPTE_COMMERCIAL_MAROC` | `ENTERPRISE` | Avance de trésorerie contre remise d'effets de commerce avant leur échéance. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/credit-descompte/escompte-commercial-maroc) |
| Financement du cycle d'exploitation | **Factor** | `BOA_FACTOR` | `ENTERPRISE` | Affacturage : financement immédiat des créances commerciales, garantie contre les impayés et externalisation du recouvrement ; réservé aux entreprises ayant au moins un an d'activité et 2 MDH de chiffre d'affaires. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/supply-chain/factor) |
| Financement du cycle d'exploitation | **SCF by BANK OF AFRICA** | `BOA_SCF` | `ENTERPRISE` | Plateforme digitale de Supply Chain Finance : financement des fournisseurs d'un donneur d'ordres avant l'échéance de leurs factures. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/supply-chain/scf-bank-africa) |
| Financement du cycle d'exploitation | **Damane Atassyir** | `BOA_DAMANE_ATASSYIR` | `ENTERPRISE` | Produit de garantie couvrant jusqu'à 60 % des crédits de fonctionnement (plafond 10 MDH par opération) avec une commission réduite, en alternative au nantissement. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/credit-avec-garanties-dorganismes-etatique/damane-atassyir) |
| Financement du cycle d'exploitation | **Avance sur marché nanti** | `BOA_AVANCE_MARCHE_NANTI` | `ENTERPRISE` | Avance de trésorerie adossée à une créance sur marché public ou semi-public nanti. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/avance-sur-marche-nanti) |
| Avances et découverts | **Crédit de campagne** | `BOA_CREDIT_CAMPAGNE` | `ENTERPRISE` | Facilité de caisse adaptée aux activités périodiques et saisonnières ; la durée varie selon la campagne et se situe généralement entre 6 et 12 mois. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/credit-de-campagne) |
| Avances et découverts | **Crédit relais** | `BOA_CREDIT_RELAIS` | `ENTERPRISE` | Financement transitoire dans l'attente d'une rentrée de fonds certaine. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/credit-relais) |
| Opérations à l'international | **Crédit documentaire** | `BOA_CREDIT_DOCUMENTAIRE` | `ENTERPRISE` | Sécurisation des paiements à l'import et à l'export : paiement garanti contre remise des documents d'expédition. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/reglement-linternational/credit-documentaire) |
| Opérations à l'international | **Lettre de crédit stand-by** | `BOA_LC_STANDBY` | `ENTERPRISE` | Garantie de paiement en couverture d'une transaction internationale. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/reglement-linternational/lettre-de-credit-stand) |
| Opérations à l'international | **Financement des Importations** | `BOA_FINANCEMENT_IMPORTATIONS` | `ENTERPRISE` | Ligne de crédit permettant de régler les importations sans déséquilibrer la trésorerie et en optimisant la rotation des stocks. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/financement-des-importations) |
| Opérations à l'international | **Préfinancement à l'exportation** | `BOA_PREFINANCEMENT_EXPORT` | `ENTERPRISE` | Ligne de crédit finançant le cycle de production des exportateurs (matières premières, stockage, exploitation) jusqu'à six mois, prorogeable. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/prefinancement-lexportation) |
| Opérations à l'international | **Mobilisation de créances sur l'étranger** | `BOA_MOBILISATION_CREANCES_ETRANGER` | `ENTERPRISE` | Avance immédiate sur les créances en devises des exportateurs qui accordent des délais de paiement à leurs acheteurs. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/mobilisation-de-creances-sur-letranger) |
| Opérations à l'international | **Compte en devises** | `BOA_COMPTE_DEVISES` | `ENTERPRISE` | Compte pour gérer les opérations en devises des entreprises exportatrices : virements et encaissements de l'étranger, moyens de paiement internationaux. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/gerer-mes-comptes-et-package/compte-en-devises) |
| Gestion des flux et de la trésorerie | **Pack Business PME** | `BOA_PACK_BUSINESS_PME` | `SMALL`, `MEDIUM` | Forfait mensuel regroupant compte entreprise, carte business internationale, banque en ligne et un forfait de services, avec exonération de commissions. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/pack-dedie/pack-business-pme) |
| Gestion des flux et de la trésorerie | **Business Online** | `BOA_BUSINESS_ONLINE` | `ENTERPRISE` | Portail de banque à distance des entreprises, avec applications mobiles. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises) |
| Gestion des flux et de la trésorerie | **Virement de masse** | `BOA_VIREMENT_MASSE` | `ENTERPRISE` | Exécution de virements multiples ou automatisés, notamment pour les salaires et fournisseurs. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/moyens-de-paiement/virement-de-masse) |
| Gestion des flux et de la trésorerie | **Prélèvement de masse** | `BOA_PRELEVEMENT_MASSE` | `ENTERPRISE` | Encaissement automatisé des créances récurrentes par prélèvement en volume. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/moyens-de-paiement/prelevement-de-masse) |
| Gestion des flux et de la trésorerie | **Ramassage de fonds** | `BOA_RAMASSAGE_FONDS` | `ENTERPRISE` | Collecte et transport sécurisés des espèces par des prestataires qualifiés. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/gestion-de-tresorerie/ramassage-de-fonds) |
| Gestion des flux et de la trésorerie | **Cash Pooling** | `BOA_CASH_POOLING` | `LARGE`, `ENTERPRISE` | Centralisation de la trésorerie des entreprises multi-comptes ou multi-filiales pour éliminer les découverts et optimiser les intérêts. | [Page BOA](https://www.bankofafrica.ma/fr/entreprises/gestion-de-tresorerie/cash-pooling) |
| Placements à taux garanti | **Dépôt à terme** | `BOA_DEPOT_A_TERME` | `PROFESSIONAL` | Placement bloqué sur 1, 3, 6, 12 ou 24 mois à taux garanti, sans frais de souscription, de gestion ni de clôture, avec possibilité d'avance. | [Page BOA](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/depot-terme) |
| Placements à taux garanti | **Bon de caisse** | `BOA_BON_DE_CAISSE` | `PROFESSIONAL` | Placement à durée fixe de 1, 3, 6, 12 ou 24 mois, rémunéré par des intérêts nets, à partir de 5 000 DH, avec possibilité d'avance. | [Page BOA](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/bon-de-caisse) |
| Placements en OPCVM | **OPCVM** | `BOA_OPCVM` | `PROFESSIONAL` | Placement en portefeuilles collectifs de valeurs mobilières gérés par des professionnels, permettant de diversifier l'épargne. | [Page BOA](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/opcvm) |

## Données et usages

Les anciennes références génériques du prototype restent en base en statut inactif lorsque le seed synthétique est rejoué, afin de préserver les clés historiques. La migration `0018` transforme les recommandations des seules règles techniques et Rule Studio synthétiques connues, identifiées par `demo-data-generator`, et recalcule le checksum de la version Rule Studio. Elle ne réécrit aucune configuration utilisateur ou BOA. Les nouvelles règles avec un code absent du catalogue sont refusées ; une règle publiée obsolète rencontrée par Opportunity provoque une erreur explicite et aucune recommandation partielle n’est persistée.

La commande ci-dessous met à jour les 28 produits du référentiel et régénère uniquement les détentions créées par `demo-data-generator`; elle ne supprime pas les détentions importées par un autre acteur.

```bash
PYTHONPATH=backend/src:. python database/seed/generate.py --database-url "$DATABASE_URL" --products-only
```

La migration `0018` reste une migration de schéma et de compatibilité des règles ; elle ne se substitue pas à cette matérialisation gouvernée. Product Service retourne `503 PRODUCT_CATALOG_NOT_READY` sur `/ready` si les 28 codes ne sont pas tous actifs avec la famille et l’URL attendues, ou si un code actif non gouverné est présent. L’import admin refuse également les codes inconnus, les divergences de famille ou de provenance et toute détention vers un produit inconnu, absent ou inactif, avant toute écriture du lot. Ainsi, une base migrée mais non seedée ne peut pas être déclarée prête ni alimenter silencieusement Opportunity.

Les critères structurés dans `eligibilityRules` reprennent uniquement des éléments visibles sur les pages publiques et restent informatifs. Ils ne sont pas évalués par l'Opportunity Engine. Les règles de démonstration et leurs seuils utilisent des données synthétiques et portent le statut **HYPOTHÈSE À VALIDER AVEC BOA**.

Les preuves reproductibles sont produites par [`validate-product-catalog-migration.sh`](../scripts/validate-product-catalog-migration.sh) pour les cycles PostgreSQL et [`validate-product-catalog.sh`](../scripts/validate-product-catalog.sh) pour la readiness, le catalogue servi et la chaîne métier. Leurs résultats versionnés se trouvent dans [`docs/evidence/catalog/`](evidence/catalog/).

## Limites

Les pages de Dépôt à terme, Bon de caisse et OPCVM appartiennent à la rubrique publique « Professionnels » ; leur usage pour une PME doit être confirmé par BOA. Cash Pooling est présenté pour des organisations multi-comptes ou multi-filiales et n'est pas étiqueté comme une offre PME. La page Business Online utilisée est une page entreprise générale, non une fiche produit dédiée. Aucun tarif, taux contractuel ou règle d'octroi n'est inféré.
