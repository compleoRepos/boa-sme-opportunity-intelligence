from __future__ import annotations

from uuid import UUID, uuid5

BOA_NAMESPACE = UUID("92777cf0-4ef3-5fe1-8557-8334407d8fa2")


def deterministic_uuid(*parts: object) -> UUID:
    """Return a stable UUID for a canonical sequence of business key parts."""
    return uuid5(BOA_NAMESPACE, "|".join(str(part) for part in parts))
