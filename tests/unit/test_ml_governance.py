from datetime import date

import pytest
from boa_oi.ml.governance import (
    activation_blockers,
    canonical_digest,
    dataset_manifest_blockers,
    evaluation_blockers,
)
from boa_oi.mlops.domain import (
    FeatureContaminationError,
    FeatureLineage,
    TrainingExample,
    TrainingLineage,
)


def test_canonical_digest_is_order_independent_and_sensitive_to_values():
    first = canonical_digest({"b": 2, "a": {"x": 1}})
    repeated = canonical_digest({"a": {"x": 1}, "b": 2})
    changed = canonical_digest({"a": {"x": 2}, "b": 2})
    assert first == repeated
    assert len(first) == 64
    assert first != changed


def test_local_or_synthetic_labels_block_dataset_and_activation():
    blockers = dataset_manifest_blockers(
        source_kind="LOCAL_COMMERCIAL_OUTCOME",
        feature_snapshot_ids=[],
        labels=[],
        training_cutoff="2026-03-31",
    )
    assert blockers == [
        "BOA_HISTORICAL_LABELS_UNAVAILABLE",
        "FEATURE_SNAPSHOTS_MISSING",
        "LABEL_SNAPSHOTS_MISSING",
    ]
    activation = activation_blockers(
        deployment_mode="POC_SHADOW",
        source_kind="SYNTHETIC",
        dataset_manifest_hash=None,
        artifact_checksum=None,
        lineage_examples=[],
        metrics={"Precision@K": "N/A", "calibrationStatus": "NOT_VALIDATED"},
    )
    assert "BOA_HISTORICAL_LABELS_UNAVAILABLE" in activation
    assert "DATASET_MANIFEST_HASH_MISSING" in activation
    assert "MODEL_ARTIFACT_CHECKSUM_MISSING" in activation
    assert "POINT_IN_TIME_EXAMPLES_MISSING" in activation
    assert "EVALUATION_NOT_VALIDATED" in activation
    assert "CALIBRATION_NOT_VALIDATED" in activation


def test_complete_boa_evidence_is_gate_eligible_but_remains_shadow():
    label = {
        "sourceKind": "BOA_HISTORICAL_OBSERVED",
        "candidateOnly": False,
        "windowClosed": True,
        "outcomeValue": True,
        "featureSnapshotId": "feature-1",
        "labelAvailableFrom": "2026-04-30",
    }
    assert (
        dataset_manifest_blockers(
            source_kind="BOA_HISTORICAL_OBSERVED",
            feature_snapshot_ids=["feature-1"],
            labels=[label],
            training_cutoff="2026-03-31",
        )
        == []
    )
    assert (
        activation_blockers(
            deployment_mode="POC_SHADOW",
            source_kind="BOA_HISTORICAL_OBSERVED",
            dataset_manifest_hash="a" * 64,
            artifact_checksum="b" * 64,
            lineage_examples=[{"entityId": "SME-1"}],
            metrics={
                "PR-AUC": 0.7,
                "brierScore": 0.18,
                "expectedCalibrationError": 0.07,
                "calibrationStatus": "VALIDATED",
            },
        )
        == []
    )


def test_activation_rejects_declared_calibration_without_brier_and_ece():
    blockers = activation_blockers(
        deployment_mode="POC_SHADOW",
        source_kind="BOA_HISTORICAL_OBSERVED",
        dataset_manifest_hash="a" * 64,
        artifact_checksum="b" * 64,
        lineage_examples=[{"entityId": "SME-1"}],
        metrics={"PR-AUC": 0.7, "calibrationStatus": "VALIDATED"},
    )
    assert "BRIER_SCORE_NOT_VALIDATED" in blockers
    assert "ECE_NOT_VALIDATED" in blockers


def test_evaluation_requires_boa_source_criteria_brier_ece_and_validated_calibration():
    blockers = evaluation_blockers(
        source_kind="SYNTHETIC",
        metrics={"PR-AUC": "N/A"},
        calibration={
            "status": "NOT_VALIDATED",
            "brierScore": "N/A",
            "expectedCalibrationError": "N/A",
        },
        acceptance_criteria={},
    )
    assert blockers == [
        "BOA_HISTORICAL_LABELS_UNAVAILABLE",
        "BOA_ACCEPTANCE_CRITERIA_NOT_APPROVED",
        "EVALUATION_METRICS_NOT_EXPLOITABLE",
        "CALIBRATION_NOT_VALIDATED",
        "BRIER_SCORE_MISSING",
        "ECE_MISSING",
    ]


def test_point_in_time_lineage_rejects_late_sources_labels_and_duplicates():
    late_source = FeatureLineage(
        "balance",
        date(2026, 3, 30),
        date(2026, 3, 31),
        source_available_at=date(2026, 4, 1),
    )
    with pytest.raises(FeatureContaminationError, match="sourceAvailableAt"):
        late_source.validate()

    feature = FeatureLineage("balance", date(2026, 3, 30), date(2026, 3, 31))
    invalid_label = TrainingExample(
        "SME-1",
        date(2026, 3, 31),
        (feature,),
        label=True,
        label_available_from=date(2026, 3, 31),
    )
    with pytest.raises(FeatureContaminationError, match="strictly after"):
        invalid_label.validate_temporal_integrity()

    valid = TrainingExample(
        "SME-1",
        date(2026, 3, 31),
        (feature,),
        label=True,
        label_available_from=date(2026, 4, 30),
    )
    lineage = TrainingLineage(
        dataset_id="dataset-v1",
        feature_set_version="features-v1",
        training_cutoff=date(2026, 3, 31),
        examples=(valid, valid),
        dataset_manifest_hash="a" * 64,
        source_kind="BOA_HISTORICAL_OBSERVED",
        target_outcome="CONVERTED",
        horizon_days=30,
        population={"segment": "SME"},
    )
    with pytest.raises(ValueError, match="duplicate"):
        lineage.validate()
