from boa_oi.ml_training.routes import _g3_gate


def test_g3_is_blocked_when_g1_is_blocked_even_with_champion_and_events() -> None:
    passed, missing = _g3_gate(
        g1_passed=False,
        g2_passed=True,
        has_champion=True,
        has_model_governance_event=True,
        has_active_ml_policy=True,
        has_policy_activation_event=True,
    )

    assert passed is False
    assert missing is not None and "G1" in missing


def test_g3_is_blocked_without_active_ml_positive_policy() -> None:
    passed, missing = _g3_gate(
        g1_passed=True,
        g2_passed=True,
        has_champion=True,
        has_model_governance_event=True,
        has_active_ml_policy=False,
        has_policy_activation_event=False,
    )

    assert passed is False
    assert missing is not None and "poids ML strictement positif" in missing


def test_g3_passes_only_when_every_prerequisite_is_met() -> None:
    passed, missing = _g3_gate(
        g1_passed=True,
        g2_passed=True,
        has_champion=True,
        has_model_governance_event=True,
        has_active_ml_policy=True,
        has_policy_activation_event=True,
    )

    assert passed is True
    assert missing is None
