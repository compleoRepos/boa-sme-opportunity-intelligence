from __future__ import annotations

from datetime import date

import pytest
from boa_oi.opportunities import OpportunityContext
from boa_oi.technical.config import load_rule_set


@pytest.fixture(scope="session")
def rule_set():
    return load_rule_set()


@pytest.fixture
def valid_context_factory():
    def factory(**overrides):
        values = {
            "customer_id": "SME-00125",
            "as_of_date": date(2026, 9, 30),
            "facts": {},
            "data_coverage": 1.0,
            "data_quality": "VALID",
            "seasonality_adjusted": True,
            "false_positive_flags": (),
        }
        values.update(overrides)
        return OpportunityContext(**values)

    return factory
