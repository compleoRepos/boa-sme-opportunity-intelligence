"""Catalogue indicatif de produits BANK OF AFRICA visibles sur le site public.

Source unique du catalogue produit utilisé par le seed, le service mock-banking et
les tests. Chaque entrée reprend une page publique BANK OF AFRICA Maroc ; `source_url`
permet une vérification humaine. Ce catalogue n'est pas un référentiel contractuel et
les ciblages ou critères restent à valider avec BOA avant tout pilote réel.

Le moteur d'opportunités raisonne par *famille* (codes stables : INVESTMENT_FINANCING,
TRADE_FINANCE…) et non par produit commercial : une PME qui détient un « Crédit MLTD
Direct » n'a pas de lacune sur la famille INVESTMENT_FINANCING. Les règles recommandent
en revanche des produits commerciaux précis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BOA_SITE = "https://www.bankofafrica.ma"

FAMILIES: dict[str, str] = {
    "INVESTMENT_FINANCING": "Financement de l'investissement",
    "WORKING_CAPITAL_FACILITY": "Financement du cycle d'exploitation",
    "OVERDRAFT": "Avances et découverts",
    "TRADE_FINANCE": "Opérations à l'international",
    "CASH_MANAGEMENT": "Gestion des flux et de la trésorerie",
    "TERM_DEPOSIT": "Placements à taux garanti",
    "LIQUIDITY_INVESTMENT": "Placements en OPCVM",
}

# Ordre de préférence lorsqu'une famille est détenue par plusieurs produits.
_OWNERSHIP_RANK = {
    "OWNED": 3,
    "UNDERUTILIZED": 2,
    "ABSENT_OR_ELSEWHERE": 1,
    "ABSENT": 0,
}


@dataclass(frozen=True)
class CatalogProduct:
    code: str
    name: str
    category: str
    family: str
    description: str
    source_url: str
    target_segments: tuple[str, ...] = ("ENTERPRISE",)
    eligibility: dict[str, object] = field(default_factory=dict)

    @property
    def legacy_tuple(self) -> tuple[str, str, str]:
        return (self.code, self.name, self.category)


def _p(
    code: str,
    name: str,
    category: str,
    family: str,
    description: str,
    path: str,
    segments: tuple[str, ...] = ("ENTERPRISE",),
    **eligibility: object,
) -> CatalogProduct:
    return CatalogProduct(
        code=code,
        name=name,
        category=category,
        family=family,
        description=description,
        source_url=f"{BOA_SITE}{path}",
        target_segments=segments,
        eligibility=dict(eligibility),
    )


BOA_PRODUCTS: tuple[CatalogProduct, ...] = (
    # Financer mon investissement
    _p(
        "BOA_CREDIT_MLTD_DIRECT",
        "Crédit MLTD Direct",
        "FINANCING",
        "INVESTMENT_FINANCING",
        "Crédit à moyen et long terme pour l'acquisition de terrains, locaux, fonds de "
        "commerce, constructions et équipements ; jusqu'à 70 % de l'investissement sur "
        "7 à 12 ans selon le type de crédit.",
        "/fr/entreprises/credit-moyen-et-long-terme/credit-mltd-direct",
        maxFinancingRatio=0.70,
        durationYears=[7, 12],
    ),
    _p(
        "BOA_FINANCEMENT_ENTREPRISES",
        "Financement des Entreprises by BANK OF AFRICA",
        "FINANCING",
        "INVESTMENT_FINANCING",
        "Solutions et lignes de financement destinées au démarrage, au développement "
        "ou à l'extension des activités d'entreprise.",
        "/fr/entreprises/credit-moyen-et-long-terme/financement-des-entreprises-bank-africa",
        ("SMALL", "MEDIUM", "ENTERPRISE", "PROFESSIONAL"),
    ),
    _p(
        "BOA_BAIL_ENTREPRISE",
        "Bail Entreprise",
        "LEASING",
        "INVESTMENT_FINANCING",
        "Crédit-bail mobilier et immobilier finançant jusqu'à 100 % du montant hors "
        "taxes (70 000 à 5 000 000 DH), sur 60 mois pour le mobilier et 120 mois pour "
        "l'immobilier, avec option de rachat en fin de contrat.",
        "/fr/entreprises/leasing/bail-entreprise",
        minAmountMad=70_000,
        maxAmountMad=5_000_000,
    ),
    _p(
        "BOA_ISTITMAR_MAROC_PME",
        "Istitmar (Maroc PME)",
        "FINANCING",
        "INVESTMENT_FINANCING",
        "Cofinancement des investissements des très petites et petites entreprises "
        "(chiffre d'affaires jusqu'à 200 MDH) avec une prime d'investissement de 20 à "
        "30 % du coût du projet, octroyée par Maroc PME.",
        "/fr/entreprises/financement/istitmar-maroc-pme",
        ("SMALL",),
        maxTurnoverMad=200_000_000,
    ),
    _p(
        "BOA_CAP_ENERGIE",
        "CAP Energie",
        "FINANCING",
        "INVESTMENT_FINANCING",
        "Financement de projets d'efficacité énergétique, d'énergies renouvelables, "
        "d'économie d'eau et de gestion durable des terres : crédit ou bail jusqu'à "
        "100 % de l'investissement, assistance technique et subvention de 10 à 15 %, "
        "sur 10 à 12 ans.",
        "/fr/entreprises/financement-de-lefficacite-energetique/cap-energie",
    ),
    _p(
        "BOA_DAMAN_ISTITMAR",
        "Daman Istitmar",
        "GUARANTEE",
        "INVESTMENT_FINANCING",
        "Financement de projets d'investissement adossé à un dispositif de garantie.",
        "/fr/entreprises/credit-avec-garanties-dorganismes-etatique/daman-istitmar",
    ),
    # Financer mon cycle d'exploitation
    _p(
        "BOA_ESCOMPTE_COMMERCIAL_MAROC",
        "Escompte Commercial Maroc",
        "FINANCING",
        "WORKING_CAPITAL_FACILITY",
        "Avance de trésorerie contre remise d'effets de commerce avant leur échéance.",
        "/fr/entreprises/credit-descompte/escompte-commercial-maroc",
    ),
    _p(
        "BOA_FACTOR",
        "Factor",
        "FINANCING",
        "WORKING_CAPITAL_FACILITY",
        "Affacturage : financement immédiat des créances commerciales, garantie contre "
        "les impayés et externalisation du recouvrement ; réservé aux entreprises ayant "
        "au moins un an d'activité et 2 MDH de chiffre d'affaires.",
        "/fr/entreprises/supply-chain/factor",
        minTurnoverMad=2_000_000,
        minTenureMonths=12,
    ),
    _p(
        "BOA_SCF",
        "SCF by BANK OF AFRICA",
        "FINANCING",
        "WORKING_CAPITAL_FACILITY",
        "Plateforme digitale de Supply Chain Finance : financement des fournisseurs "
        "d'un donneur d'ordres avant l'échéance de leurs factures.",
        "/fr/entreprises/supply-chain/scf-bank-africa",
    ),
    _p(
        "BOA_DAMANE_ATASSYIR",
        "Damane Atassyir",
        "GUARANTEE",
        "WORKING_CAPITAL_FACILITY",
        "Produit de garantie couvrant jusqu'à 60 % des crédits de fonctionnement "
        "(plafond 10 MDH par opération) avec une commission réduite, en alternative "
        "au nantissement.",
        "/fr/entreprises/credit-avec-garanties-dorganismes-etatique/damane-atassyir",
        maxGuaranteedAmountMad=10_000_000,
    ),
    _p(
        "BOA_AVANCE_MARCHE_NANTI",
        "Avance sur marché nanti",
        "FINANCING",
        "WORKING_CAPITAL_FACILITY",
        "Avance de trésorerie adossée à une créance sur marché public ou semi-public nanti.",
        "/fr/entreprises/avances-et-decouverts/avance-sur-marche-nanti",
    ),
    # Avances et découverts
    _p(
        "BOA_CREDIT_CAMPAGNE",
        "Crédit de campagne",
        "FINANCING",
        "OVERDRAFT",
        "Facilité de caisse adaptée aux activités périodiques et saisonnières ; la durée "
        "varie selon la campagne et se situe généralement entre 6 et 12 mois.",
        "/fr/entreprises/avances-et-decouverts/credit-de-campagne",
    ),
    _p(
        "BOA_CREDIT_RELAIS",
        "Crédit relais",
        "FINANCING",
        "OVERDRAFT",
        "Financement transitoire dans l'attente d'une rentrée de fonds certaine.",
        "/fr/entreprises/avances-et-decouverts/credit-relais",
    ),
    # Opérations à l'international
    _p(
        "BOA_CREDIT_DOCUMENTAIRE",
        "Crédit documentaire",
        "TRADE",
        "TRADE_FINANCE",
        "Sécurisation des paiements à l'import et à l'export : paiement garanti contre "
        "remise des documents d'expédition.",
        "/fr/entreprises/reglement-linternational/credit-documentaire",
    ),
    _p(
        "BOA_LC_STANDBY",
        "Lettre de crédit stand-by",
        "TRADE",
        "TRADE_FINANCE",
        "Garantie de paiement en couverture d'une transaction internationale.",
        "/fr/entreprises/reglement-linternational/lettre-de-credit-stand",
    ),
    _p(
        "BOA_FINANCEMENT_IMPORTATIONS",
        "Financement des Importations",
        "TRADE",
        "TRADE_FINANCE",
        "Ligne de crédit permettant de régler les importations sans déséquilibrer la "
        "trésorerie et en optimisant la rotation des stocks.",
        "/fr/entreprises/financements-linternational/financement-des-importations",
    ),
    _p(
        "BOA_PREFINANCEMENT_EXPORT",
        "Préfinancement à l'exportation",
        "TRADE",
        "TRADE_FINANCE",
        "Ligne de crédit finançant le cycle de production des exportateurs (matières "
        "premières, stockage, exploitation) jusqu'à six mois, prorogeable.",
        "/fr/entreprises/financements-linternational/prefinancement-lexportation",
    ),
    _p(
        "BOA_MOBILISATION_CREANCES_ETRANGER",
        "Mobilisation de créances sur l'étranger",
        "TRADE",
        "TRADE_FINANCE",
        "Avance immédiate sur les créances en devises des exportateurs qui accordent "
        "des délais de paiement à leurs acheteurs.",
        "/fr/entreprises/financements-linternational/mobilisation-de-creances-sur-letranger",
    ),
    _p(
        "BOA_COMPTE_DEVISES",
        "Compte en devises",
        "ACCOUNT",
        "TRADE_FINANCE",
        "Compte pour gérer les opérations en devises des entreprises exportatrices : "
        "virements et encaissements de l'étranger, moyens de paiement internationaux.",
        "/fr/entreprises/gerer-mes-comptes-et-package/compte-en-devises",
    ),
    # Gérer mes flux
    _p(
        "BOA_PACK_BUSINESS_PME",
        "Pack Business PME",
        "PACKAGE",
        "CASH_MANAGEMENT",
        "Forfait mensuel regroupant compte entreprise, carte business internationale, "
        "banque en ligne et un forfait de services, avec exonération de commissions.",
        "/fr/entreprises/pack-dedie/pack-business-pme",
        ("SMALL", "MEDIUM"),
    ),
    _p(
        "BOA_BUSINESS_ONLINE",
        "Business Online",
        "DIGITAL",
        "CASH_MANAGEMENT",
        "Portail de banque à distance des entreprises, avec applications mobiles.",
        "/fr/entreprises",
    ),
    _p(
        "BOA_VIREMENT_MASSE",
        "Virement de masse",
        "PAYMENT",
        "CASH_MANAGEMENT",
        "Exécution de virements multiples ou automatisés, notamment pour les salaires "
        "et fournisseurs.",
        "/fr/entreprises/moyens-de-paiement/virement-de-masse",
    ),
    _p(
        "BOA_PRELEVEMENT_MASSE",
        "Prélèvement de masse",
        "PAYMENT",
        "CASH_MANAGEMENT",
        "Encaissement automatisé des créances récurrentes par prélèvement en volume.",
        "/fr/entreprises/moyens-de-paiement/prelevement-de-masse",
    ),
    _p(
        "BOA_RAMASSAGE_FONDS",
        "Ramassage de fonds",
        "CASH",
        "CASH_MANAGEMENT",
        "Collecte et transport sécurisés des espèces par des prestataires qualifiés.",
        "/fr/entreprises/gestion-de-tresorerie/ramassage-de-fonds",
    ),
    _p(
        "BOA_CASH_POOLING",
        "Cash Pooling",
        "CASH",
        "CASH_MANAGEMENT",
        "Centralisation de la trésorerie des entreprises multi-comptes ou multi-filiales "
        "pour éliminer les découverts et optimiser les intérêts.",
        "/fr/entreprises/gestion-de-tresorerie/cash-pooling",
        ("LARGE", "ENTERPRISE"),
    ),
    # Placements
    _p(
        "BOA_DEPOT_A_TERME",
        "Dépôt à terme",
        "INVESTMENT",
        "TERM_DEPOSIT",
        "Placement bloqué sur 1, 3, 6, 12 ou 24 mois à taux garanti, sans frais de "
        "souscription, de gestion ni de clôture, avec possibilité d'avance.",
        "/fr/professionnels/placement-bancaire/depot-terme",
        ("PROFESSIONAL",),
        durationMonths=[1, 3, 6, 12, 24],
    ),
    _p(
        "BOA_BON_DE_CAISSE",
        "Bon de caisse",
        "INVESTMENT",
        "TERM_DEPOSIT",
        "Placement à durée fixe de 1, 3, 6, 12 ou 24 mois, rémunéré par des intérêts "
        "nets, à partir de 5 000 DH, avec possibilité d'avance.",
        "/fr/professionnels/placement-bancaire/bon-de-caisse",
        ("PROFESSIONAL",),
        minAmountMad=5_000,
        durationMonths=[1, 3, 6, 12, 24],
    ),
    _p(
        "BOA_OPCVM",
        "OPCVM",
        "INVESTMENT",
        "LIQUIDITY_INVESTMENT",
        "Placement en portefeuilles collectifs de valeurs mobilières gérés par des "
        "professionnels, permettant de diversifier l'épargne.",
        "/fr/professionnels/placement-bancaire/opcvm",
        ("PROFESSIONAL",),
    ),
)

PRODUCTS_BY_CODE: dict[str, CatalogProduct] = {item.code: item for item in BOA_PRODUCTS}
PRODUCTS_BY_FAMILY: dict[str, tuple[CatalogProduct, ...]] = {
    family: tuple(item for item in BOA_PRODUCTS if item.family == family) for family in FAMILIES
}

# Compatibilité avec les appelants historiques attendant des triplets (code, nom, catégorie).
PRODUCTS: tuple[tuple[str, str, str], ...] = tuple(item.legacy_tuple for item in BOA_PRODUCTS)


def family_of(product: dict[str, object]) -> str:
    """Famille d'un produit sérialisé ; un produit sans famille est sa propre famille."""
    family = product.get("family")
    return str(family) if family else str(product.get("productId"))


def family_status(gaps: list[dict[str, object]]) -> dict[str, str]:
    """Statut de détention par famille ET par produit, à partir de `/product-gaps`.

    Une famille est OWNED dès qu'un de ses produits est détenu, UNDERUTILIZED si le
    meilleur produit détenu est sous-utilisé, ABSENT_OR_ELSEWHERE si la visibilité
    multibancaire requalifie au moins une absence, ABSENT sinon. Les codes produits
    restent présents pour les règles qui ciblent un produit précis.
    """
    status: dict[str, str] = {}
    for item in gaps:
        product = item["product"]
        assert isinstance(product, dict)
        current = str(item["status"])
        for key in {str(product["productId"]), family_of(product)}:
            previous = status.get(key)
            if previous is None or _OWNERSHIP_RANK[current] > _OWNERSHIP_RANK[previous]:
                status[key] = current
    return status


def as_payload(product: CatalogProduct) -> dict[str, object]:
    """Représentation API (import produits / catalogue mock-banking)."""
    return {
        "productId": product.code,
        "name": product.name,
        "category": product.category,
        "family": product.family,
        "description": product.description,
        "sourceUrl": product.source_url,
        "eligibilityRules": dict(product.eligibility),
        "targetSegment": list(product.target_segments),
        "currency": ["MAD"],
        "active": True,
    }


def demo_ownerships(customer_ref: str, scenario: str) -> tuple[str, ...]:
    """Produits détenus par une PME de démonstration, décidés famille par famille.

    Le tirage se fait sur la famille (une PME sur cinq détient chaque famille, de
    façon déterministe) puis un produit de la famille est choisi ; la distribution des
    lacunes produit vue par le moteur est donc indépendante de la taille du catalogue.
    Les PME du scénario INTERNATIONAL_GROWTH n'ont jamais de produit international,
    pour que la lacune trade finance soit observable.
    """
    import hashlib

    owned: list[str] = []
    for family, products in PRODUCTS_BY_FAMILY.items():
        if not products or (scenario == "INTERNATIONAL_GROWTH" and family == "TRADE_FINANCE"):
            continue
        digest = int(hashlib.sha256(f"{customer_ref}|{family}".encode()).hexdigest(), 16)
        if digest % 5 == 0:
            owned.append(products[(digest // 5) % len(products)].code)
    return tuple(owned)
