# Catalogue commercial BANK OF AFRICA (entreprises et PME)

**Source unique :** `backend/src/boa_oi/catalog.py`. Le seed (`database/seed/generate.py`), le service mock-banking et les tests l'importent ; le Product Service le sert via `GET /api/v1/products` (champs `family`, `description`, `sourceUrl` ajoutés par la migration `0005_product_catalog`).

Chaque produit est un produit réellement commercialisé par BANK OF AFRICA au Maroc, relevé le 19 septembre 2026 sur les pages publiques de bankofafrica.ma (rubriques *Entreprises* et *Placement bancaire* des professionnels). Les descriptions reprennent les caractéristiques publiées ; quand une page ne précise pas un chiffre, il n'est pas inventé. Les conditions tarifaires ne sont jamais reprises.

## Familles et moteur

Le moteur d'opportunités raisonne par **famille** (codes stables ci-dessous) : une PME qui détient n'importe quel produit d'une famille n'a pas de lacune sur cette famille (`boa_oi.catalog.family_status`). Les règles, elles, recommandent des **produits commerciaux précis** (`recommended_product_codes` dans `database/seed/rules.yaml`, `recommendation.products` dans le Rule Studio). Les anciens codes génériques du prototype (`INVESTMENT_FINANCING`, `TERM_DEPOSIT`…) restent en base comme produits inactifs pour ne pas casser les détentions historiques.

| Famille | Libellé | Produits |
|---|---|---:|
| `INVESTMENT_FINANCING` | Financement de l'investissement | 6 |
| `WORKING_CAPITAL_FACILITY` | Financement du cycle d'exploitation | 5 |
| `OVERDRAFT` | Avances et découverts | 2 |
| `TRADE_FINANCE` | Opérations à l'international | 6 |
| `CASH_MANAGEMENT` | Gestion des flux et de la trésorerie | 6 |
| `TERM_DEPOSIT` | Placements à taux garanti | 2 |
| `LIQUIDITY_INVESTMENT` | Placements en OPCVM | 1 |

## Produits

### Financement de l'investissement

- **Crédit MLTD Direct** (`BOA_CREDIT_MLTD_DIRECT`, financing, segments SMALL, MEDIUM) : Crédit à moyen et long terme pour l'acquisition de terrains, locaux, fonds de commerce, constructions et équipements ; jusqu'à 70 % de l'investissement sur 7 à 12 ans selon le type de crédit. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/credit-moyen-et-long-terme/credit-mltd-direct)
- **Financement des Entreprises by BANK OF AFRICA** (`BOA_FINANCEMENT_ENTREPRISES`, financing, segments SMALL, MEDIUM) : Crédits d'investissement et de trésorerie destinés aux entreprises, PME, auto-entrepreneurs et professions libérales. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/credit-moyen-et-long-terme/financement-des-entreprises-bank-africa)
- **Bail Entreprise** (`BOA_BAIL_ENTREPRISE`, leasing, segments SMALL, MEDIUM) : Crédit-bail mobilier et immobilier finançant jusqu'à 100 % du montant hors taxes (70 000 à 5 000 000 DH), sur 60 mois pour le mobilier et 120 mois pour l'immobilier, avec option de rachat en fin de contrat. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/leasing/bail-entreprise)
- **Istitmar (Maroc PME)** (`BOA_ISTITMAR_MAROC_PME`, financing, segments SMALL) : Cofinancement des investissements des très petites et petites entreprises (chiffre d'affaires jusqu'à 200 MDH) avec une prime d'investissement de 20 à 30 % du coût du projet, octroyée par Maroc PME. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/financement/istitmar-maroc-pme)
- **CAP Energie** (`BOA_CAP_ENERGIE`, financing, segments SMALL, MEDIUM) : Financement de projets d'efficacité énergétique, d'énergies renouvelables, d'économie d'eau et de gestion durable des terres : crédit ou bail jusqu'à 100 % de l'investissement, assistance technique et subvention de 10 à 15 %, sur 10 à 12 ans. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/financement-de-lefficacite-energetique/cap-energie)
- **Daman Istitmar** (`BOA_DAMAN_ISTITMAR`, guarantee, segments SMALL, MEDIUM) : Crédit d'investissement bénéficiant d'une garantie d'organisme étatique. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/credit-avec-garanties-dorganismes-etatique/daman-istitmar)

### Financement du cycle d'exploitation

- **Escompte Commercial Maroc** (`BOA_ESCOMPTE_COMMERCIAL_MAROC`, financing, segments SMALL, MEDIUM) : Financement des effets de commerce domestiques avant leur échéance. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/credit-descompte/escompte-commercial-maroc)
- **Factor** (`BOA_FACTOR`, financing, segments SMALL, MEDIUM) : Affacturage : financement immédiat des créances commerciales, garantie contre les impayés et externalisation du recouvrement ; réservé aux entreprises ayant au moins un an d'activité et 2 MDH de chiffre d'affaires. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/supply-chain/factor)
- **SCF by BANK OF AFRICA** (`BOA_SCF`, financing, segments SMALL, MEDIUM) : Plateforme digitale de Supply Chain Finance : financement des fournisseurs d'un donneur d'ordres avant l'échéance de leurs factures. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/supply-chain/scf-bank-africa)
- **Damane Atassyir** (`BOA_DAMANE_ATASSYIR`, guarantee, segments SMALL, MEDIUM) : Garantie publique couvrant jusqu'à 60 % des crédits de fonctionnement (plafond 10 MDH par opération) avec une commission réduite, en alternative au nantissement. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/credit-avec-garanties-dorganismes-etatique/damane-atassyir)
- **Avance sur marché nanti** (`BOA_AVANCE_MARCHE_NANTI`, financing, segments SMALL, MEDIUM) : Avance de trésorerie adossée à un marché public nanti. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/avance-sur-marche-nanti)

### Avances et découverts

- **Crédit de campagne** (`BOA_CREDIT_CAMPAGNE`, financing, segments SMALL, MEDIUM) : Facilité de caisse adaptée aux activités périodiques et saisonnières, avec remboursement échelonné sur 6 à 12 mois. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/credit-de-campagne)
- **Crédit relais** (`BOA_CREDIT_RELAIS`, financing, segments SMALL, MEDIUM) : Financement transitoire dans l'attente d'une rentrée de fonds certaine. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/avances-et-decouverts/credit-relais)

### Opérations à l'international

- **Crédit documentaire** (`BOA_CREDIT_DOCUMENTAIRE`, trade, segments SMALL, MEDIUM) : Sécurisation des paiements à l'import et à l'export : paiement garanti contre remise des documents d'expédition. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/reglement-linternational/credit-documentaire)
- **Lettre de crédit stand-by** (`BOA_LC_STANDBY`, trade, segments SMALL, MEDIUM) : Garantie de paiement à première demande en couverture d'une transaction internationale. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/reglement-linternational/lettre-de-credit-stand)
- **Financement des Importations** (`BOA_FINANCEMENT_IMPORTATIONS`, trade, segments SMALL, MEDIUM) : Ligne de crédit permettant de régler les importations sans déséquilibrer la trésorerie et en optimisant la rotation des stocks. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/financement-des-importations)
- **Préfinancement à l'exportation** (`BOA_PREFINANCEMENT_EXPORT`, trade, segments SMALL, MEDIUM) : Ligne de crédit finançant le cycle de production des exportateurs (matières premières, stockage, exploitation) jusqu'à six mois, prorogeable. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/prefinancement-lexportation)
- **Mobilisation de créances sur l'étranger** (`BOA_MOBILISATION_CREANCES_ETRANGER`, trade, segments SMALL, MEDIUM) : Avance immédiate sur les créances en devises des exportateurs qui accordent des délais de paiement à leurs acheteurs. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/financements-linternational/mobilisation-de-creances-sur-letranger)
- **Compte en devises** (`BOA_COMPTE_DEVISES`, account, segments SMALL, MEDIUM) : Compte pour gérer les opérations en devises des entreprises exportatrices : virements et encaissements de l'étranger, moyens de paiement internationaux. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/gerer-mes-comptes-et-package/compte-en-devises)

### Gestion des flux et de la trésorerie

- **Pack Business PME** (`BOA_PACK_BUSINESS_PME`, package, segments SMALL, MEDIUM) : Forfait mensuel regroupant compte entreprise, carte business internationale, banque en ligne et un forfait de services, avec exonération de commissions. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/pack-dedie/pack-business-pme)
- **Business Online** (`BOA_BUSINESS_ONLINE`, digital, segments SMALL, MEDIUM) : Portail de banque à distance des entreprises, avec applications mobiles. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises)
- **Virement de masse** (`BOA_VIREMENT_MASSE`, payment, segments SMALL, MEDIUM) : Exécution de virements en volume (salaires, fournisseurs) depuis un fichier. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/moyens-de-paiement/virement-de-masse)
- **Prélèvement de masse** (`BOA_PRELEVEMENT_MASSE`, payment, segments SMALL, MEDIUM) : Encaissement automatisé des créances récurrentes par prélèvement en volume. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/moyens-de-paiement/prelevement-de-masse)
- **Ramassage de fonds** (`BOA_RAMASSAGE_FONDS`, cash, segments SMALL, MEDIUM) : Collecte et transport sécurisés des espèces par des prestataires qualifiés. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/gestion-de-tresorerie/ramassage-de-fonds)
- **Cash Pooling** (`BOA_CASH_POOLING`, cash, segments MEDIUM) : Centralisation de la trésorerie des entreprises multi-comptes ou multi-filiales pour éliminer les découverts et optimiser les intérêts. [Fiche produit](https://www.bankofafrica.ma/fr/entreprises/gestion-de-tresorerie/cash-pooling)

### Placements à taux garanti

- **Dépôt à terme** (`BOA_DEPOT_A_TERME`, investment, segments SMALL, MEDIUM) : Placement bloqué sur 1, 3, 6, 12 ou 24 mois à taux garanti, sans frais de souscription, de gestion ni de clôture, avec possibilité d'avance. [Fiche produit](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/depot-terme)
- **Bon de caisse** (`BOA_BON_DE_CAISSE`, investment, segments SMALL, MEDIUM) : Placement à durée fixe (1 à 24 mois) rémunéré par des intérêts nets, à partir de 5 000 DH, avec possibilité d'avance. [Fiche produit](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/bon-de-caisse)

### Placements en OPCVM

- **OPCVM** (`BOA_OPCVM`, investment, segments SMALL, MEDIUM) : Placement en portefeuilles collectifs de valeurs mobilières gérés par des professionnels, pour diversifier les excédents de trésorerie. [Fiche produit](https://www.bankofafrica.ma/fr/professionnels/placement-bancaire/opcvm)

## Rechargement

```bash
PYTHONPATH=backend/src:. python database/seed/generate.py --database-url "$DATABASE_URL" --products-only
```

Recharge le catalogue (upsert), désactive les codes absents du catalogue et regénère les détentions de démonstration (une PME sur cinq détient chaque famille, un produit tiré de façon déterministe ; les PME du scénario `INTERNATIONAL_GROWTH` n'ont jamais de produit international). Les règles moteur déjà persistées dans `opportunity.opportunity_rules` conservent leurs produits recommandés : les mettre à jour via `PATCH /api/v1/admin/rules/{id}` (paramètre `recommended_product_codes`), puis rejouer le pipeline.

## Limites connues

- Le site public ne présente pas de rubrique « placements » pour les entreprises : Dépôt à terme, Bon de caisse et OPCVM proviennent de l'offre *Professionnels & TPE* et sont à confirmer pour le segment PME.
- Les critères d'éligibilité (`eligibilityRules`) ne reprennent que les chiffres publiés (montants, durées, chiffre d'affaires) ; ils sont informatifs et ne sont pas évalués par le moteur.
- Les produits « Me protéger » (assurances) et les cartes ne sont pas repris : aucune règle ne les recommande à ce stade.
