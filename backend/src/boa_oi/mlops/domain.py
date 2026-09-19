from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Any, ClassVar, Iterable, Mapping, Sequence

NA = "N/A"
Timestamp = date | datetime


def _as_datetime(value: Timestamp) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _valid_score(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
        and 0 <= float(value) <= 1
    )


class FeatureContaminationError(ValueError):
    """Raised when a feature was not observable at the prediction observation time."""


ContaminationError = FeatureContaminationError


@dataclass(frozen=True)
class FeatureLineage:
    feature_name: str
    feature_timestamp: Timestamp
    observation_as_of: Timestamp
    source: str = "unknown"
    source_record_id: str | None = None

    @property
    def is_temporally_valid(self) -> bool:
        return _as_datetime(self.feature_timestamp) <= _as_datetime(self.observation_as_of)

    def validate(self) -> None:
        if not self.is_temporally_valid:
            raise FeatureContaminationError(
                f"featureTimestamp ({self.feature_timestamp.isoformat()}) is after "
                f"observationAsOf ({self.observation_as_of.isoformat()}) for {self.feature_name}"
            )


# Clear aliases make the boundary usable by ingestion code without introducing adapters.
FeatureObservation = FeatureLineage
FeatureRecord = FeatureLineage


@dataclass(frozen=True)
class TrainingExample:
    entity_id: str
    observation_as_of: Timestamp
    features: tuple[FeatureLineage, ...] = ()
    label: int | bool | None = None
    label_available_from: Timestamp | None = None
    treatment: int | bool | None = None
    score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        for feature in self.features:
            if feature.observation_as_of != self.observation_as_of:
                raise ValueError("feature observationAsOf must match the training example")

    def validate_temporal_integrity(self) -> None:
        for feature in self.features:
            feature.validate()

    @property
    def is_label_mature(self) -> bool:
        return self.label_available_from is not None


@dataclass(frozen=True)
class TrainingLineage:
    dataset_id: str
    feature_set_version: str
    training_cutoff: Timestamp
    examples: tuple[TrainingExample, ...] = ()
    source_snapshots: tuple[str, ...] = ()
    code_revision: str | None = None
    label_definition: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "examples", tuple(self.examples))
        object.__setattr__(self, "source_snapshots", tuple(self.source_snapshots))

    def validate(self) -> None:
        for example in self.examples:
            example.validate_temporal_integrity()
            if _as_datetime(example.observation_as_of) > _as_datetime(self.training_cutoff):
                raise ValueError("training examples cannot be after the training cutoff")

    @property
    def contaminated_examples(self) -> tuple[TrainingExample, ...]:
        return tuple(
            example
            for example in self.examples
            if any(not feature.is_temporally_valid for feature in example.features)
        )


TrainingDatasetLineage = TrainingLineage


@dataclass(frozen=True)
class ContaminationFinding:
    entity_id: str
    feature_name: str
    feature_timestamp: Timestamp
    observation_as_of: Timestamp


def contamination_findings(examples: Iterable[TrainingExample]) -> tuple[ContaminationFinding, ...]:
    findings: list[ContaminationFinding] = []
    for example in examples:
        for feature in example.features:
            if not feature.is_temporally_valid:
                findings.append(
                    ContaminationFinding(
                        example.entity_id,
                        feature.feature_name,
                        feature.feature_timestamp,
                        feature.observation_as_of,
                    )
                )
    return tuple(findings)


def validate_temporal_integrity(
    dataset_or_examples: TrainingLineage | Iterable[TrainingExample],
) -> None:
    examples = (
        dataset_or_examples.examples
        if isinstance(dataset_or_examples, TrainingLineage)
        else tuple(dataset_or_examples)
    )
    findings = contamination_findings(examples)
    if findings:
        first = findings[0]
        raise FeatureContaminationError(
            f"temporal contamination detected for {first.entity_id}/{first.feature_name}: "
            f"featureTimestamp={first.feature_timestamp.isoformat()} > "
            f"observationAsOf={first.observation_as_of.isoformat()} ({len(findings)} finding(s))"
        )


class SplitName(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


@dataclass(frozen=True)
class TemporalSplit:
    train_end: Timestamp
    validation_end: Timestamp
    test_end: Timestamp | None = None

    def __post_init__(self) -> None:
        if _as_datetime(self.train_end) >= _as_datetime(self.validation_end):
            raise ValueError("train_end must be before validation_end")
        if self.test_end is not None and _as_datetime(self.validation_end) >= _as_datetime(
            self.test_end
        ):
            raise ValueError("validation_end must be before test_end")

    def assign(self, observation_as_of: Timestamp) -> SplitName:
        value = _as_datetime(observation_as_of)
        if value <= _as_datetime(self.train_end):
            return SplitName.TRAIN
        if value <= _as_datetime(self.validation_end):
            return SplitName.VALIDATION
        if self.test_end is None or value <= _as_datetime(self.test_end):
            return SplitName.TEST
        raise ValueError("observation is after the configured test boundary")

    def split(
        self, examples: Iterable[TrainingExample]
    ) -> dict[SplitName, tuple[TrainingExample, ...]]:
        result: dict[SplitName, list[TrainingExample]] = {name: [] for name in SplitName}
        ordered = sorted(examples, key=lambda item: _as_datetime(item.observation_as_of))
        for example in ordered:
            result[self.assign(example.observation_as_of)].append(example)
        return {name: tuple(values) for name, values in result.items()}


TemporalSplitPlan = TemporalSplit


def temporal_split(
    examples: Iterable[TrainingExample], split: TemporalSplit
) -> dict[SplitName, tuple[TrainingExample, ...]]:
    return split.split(examples)


class LabelMaturity(StrEnum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    MISSING = "MISSING"


@dataclass(frozen=True)
class LabelDefinition:
    name: str
    horizon_days: int
    maturity_days: int | None = None

    def __post_init__(self) -> None:
        if self.horizon_days < 0 or (self.maturity_days is not None and self.maturity_days < 0):
            raise ValueError("label horizons cannot be negative")

    def matures_on(self, observation_as_of: Timestamp) -> datetime:
        return _as_datetime(observation_as_of) + timedelta(
            days=self.maturity_days if self.maturity_days is not None else self.horizon_days
        )


@dataclass(frozen=True)
class LabelObservation:
    observation_as_of: Timestamp
    label: int | bool | None
    label_available_from: Timestamp | None = None
    definition: LabelDefinition | None = None

    def maturity(self, evaluated_as_of: Timestamp | None = None) -> LabelMaturity:
        if self.label is None or self.label_available_from is None:
            return LabelMaturity.MISSING
        if evaluated_as_of is None or _as_datetime(self.label_available_from) <= _as_datetime(
            evaluated_as_of
        ):
            return LabelMaturity.MATURE
        return LabelMaturity.IMMATURE

    @property
    def is_mature(self) -> bool:
        return self.maturity() == LabelMaturity.MATURE


@dataclass(frozen=True)
class LabelMaturityReport:
    status: LabelMaturity
    mature_count: int
    immature_count: int
    missing_count: int

    @property
    def training_ready(self) -> bool:
        return (
            self.status == LabelMaturity.MATURE
            and self.mature_count > 0
            and self.immature_count == 0
            and self.missing_count == 0
        )


def assess_label_maturity(
    labels: Iterable[LabelObservation], evaluated_as_of: Timestamp
) -> LabelMaturityReport:
    observations = tuple(labels)
    statuses = [item.maturity(evaluated_as_of) for item in observations]
    mature = statuses.count(LabelMaturity.MATURE)
    immature = statuses.count(LabelMaturity.IMMATURE)
    missing = statuses.count(LabelMaturity.MISSING)
    status = (
        LabelMaturity.MATURE
        if observations and immature == 0 and missing == 0
        else LabelMaturity.IMMATURE
        if immature
        else LabelMaturity.MISSING
    )
    return LabelMaturityReport(status, mature, immature, missing)


validate_label_maturity = assess_label_maturity


@dataclass(frozen=True)
class MetricReport:
    precision_at_k: float | str = NA
    recall_at_k: float | str = NA
    pr_auc: float | str = NA
    calibration: float | str = NA
    lift: float | str = NA
    uplift: float | str = NA

    def as_dict(self) -> dict[str, float | str]:
        return {
            "Precision@K": self.precision_at_k,
            "Recall@K": self.recall_at_k,
            "PR-AUC": self.pr_auc,
            "calibration": self.calibration,
            "lift": self.lift,
            "uplift": self.uplift,
        }

    @property
    def calibration_error(self) -> float | str:
        return self.calibration


EvaluationMetrics = MetricReport


def _usable_inputs(scores: Sequence[float], labels: Sequence[int | bool]) -> bool:
    return (
        bool(scores)
        and len(scores) == len(labels)
        and all(_valid_score(score) for score in scores)
        and all(label in (0, 1, False, True) for label in labels)
    )


def _top_k_indices(scores: Sequence[float], k: int | float) -> list[int]:
    count = (max(1, int(len(scores) * k)) if 0 < k <= 1 else int(k)) if isinstance(k, float) else k
    if count <= 0 or count > len(scores):
        return []
    return sorted(range(len(scores)), key=lambda index: (-float(scores[index]), index))[:count]


def _average_precision(scores: Sequence[float], labels: Sequence[int | bool]) -> float | str:
    positives = sum(bool(label) for label in labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return NA
    order = sorted(range(len(scores)), key=lambda index: (-float(scores[index]), index))
    hits = 0
    total = 0.0
    for rank, index in enumerate(order, 1):
        if labels[index]:
            hits += 1
            total += hits / rank
    return total / positives


def evaluate_metrics(
    scores: Sequence[float],
    labels: Sequence[int | bool],
    k: int | float = 10,
    *,
    treatment: Sequence[int | bool] | None = None,
) -> MetricReport:
    if not _usable_inputs(scores, labels):
        return MetricReport()
    indices = _top_k_indices(scores, k)
    positives = sum(bool(label) for label in labels)
    if not indices or positives == 0:
        return MetricReport(pr_auc=_average_precision(scores, labels))
    top_positives = sum(bool(labels[index]) for index in indices)
    precision = top_positives / len(indices)
    recall = top_positives / positives
    base_rate = positives / len(labels)
    lift = precision / base_rate if base_rate > 0 else NA
    # Expected calibration error (lower is better), with ten fixed probability bins.
    bins: list[list[int]] = [[] for _ in range(10)]
    for index, score in enumerate(scores):
        bins[min(9, int(float(score) * 10))].append(index)
    calibration = sum(
        (len(bucket) / len(scores))
        * abs(
            sum(float(scores[i]) for i in bucket) / len(bucket)
            - sum(bool(labels[i]) for i in bucket) / len(bucket)
        )
        for bucket in bins
        if bucket
    )
    uplift: float | str = NA
    if (
        treatment is not None
        and len(treatment) == len(labels)
        and all(value in (0, 1, False, True) for value in treatment)
    ):
        top_treated = [i for i in indices if treatment[i]]
        top_control = [i for i in indices if not treatment[i]]
        if top_treated and top_control:
            uplift = sum(bool(labels[i]) for i in top_treated) / len(top_treated) - sum(
                bool(labels[i]) for i in top_control
            ) / len(top_control)
    return MetricReport(
        precision, recall, _average_precision(scores, labels), calibration, lift, uplift
    )


calculate_metrics = evaluate_metrics


class ModelStatus(StrEnum):
    REGISTERED = "REGISTERED"
    VALIDATING = "VALIDATING"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CHAMPION = "CHAMPION"
    RETIRED = "RETIRED"


@dataclass
class ModelVersion:
    model_id: str
    model_version: str
    artifact_uri: str = ""
    status: ModelStatus = ModelStatus.REGISTERED
    approved_by: str | None = None
    approval_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.model_id}:{self.model_version}"


class RegistryTransitionError(ValueError):
    """Raised for an invalid model registry transition or unauthorized promotion."""


class ModelRegistry:
    _transitions: ClassVar[dict[ModelStatus, set[ModelStatus]]] = {
        ModelStatus.REGISTERED: {ModelStatus.VALIDATING},
        ModelStatus.VALIDATING: {ModelStatus.SUBMITTED},
        ModelStatus.SUBMITTED: {ModelStatus.APPROVED},
        ModelStatus.APPROVED: {ModelStatus.CHAMPION},
        ModelStatus.CHAMPION: {ModelStatus.RETIRED},
        ModelStatus.RETIRED: set(),
    }

    def __init__(self) -> None:
        self._models: dict[str, ModelVersion] = {}
        self._champion_key: str | None = None
        self._previous_champion_key: str | None = None

    @property
    def models(self) -> tuple[ModelVersion, ...]:
        return tuple(self._models.values())

    @property
    def champion(self) -> ModelVersion | None:
        return self._models.get(self._champion_key) if self._champion_key else None

    def register(self, model: ModelVersion) -> ModelVersion:
        if model.status != ModelStatus.REGISTERED:
            raise RegistryTransitionError("new models must be REGISTERED")
        if model.key in self._models:
            raise RegistryTransitionError(f"model already registered: {model.key}")
        self._models[model.key] = model
        return model

    def get(self, key: str) -> ModelVersion:
        try:
            return self._models[key]
        except KeyError as exc:
            raise RegistryTransitionError(f"unknown model: {key}") from exc

    def transition(
        self, key: str, target: ModelStatus, *, actor: str | None = None, reason: str | None = None
    ) -> ModelVersion:
        model = self.get(key)
        if target not in self._transitions[model.status]:
            raise RegistryTransitionError(f"invalid transition {model.status} -> {target}")
        if target == ModelStatus.APPROVED and not actor:
            raise RegistryTransitionError("approval requires an actor")
        model.status = target
        if target == ModelStatus.APPROVED:
            model.approved_by, model.approval_reason = actor, reason
        return model

    def promote(self, key: str, *, actor: str | None = None) -> ModelVersion:
        model = self.get(key)
        if model.status != ModelStatus.APPROVED:
            raise RegistryTransitionError("only an APPROVED model can be promoted")
        if not model.approved_by:
            raise RegistryTransitionError("promotion requires recorded approval")
        if self._champion_key:
            current = self.get(self._champion_key)
            current.status = ModelStatus.RETIRED
            self._previous_champion_key = current.key
        model.status = ModelStatus.CHAMPION
        self._champion_key = model.key
        return model

    def rollback(
        self, to_key: str | None = None, *, actor: str | None = None, reason: str | None = None
    ) -> ModelVersion:
        if not self._champion_key:
            raise RegistryTransitionError("there is no champion to roll back")
        current = self.get(self._champion_key)
        target_key = to_key or self._previous_champion_key
        if not target_key or target_key not in self._models:
            raise RegistryTransitionError("no rollback target is available")
        target = self.get(target_key)
        if target.status != ModelStatus.RETIRED:
            raise RegistryTransitionError("rollback target must be RETIRED")
        current.status = ModelStatus.RETIRED
        target.status = ModelStatus.CHAMPION
        self._champion_key = target.key
        self._previous_champion_key = current.key
        return target


ModelRegistryWorkflow = ModelRegistry
Registry = ModelRegistry

__all__ = [
    "NA",
    "ContaminationError",
    "ContaminationFinding",
    "EvaluationMetrics",
    "FeatureContaminationError",
    "FeatureLineage",
    "FeatureObservation",
    "FeatureRecord",
    "LabelDefinition",
    "LabelMaturity",
    "LabelMaturityReport",
    "LabelObservation",
    "MetricReport",
    "ModelRegistry",
    "ModelRegistryWorkflow",
    "ModelStatus",
    "ModelVersion",
    "Registry",
    "RegistryTransitionError",
    "SplitName",
    "TemporalSplit",
    "TemporalSplitPlan",
    "TrainingDatasetLineage",
    "TrainingExample",
    "TrainingLineage",
    "assess_label_maturity",
    "calculate_metrics",
    "contamination_findings",
    "evaluate_metrics",
    "temporal_split",
    "validate_label_maturity",
    "validate_temporal_integrity",
]
