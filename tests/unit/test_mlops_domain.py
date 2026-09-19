from datetime import date

import pytest
from boa_oi.mlops import (
    FeatureContaminationError,
    FeatureLineage,
    LabelDefinition,
    LabelMaturity,
    LabelObservation,
    ModelRegistry,
    ModelStatus,
    ModelVersion,
    RegistryTransitionError,
    SplitName,
    TemporalSplit,
    TrainingExample,
    TrainingLineage,
    assess_label_maturity,
    evaluate_metrics,
    validate_temporal_integrity,
)
from boa_oi.mlops.service import ConflictError, MLOpsGovernanceService

AS_OF = date(2026, 1, 10)


def feature(name: str = "balance", timestamp: date = date(2026, 1, 9)) -> FeatureLineage:
    return FeatureLineage(name, timestamp, AS_OF, source="snapshot:v1")


def example(
    entity: str, when: date, *, timestamp: date | None = None, label: int | None = 1
) -> TrainingExample:
    observed = timestamp or when
    return TrainingExample(entity, when, (FeatureLineage("balance", observed, when),), label=label)


def test_clean_lineage_passes_and_dataset_cutoff_is_enforced():
    dataset = TrainingLineage("ds-1", "features-v1", AS_OF, (example("SME-1", date(2026, 1, 9)),))
    dataset.validate()
    validate_temporal_integrity(dataset)


def test_contaminated_dataset_fails_feature_timestamp_after_observation_as_of():
    contaminated = example("SME-CONTAMINATED", AS_OF, timestamp=date(2026, 1, 11))
    with pytest.raises(FeatureContaminationError, match="temporal contamination"):
        validate_temporal_integrity([contaminated])
    assert TrainingLineage(
        "ds-bad", "features-v1", AS_OF, (contaminated,)
    ).contaminated_examples == (contaminated,)


def test_temporal_split_is_chronological_and_named_train_validation_test():
    rows = [
        example("test", date(2026, 1, 9)),
        example("train", date(2026, 1, 1)),
        example("valid", date(2026, 1, 5)),
    ]
    split = TemporalSplit(date(2026, 1, 2), date(2026, 1, 6), date(2026, 1, 12))
    result = split.split(rows)
    assert [item.entity_id for item in result[SplitName.TRAIN]] == ["train"]
    assert [item.entity_id for item in result[SplitName.VALIDATION]] == ["valid"]
    assert [item.entity_id for item in result[SplitName.TEST]] == ["test"]


def test_label_maturity_blocks_immature_and_missing_labels():
    definition = LabelDefinition("converted", horizon_days=30)
    labels = (
        LabelObservation(date(2026, 1, 1), 1, date(2026, 2, 1), definition),
        LabelObservation(date(2026, 1, 2), 0, date(2026, 2, 20), definition),
        LabelObservation(date(2026, 1, 3), None, None, definition),
    )
    report = assess_label_maturity(labels, date(2026, 2, 10))
    assert report.status == LabelMaturity.IMMATURE
    assert (report.mature_count, report.immature_count, report.missing_count) == (1, 1, 1)
    assert not report.training_ready


def test_metrics_are_na_when_they_cannot_be_exploited():
    report = evaluate_metrics([0.2, 0.8], [0, 0], k=1)
    assert report.precision_at_k == "N/A"
    assert report.recall_at_k == "N/A"
    assert report.pr_auc == "N/A"
    assert report.calibration == "N/A"
    assert report.lift == "N/A"
    assert report.uplift == "N/A"
    assert evaluate_metrics([], []).as_dict() == {
        "Precision@K": "N/A",
        "Recall@K": "N/A",
        "PR-AUC": "N/A",
        "calibration": "N/A",
        "lift": "N/A",
        "uplift": "N/A",
    }


def test_metrics_compute_without_claiming_model_performance():
    report = evaluate_metrics([0.9, 0.8, 0.1, 0.2], [1, 0, 0, 1], k=2)
    assert report.precision_at_k == pytest.approx(0.5)
    assert report.recall_at_k == pytest.approx(0.5)
    assert report.pr_auc != "N/A"


def test_registry_requires_approval_before_promotion_and_supports_rollback():
    registry = ModelRegistry()
    first = registry.register(ModelVersion("sales", "v1"))
    second = registry.register(ModelVersion("sales", "v2"))
    for key in (first.key, second.key):
        registry.transition(key, ModelStatus.VALIDATING)
        registry.transition(key, ModelStatus.SUBMITTED)
    with pytest.raises(RegistryTransitionError):
        registry.promote(first.key)
    registry.transition(first.key, ModelStatus.APPROVED, actor="reviewer", reason="reviewed")
    registry.promote(first.key)
    assert registry.champion == first and first.status == ModelStatus.CHAMPION
    registry.transition(second.key, ModelStatus.APPROVED, actor="reviewer", reason="reviewed")
    registry.promote(second.key)
    assert registry.champion == second and first.status == ModelStatus.RETIRED
    registry.rollback(actor="reviewer", reason="rollback test")
    assert registry.champion == first and second.status == ModelStatus.RETIRED


def test_service_forbids_auto_approval_and_requires_distinct_release_manager():
    service = MLOpsGovernanceService()
    payload = {
        "modelId": "sales-propensity",
        "modelVersion": "v-governed",
        "featureVersion": "features-v2",
        "datasetVersion": "dataset-v1",
        "trainingPeriodFrom": "2026-01-01",
        "trainingPeriodTo": "2026-03-31",
        "validationPeriodFrom": "2026-04-01",
        "validationPeriodTo": "2026-04-30",
        "codeVersion": "abc123",
        "metrics": {"Precision@K": "N/A"},
        "lineage": {
            "trainingCutoff": "2026-03-31",
            "sourceSnapshots": ["feature-snapshot-v1"],
            "examples": [
                {
                    "entityId": "SME-1",
                    "observationAsOf": "2026-03-15",
                    "features": [
                        {
                            "featureName": "balance",
                            "featureTimestamp": "2026-03-14",
                            "observationAsOf": "2026-03-15",
                            "source": "analytics:v1",
                        }
                    ],
                }
            ],
        },
    }
    service.register_run(payload, actor="author", trace_id="trace-register")
    service.validate_lineage(
        "sales-propensity", "v-governed", actor="author", trace_id="trace-validate"
    )
    service.submit("sales-propensity", "v-governed", actor="author", trace_id="trace-submit")
    with pytest.raises(ConflictError, match="auto-approval"):
        service.approve("sales-propensity", "v-governed", actor="author", trace_id="trace-self")
    service.approve("sales-propensity", "v-governed", actor="reviewer", trace_id="trace-approve")
    with pytest.raises(ConflictError, match="promote their own"):
        service.promote(
            "sales-propensity", "v-governed", actor="reviewer", trace_id="trace-self-release"
        )
    promoted = service.promote(
        "sales-propensity", "v-governed", actor="release-manager", trace_id="trace-release"
    )
    assert promoted.status == "CHAMPION"
    assert service.champion() == promoted
    assert [event.action for event in service.audits()] == [
        "REGISTERED",
        "LINEAGE_VALIDATED",
        "SUBMITTED",
        "APPROVED",
        "PROMOTED",
    ]
