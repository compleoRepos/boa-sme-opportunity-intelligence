"""Données de référence de démonstration partagées (agences).

Aucune table d'agence n'existe dans le MVP : les codes BR-xx du seed sont libellés ici.
Surchargeable par la variable d'environnement BRANCH_LABELS_JSON ({"BR-01": "..."}).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

DEFAULT_BRANCH_LABELS: dict[str, str] = {
    "BR-01": "Casablanca Anfa",
    "BR-02": "Casablanca Sidi Maârouf",
    "BR-03": "Rabat Agdal",
    "BR-04": "Tanger Zone Franche",
    "BR-05": "Marrakech Guéliz",
}


@lru_cache(maxsize=1)
def branch_labels() -> dict[str, str]:
    raw = os.getenv("BRANCH_LABELS_JSON")
    if not raw:
        return dict(DEFAULT_BRANCH_LABELS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_BRANCH_LABELS)
    return {**DEFAULT_BRANCH_LABELS, **{str(k): str(v) for k, v in parsed.items()}}


def branch_label(code: str | None) -> str | None:
    if not code:
        return None
    return branch_labels().get(code, code)


__all__ = ["DEFAULT_BRANCH_LABELS", "branch_label", "branch_labels"]
