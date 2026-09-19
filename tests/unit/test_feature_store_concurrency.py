from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest
from boa_oi.feature_store_api import claim_materialization
from boa_oi.platform import Problem
from sqlalchemy.dialects import postgresql


class Bind:
    class dialect:
        name = "postgresql"


class SessionDouble:
    def __init__(self, claimed: bool) -> None:
        self.claimed = claimed
        self.statement: Any | None = None

    def get_bind(self) -> Bind:
        return Bind()

    def scalar(self, statement: Any) -> bool:
        self.statement = statement
        return self.claimed


def test_materialization_claim_is_non_blocking_postgresql_lock() -> None:
    session = SessionDouble(claimed=True)

    claim_materialization(
        cast(Any, session),
        "SME-00001",
        date(2026, 9, 30),
        "sales-features-v2",
    )

    assert session.statement is not None
    rendered = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "pg_try_advisory_xact_lock" in rendered


def test_materialization_claim_conflict_is_controlled() -> None:
    session = SessionDouble(claimed=False)

    with pytest.raises(Problem) as captured:
        claim_materialization(
            cast(Any, session),
            "SME-00001",
            date(2026, 9, 30),
            "sales-features-v2",
        )

    assert captured.value.status_code == 409
    assert captured.value.code == "FEATURE_MATERIALIZATION_IN_PROGRESS"
