"""Noms de démonstration réalistes et déterministes (PME, chargés de clientèle, agences).

Toutes les entités restent synthétiques : aucune raison sociale, personne ou agence réelle
n'est visée. Les fonctions sont pures et dépendent uniquement de l'index de seed, ce qui
conserve la reproductibilité du jeu de données.
"""

from __future__ import annotations

from boa_oi.technical.reference import DEFAULT_BRANCH_LABELS as BRANCH_LABELS
from boa_oi.technical.reference import branch_label

RM_FIRST_NAMES = (
    "Ahmed",
    "Salma",
    "Youssef",
    "Imane",
    "Mehdi",
    "Kenza",
    "Omar",
    "Hajar",
    "Anas",
    "Meryem",
    "Karim",
    "Nadia",
    "Hamza",
    "Sara",
    "Reda",
    "Amina",
    "Yassine",
    "Ghita",
    "Adil",
    "Lamia",
    "Othmane",
    "Zineb",
    "Tarik",
    "Soukaina",
    "Ismail",
)
RM_LAST_NAMES = (
    "Bennani",
    "El Idrissi",
    "Tazi",
    "Alaoui",
    "Berrada",
    "Chraibi",
    "Fassi",
    "Lahlou",
    "Sqalli",
    "Benjelloun",
    "Kettani",
    "Mansouri",
    "Ouazzani",
    "Rhazi",
    "Sebti",
    "Belkadi",
    "Cherkaoui",
    "Drissi",
    "El Amrani",
    "Filali",
    "Guessous",
    "Hajji",
    "Jabri",
    "Karimi",
    "Lazrak",
)

# Raisons sociales : [préfixe géographique/évocateur] + [mot métier par secteur] + [forme].
NAME_PREFIXES = (
    "Atlas",
    "Maghreb",
    "Chaouia",
    "Souss",
    "Rif",
    "Tensift",
    "Bouregreg",
    "Anfa",
    "Zenata",
    "Tadla",
    "Saïss",
    "Oriental",
    "Sahel",
    "Doukkala",
    "Zaër",
    "Haouz",
    "Loukkos",
    "Ourika",
    "Tafilalet",
    "Draa",
    "Abda",
    "Gharb",
    "Amazigh",
    "Cèdre",
    "Argan",
    "Zellige",
    "Kasbah",
    "Médina",
    "Corniche",
    "Océan",
    "Alizé",
    "Sirocco",
    "Meseta",
    "Toubkal",
    "Ifrane",
    "Azur",
    "Horizon",
    "Zénith",
    "Nord",
    "Sud",
    "Littoral",
    "Continental",
    "Delta",
    "Émeraude",
    "Ambre",
    "Safran",
    "Jasmin",
    "Olivier",
    "Palmier",
    "Cyprès",
)
SECTOR_WORDS: dict[str, tuple[str, ...]] = {
    "INDUSTRIE": (
        "Métal Industrie",
        "Plast Industrie",
        "Mécanique",
        "Industries",
        "Emballage",
        "Câblage",
    ),
    "IMPORT_EXPORT": (
        "Import Export",
        "Négoce International",
        "Trading",
        "Sourcing",
        "Overseas",
        "Comex",
    ),
    "DISTRIBUTION": (
        "Distribution",
        "Logistique",
        "Diffusion",
        "Grossiste",
        "Approvisionnement",
        "Dispatch",
    ),
    "SERVICES": ("Services", "Conseil", "Facilities", "Solutions", "Ingénierie", "Consulting"),
    "BTP": ("BTP", "Construction", "Travaux", "Bâtiment", "Génie Civil", "Aménagement"),
    "AGRICULTURE": ("Agri", "Agro", "Domaines", "Vergers", "Cultures", "Agrumes"),
    "COMMERCE": ("Commerce", "Négoce", "Comptoir", "Market", "Bazar", "Maison"),
    "TECHNOLOGIE": ("Tech", "Digital", "Systèmes", "Data", "Software", "Automation"),
}
LEGAL_FORMS = ("SARL", "SA", "SARL AU", "SAS")


def customer_name(index: int, sector: str) -> str:
    """Raison sociale unique et stable pour un index de seed (1..N) et un secteur."""
    words = SECTOR_WORDS.get(sector, ("Entreprise",))
    prefix = NAME_PREFIXES[(index * 7) % len(NAME_PREFIXES)]
    word = words[(index // len(NAME_PREFIXES)) % len(words)]
    form = LEGAL_FORMS[(index * 3) % len(LEGAL_FORMS)]
    cycle = index // (len(NAME_PREFIXES) * len(words))
    suffix = f" {cycle + 1}" if cycle else ""
    return f"{prefix} {word}{suffix} {form}"


def relationship_manager_index(customer_index: int, manager_count: int = 25) -> int:
    """Affectation déterministe PME -> CC (1..manager_count), volontairement inégale.

    L'agence BR-01 (CC 1..5) concentre la moitié du portefeuille afin de disposer d'une
    agence de démonstration dense ; le CC n°1 porte le portefeuille le plus large.
    Les scénarios cyclent tous les 8 clients, la diversité par CC est donc préservée.
    """
    if customer_index <= 250:
        slot = (customer_index - 1) % 20
        if slot < 5:
            return 1
        if slot < 9:
            return 2
        if slot < 13:
            return 3
        if slot < 17:
            return 4
        return 5
    return 6 + (customer_index - 251) % (manager_count - 5)


def relationship_manager_name(index: int) -> str:
    """Prénom + nom déterministes pour le chargé de clientèle numéro `index` (1..25)."""
    first = RM_FIRST_NAMES[(index - 1) % len(RM_FIRST_NAMES)]
    last = RM_LAST_NAMES[(index * 11) % len(RM_LAST_NAMES)]
    return f"{first} {last}"


__all__ = [
    "BRANCH_LABELS",
    "branch_label",
    "customer_name",
    "relationship_manager_index",
    "relationship_manager_name",
]
