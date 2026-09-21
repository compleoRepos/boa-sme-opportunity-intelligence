"""Application service for the POC-assistive ML governance workflow.

The service deliberately does not train models or make performance claims.  It records
reproducible run metadata, delegates temporal checks and evaluation to the pure domain,
and keeps every state mutation auditable.  ``InMemoryModelRepository`` is useful for
local/API tests; ``SqlAlchemyModelRepository`` can be supplied by a service process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Protocol
from uuid import UUID

from boa_oi.ml.governance import POC_SHADOW, activation_blockers

from .domain import (
    FeatureLineage,
    LabelDefinition,
    LabelObservation,
    ModelStatus,
    TrainingExample,
    TrainingLineage,
    assess_label_maturity,
    evaluate_metrics,
    validate_temporal_integrity,
)

try:  # SQLAlchemy is optional for the pure in-memory API path.
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from boa_oi.models.entities import (
        FeatureMaterialization,
        MLDatasetManifest,
        MLEvaluationSnapshot,
        MLGovernanceAuditLog,
        MLTrainingRun,
        ModelRegistry,
        OutcomeLabelSnapshot,
    )
except ImportError:  # pragma: no cover - only exercised in minimal environments.
    Session = Any  # type: ignore[misc,assignment]
    FeatureMaterialization = MLDatasetManifest = MLEvaluationSnapshot = None  # type: ignore[assignment,misc]
    MLGovernanceAuditLog = MLTrainingRun = ModelRegistry = OutcomeLabelSnapshot = None  # type: ignore[assignment,misc]


class GovernanceError(ValueError):
    """A domain-safe error suitable for translating to an HTTP 4xx response."""


class NotFoundError(GovernanceError):
    pass


class ConflictError(GovernanceError):
    pass


class ValidationError(GovernanceError):
    pass


@dataclass(frozen=True)
class AuditEntry:
    action: str
    user_id: str
    object_type: str
    object_id: str
    object_version: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    reason: str | None
    trace_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "userId": self.user_id,
            "objectType": self.object_type,
            "objectId": self.object_id,
            "objectVersion": self.object_version,
            "oldValue": self.old_value,
            "newValue": self.new_value,
            "reason": self.reason,
            "traceId": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RunRecord:
    model_id: str
    model_version: str
    feature_version: str
    dataset_version: str
    training_period_from: date
    training_period_to: date
    validation_period_from: date
    validation_period_to: date
    test_period_from: date | None
    test_period_to: date | None
    code_version: str
    hyperparameters: dict[str, Any]
    metrics: dict[str, Any]
    lineage: TrainingLineage
    deployment_mode: str = POC_SHADOW
    dataset_manifest_hash: str | None = None
    artifact_checksum: str | None = None
    source_kind: str = "UNKNOWN"
    activation_gate_status: str = "BLOCKED"
    activation_gate_blockers: list[str] = field(default_factory=list)
    status: str = ModelStatus.REGISTERED.value
    approved_by: str | None = None
    approved_at: datetime | None = None
    author: str = "unknown"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    validation: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.model_id}:{self.model_version}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "featureVersion": self.feature_version,
            "datasetVersion": self.dataset_version,
            "trainingPeriodFrom": self.training_period_from.isoformat(),
            "trainingPeriodTo": self.training_period_to.isoformat(),
            "validationPeriodFrom": self.validation_period_from.isoformat(),
            "validationPeriodTo": self.validation_period_to.isoformat(),
            "testPeriodFrom": self.test_period_from.isoformat() if self.test_period_from else None,
            "testPeriodTo": self.test_period_to.isoformat() if self.test_period_to else None,
            "codeVersion": self.code_version,
            "hyperparameters": self.hyperparameters,
            "metrics": self.metrics,
            "lineage": _lineage_payload(self.lineage),
            "deploymentMode": self.deployment_mode,
            "datasetManifestHash": self.dataset_manifest_hash,
            "artifactChecksum": self.artifact_checksum,
            "sourceKind": self.source_kind,
            "activationGateStatus": self.activation_gate_status,
            "activationGateBlockers": self.activation_gate_blockers,
            "status": self.status,
            "approvedBy": self.approved_by,
            "approvedAt": self.approved_at.isoformat() if self.approved_at else None,
            "author": self.author,
            "validation": self.validation,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


def _timestamp(value: date | datetime) -> str:
    return value.isoformat()


def _lineage_payload(lineage: TrainingLineage) -> dict[str, Any]:
    return {
        "datasetId": lineage.dataset_id,
        "featureSetVersion": lineage.feature_set_version,
        "trainingCutoff": _timestamp(lineage.training_cutoff),
        "sourceSnapshots": list(lineage.source_snapshots),
        "codeRevision": lineage.code_revision,
        "labelDefinition": lineage.label_definition,
        "datasetManifestHash": lineage.dataset_manifest_hash,
        "sourceKind": lineage.source_kind,
        "targetOutcome": lineage.target_outcome,
        "horizonDays": lineage.horizon_days,
        "population": dict(lineage.population),
        "examples": [
            {
                "entityId": example.entity_id,
                "observationAsOf": _timestamp(example.observation_as_of),
                "label": example.label,
                "labelAvailableFrom": (
                    _timestamp(example.label_available_from)
                    if example.label_available_from is not None
                    else None
                ),
                "treatment": example.treatment,
                "score": example.score,
                "features": [
                    {
                        "featureName": feature.feature_name,
                        "featureTimestamp": _timestamp(feature.feature_timestamp),
                        "observationAsOf": _timestamp(feature.observation_as_of),
                        "source": feature.source,
                        "sourceRecordId": feature.source_record_id,
                        "sourceAvailableAt": (
                            _timestamp(feature.source_available_at)
                            if feature.source_available_at is not None
                            else None
                        ),
                    }
                    for feature in example.features
                ],
            }
            for example in lineage.examples
        ],
    }


class GovernanceRepository(Protocol):
    def add(self, run: RunRecord) -> RunRecord: ...
    def get(self, key: str) -> RunRecord: ...
    def save(self, run: RunRecord) -> RunRecord: ...
    def all(self) -> list[RunRecord]: ...
    def audit(self, entry: AuditEntry) -> AuditEntry: ...
    def audits(self) -> list[AuditEntry]: ...


class InMemoryModelRepository:
    """Deterministic repository used by tests and the no-database POC deployment."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._audits: list[AuditEntry] = []

    def add(self, run: RunRecord) -> RunRecord:
        if run.key in self._runs:
            raise ConflictError(f"run already exists: {run.key}")
        self._runs[run.key] = run
        return run

    def get(self, key: str) -> RunRecord:
        try:
            return self._runs[key]
        except KeyError as exc:
            raise NotFoundError(f"unknown model run: {key}") from exc

    def save(self, run: RunRecord) -> RunRecord:
        if run.key not in self._runs:
            raise NotFoundError(f"unknown model run: {run.key}")
        run.updated_at = datetime.now(timezone.utc)
        self._runs[run.key] = run
        return run

    def all(self) -> list[RunRecord]:
        return list(self._runs.values())

    def audit(self, entry: AuditEntry) -> AuditEntry:
        self._audits.append(entry)
        return entry

    def audits(self) -> list[AuditEntry]:
        return list(self._audits)


class SqlAlchemyModelRepository(InMemoryModelRepository):
    """Repository adapter for the existing ``ml`` entities.

    The in-memory index remains the source for domain objects during one request, while
    writes are mirrored to SQLAlchemy when a session is supplied. This keeps the service
    usable with SQLite/unit-test sessions and does not require model training workers.
    """

    def __init__(self, session: Session | None = None) -> None:
        super().__init__()
        self.session = session
        if session is not None and MLTrainingRun is not None:
            for entity in session.scalars(select(MLTrainingRun)).all():
                lineage = lineage_from_payload(
                    {"lineage": dict(entity.lineage_json or {})},
                    defaults={
                        "dataset_version": entity.dataset_version,
                        "feature_version": entity.feature_version,
                        "training_period_to": entity.training_period_to,
                        "code_version": entity.code_version,
                    },
                )
                metrics = dict(entity.metrics_json or {})
                validation = dict(metrics.pop("_governanceValidation", {}) or {})
                self._runs[f"{entity.model_id}:{entity.model_version}"] = RunRecord(
                    entity.model_id,
                    entity.model_version,
                    entity.feature_version,
                    entity.dataset_version,
                    entity.training_period_from,
                    entity.training_period_to,
                    entity.validation_period_from,
                    entity.validation_period_to,
                    entity.test_period_from,
                    entity.test_period_to,
                    entity.code_version,
                    dict(entity.hyperparameters_json or {}),
                    metrics,
                    lineage,
                    deployment_mode=entity.deployment_mode,
                    dataset_manifest_hash=entity.dataset_manifest_hash,
                    artifact_checksum=entity.artifact_checksum,
                    source_kind=lineage.source_kind,
                    activation_gate_status=entity.activation_gate_status,
                    activation_gate_blockers=list(validation.get("activationBlockers", [])),
                    status=entity.status,
                    approved_by=entity.approved_by,
                    approved_at=entity.approved_at,
                    author=entity.created_by,
                    validation=validation,
                )
            if MLGovernanceAuditLog is not None:
                for audit_entity in session.scalars(
                    select(MLGovernanceAuditLog).order_by(MLGovernanceAuditLog.timestamp)
                ).all():
                    self._audits.append(
                        AuditEntry(
                            audit_entity.action,
                            audit_entity.user_id,
                            audit_entity.object_type,
                            audit_entity.object_id,
                            audit_entity.object_version,
                            audit_entity.old_value_json,
                            audit_entity.new_value_json,
                            audit_entity.reason,
                            audit_entity.trace_id,
                            audit_entity.timestamp,
                        )
                    )

    def _flush(self) -> None:
        if self.session is not None:
            self.session.flush()

    def add(self, run: RunRecord) -> RunRecord:
        result = super().add(run)
        if self.session is not None and MLTrainingRun is not None:
            self.session.add(
                MLTrainingRun(
                    model_id=run.model_id,
                    model_version=run.model_version,
                    feature_version=run.feature_version,
                    dataset_version=run.dataset_version,
                    training_period_from=run.training_period_from,
                    training_period_to=run.training_period_to,
                    validation_period_from=run.validation_period_from,
                    validation_period_to=run.validation_period_to,
                    test_period_from=run.test_period_from,
                    test_period_to=run.test_period_to,
                    code_version=run.code_version,
                    hyperparameters_json=run.hyperparameters,
                    metrics_json={
                        **run.metrics,
                        "_governanceValidation": run.validation,
                    },
                    lineage_json=_lineage_payload(run.lineage),
                    deployment_mode=run.deployment_mode,
                    dataset_manifest_hash=run.dataset_manifest_hash,
                    activation_gate_status=run.activation_gate_status,
                    artifact_checksum=run.artifact_checksum,
                    status=run.status,
                    created_by=run.author,
                )
            )
            self._flush()
        return result

    def save(self, run: RunRecord) -> RunRecord:
        result = super().save(run)
        if self.session is not None and MLTrainingRun is not None:
            entity = self.session.scalar(
                select(MLTrainingRun).where(
                    MLTrainingRun.model_id == run.model_id,
                    MLTrainingRun.model_version == run.model_version,
                )
            )
            if entity is not None:
                entity.status = run.status
                entity.approved_by = run.approved_by
                entity.approved_at = run.approved_at
                entity.metrics_json = {
                    **run.metrics,
                    "_governanceValidation": run.validation,
                }
                entity.hyperparameters_json = run.hyperparameters
                entity.lineage_json = _lineage_payload(run.lineage)
                entity.deployment_mode = run.deployment_mode
                entity.dataset_manifest_hash = run.dataset_manifest_hash
                entity.activation_gate_status = run.activation_gate_status
                entity.artifact_checksum = run.artifact_checksum
                self._flush()
        return result

    def audit(self, entry: AuditEntry) -> AuditEntry:
        result = super().audit(entry)
        if self.session is not None and MLGovernanceAuditLog is not None:
            self.session.add(
                MLGovernanceAuditLog(
                    action=entry.action,
                    user_id=entry.user_id,
                    object_type=entry.object_type,
                    object_id=entry.object_id,
                    object_version=entry.object_version,
                    old_value_json=entry.old_value,
                    new_value_json=entry.new_value,
                    reason=entry.reason,
                    trace_id=entry.trace_id,
                    timestamp=entry.timestamp,
                )
            )
            self._flush()
        return result

    def promote_registry(self, run: RunRecord, actor: str) -> None:
        if self.session is None or ModelRegistry is None:
            return
        target = self.session.scalar(
            select(ModelRegistry).where(ModelRegistry.model_version == run.model_version)
        )
        if target is None:
            raise ConflictError("the approved run has no registered inference artifact")
        current_champions = self.session.scalars(
            select(ModelRegistry).where(
                ModelRegistry.status.in_(("CHAMPION", "ACTIVE")),
                ModelRegistry.id != target.id,
            )
        ).all()
        for current in current_champions:
            current.status = "RETIRED"
            current.retired_at = datetime.now(timezone.utc)
        if current_champions:
            self._flush()
        target.status = "CHAMPION"
        target.approved_by = run.approved_by or actor
        target.approved_at = run.approved_at or datetime.now(timezone.utc)
        target.training_period_from = run.training_period_from
        target.training_period_to = run.training_period_to
        target.validation_period_from = run.validation_period_from
        target.validation_period_to = run.validation_period_to
        target.hyperparameters_json = run.hyperparameters
        self._flush()

    def activation_evidence_blockers(self, run: RunRecord) -> list[str]:
        if (
            self.session is None
            or MLDatasetManifest is None
            or MLEvaluationSnapshot is None
            or OutcomeLabelSnapshot is None
            or FeatureMaterialization is None
        ):
            return ["PERSISTED_ACTIVATION_EVIDENCE_UNAVAILABLE"]
        blockers: list[str] = []
        manifest = self.session.scalar(
            select(MLDatasetManifest).where(
                MLDatasetManifest.manifest_hash == run.dataset_manifest_hash
            )
        )
        if manifest is None:
            return ["DATASET_MANIFEST_NOT_FOUND"]
        if manifest.source_kind != "BOA_HISTORICAL_OBSERVED":
            blockers.append("PERSISTED_MANIFEST_SOURCE_NOT_BOA_HISTORICAL")
        if manifest.status != "VALIDATED" or manifest.blockers_json:
            blockers.append("PERSISTED_MANIFEST_NOT_VALIDATED")
        if (
            manifest.target_outcome != run.lineage.target_outcome
            or manifest.horizon_days != run.lineage.horizon_days
            or dict(manifest.population_json or {}) != dict(run.lineage.population)
        ):
            blockers.append("MANIFEST_RUN_CONTRACT_MISMATCH")
        try:
            label_ids = [UUID(str(item)) for item in manifest.label_snapshot_ids_json]
            feature_ids = [UUID(str(item)) for item in manifest.feature_snapshot_ids_json]
        except (TypeError, ValueError):
            blockers.append("MANIFEST_SNAPSHOT_IDENTIFIERS_INVALID")
            label_ids = []
            feature_ids = []
        labels = (
            list(
                self.session.scalars(
                    select(OutcomeLabelSnapshot).where(OutcomeLabelSnapshot.id.in_(label_ids))
                )
            )
            if label_ids
            else []
        )
        if not labels or len(labels) != len(label_ids) or manifest.row_count != len(labels):
            blockers.append("PERSISTED_LABEL_SNAPSHOTS_INCOMPLETE")
        elif any(
            item.source_kind != "BOA_HISTORICAL_OBSERVED"
            or item.candidate_only
            or not item.window_closed
            or item.outcome_value not in (True, False)
            or item.feature_snapshot_id not in feature_ids
            or item.dataset_manifest_hash != manifest.manifest_hash
            or item.label_available_from <= manifest.training_cutoff
            for item in labels
        ):
            blockers.append("PERSISTED_LABELS_NOT_TRAINING_ELIGIBLE")
        feature_count = (
            len(
                list(
                    self.session.scalars(
                        select(FeatureMaterialization.id).where(
                            FeatureMaterialization.id.in_(feature_ids)
                        )
                    )
                )
            )
            if feature_ids
            else 0
        )
        if feature_count != len(feature_ids):
            blockers.append("PERSISTED_FEATURE_SNAPSHOTS_INCOMPLETE")
        evaluation = self.session.scalar(
            select(MLEvaluationSnapshot)
            .where(
                MLEvaluationSnapshot.model_version == run.model_version,
                MLEvaluationSnapshot.dataset_manifest_hash == manifest.manifest_hash,
            )
            .order_by(MLEvaluationSnapshot.created_at.desc())
        )
        if evaluation is None:
            blockers.append("PERSISTED_EVALUATION_NOT_FOUND")
        else:
            criteria = dict(evaluation.acceptance_criteria_json or {})
            metrics = dict(evaluation.metrics_json or {})
            calibration = dict(evaluation.calibration_json or {})
            if (
                evaluation.source_kind != "BOA_HISTORICAL_OBSERVED"
                or evaluation.status != "VALIDATED"
                or evaluation.blockers_json
                or criteria.get("approved") is not True
                or not criteria.get("approvedBy")
                or calibration.get("status") != "VALIDATED"
                or evaluation.created_by == run.author
            ):
                blockers.append("PERSISTED_EVALUATION_NOT_VALIDATED")
            for key in ("brierScore", "expectedCalibrationError"):
                value = metrics.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= float(value) <= 1
                    or calibration.get(key) != value
                ):
                    blockers.append("PERSISTED_EVALUATION_METRICS_INVALID")
        return list(dict.fromkeys(blockers))

    def rollback_registry(self, target: RunRecord, current: RunRecord) -> None:
        if self.session is None or ModelRegistry is None:
            return
        target_row = self.session.scalar(
            select(ModelRegistry).where(ModelRegistry.model_version == target.model_version)
        )
        current_row = self.session.scalar(
            select(ModelRegistry).where(ModelRegistry.model_version == current.model_version)
        )
        if target_row is None or current_row is None:
            raise ConflictError("rollback requires both registered inference artifacts")
        current_row.status = "RETIRED"
        current_row.retired_at = datetime.now(timezone.utc)
        self._flush()
        target_row.status = "CHAMPION"
        target_row.retired_at = None
        self._flush()


def _date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"{field_name} must be an ISO date") from exc
    raise ValidationError(f"{field_name} is required")


def _feature(payload: Mapping[str, Any]) -> FeatureLineage:
    return FeatureLineage(
        str(payload.get("featureName", payload.get("feature_name", "unknown"))),
        _date(
            payload.get("featureTimestamp", payload.get("feature_timestamp")), "featureTimestamp"
        ),
        _date(payload.get("observationAsOf", payload.get("observation_as_of")), "observationAsOf"),
        str(payload.get("source", "unknown")),
        payload.get("sourceRecordId", payload.get("source_record_id")),
        _date(payload["sourceAvailableAt"], "sourceAvailableAt")
        if payload.get("sourceAvailableAt")
        else None,
    )


def _example(payload: Mapping[str, Any]) -> TrainingExample:
    observation = _date(
        payload.get("observationAsOf", payload.get("observation_as_of")), "observationAsOf"
    )
    features = tuple(_feature(item) for item in payload.get("features", ()))
    return TrainingExample(
        str(payload.get("entityId", payload.get("entity_id", "unknown"))),
        observation,
        features,
        payload.get("label"),
        _date(payload["labelAvailableFrom"], "labelAvailableFrom")
        if payload.get("labelAvailableFrom")
        else None,
        payload.get("treatment"),
        payload.get("score"),
    )


def lineage_from_payload(
    payload: Mapping[str, Any], *, defaults: Mapping[str, Any]
) -> TrainingLineage:
    source = payload.get("lineage") or payload.get("trainingLineage") or payload
    examples = tuple(_example(item) for item in source.get("examples", ()))
    return TrainingLineage(
        str(source.get("datasetId", source.get("datasetVersion", defaults["dataset_version"]))),
        str(
            source.get(
                "featureSetVersion", source.get("featureVersion", defaults["feature_version"])
            )
        ),
        _date(source.get("trainingCutoff", defaults["training_period_to"]), "trainingCutoff"),
        examples,
        tuple(str(item) for item in source.get("sourceSnapshots", ())),
        source.get("codeRevision", defaults.get("code_version")),
        source.get("labelDefinition"),
        source.get("datasetManifestHash"),
        str(source.get("sourceKind", "UNKNOWN")),
        source.get("targetOutcome"),
        int(source["horizonDays"]) if source.get("horizonDays") is not None else None,
        dict(source.get("population", {}) or {}),
    )


class MLOpsGovernanceService:
    """State machine facade for registration and governed promotion."""

    def __init__(self, repository: GovernanceRepository | None = None) -> None:
        self.repository = repository or InMemoryModelRepository()
        champions = sorted(
            (run for run in self.repository.all() if run.status == "CHAMPION"),
            key=lambda item: item.updated_at,
        )
        retired = sorted(
            (run for run in self.repository.all() if run.status == "RETIRED"),
            key=lambda item: item.updated_at,
        )
        self._champion_key: str | None = champions[-1].key if champions else None
        self._previous_champion_key: str | None = retired[-1].key if retired else None

    def _audit(
        self,
        action: str,
        run: RunRecord,
        actor: str,
        old: dict[str, Any] | None,
        new: dict[str, Any] | None,
        reason: str | None,
        trace_id: str,
    ) -> None:
        self.repository.audit(
            AuditEntry(
                action,
                actor,
                "MLTrainingRun",
                run.model_id,
                run.model_version,
                old,
                new,
                reason,
                trace_id,
            )
        )

    def register_run(
        self, payload: Mapping[str, Any], *, actor: str, trace_id: str, reason: str | None = None
    ) -> RunRecord:
        model_id = str(payload.get("modelId", payload.get("model_id", "sales-propensity")))
        model_version = str(payload.get("modelVersion", payload.get("model_version", "")))
        if not model_version:
            raise ValidationError("modelVersion is required")
        defaults = {
            "dataset_version": payload.get("datasetVersion", payload.get("dataset_version", "")),
            "feature_version": payload.get("featureVersion", payload.get("feature_version", "")),
            "training_period_to": payload.get(
                "trainingPeriodTo", payload.get("training_period_to")
            ),
            "code_version": payload.get("codeVersion", payload.get("code_version", "")),
        }
        for key in ("dataset_version", "feature_version", "training_period_to", "code_version"):
            if defaults[key] in (None, ""):
                raise ValidationError(f"{key} is required")
        metrics = dict(payload.get("metrics", payload.get("metricsJson", {})) or {})
        lineage = lineage_from_payload(payload, defaults=defaults)
        deployment_mode = str(payload.get("deploymentMode", POC_SHADOW))
        dataset_manifest_hash = payload.get("datasetManifestHash") or lineage.dataset_manifest_hash
        artifact_checksum = payload.get("artifactChecksum")
        blockers = activation_blockers(
            deployment_mode=deployment_mode,
            source_kind=lineage.source_kind,
            dataset_manifest_hash=(
                str(dataset_manifest_hash) if dataset_manifest_hash is not None else None
            ),
            artifact_checksum=(str(artifact_checksum) if artifact_checksum is not None else None),
            lineage_examples=lineage.examples,
            metrics=metrics,
        )
        run = RunRecord(
            model_id,
            model_version,
            str(defaults["feature_version"]),
            str(defaults["dataset_version"]),
            _date(
                payload.get("trainingPeriodFrom", payload.get("training_period_from")),
                "trainingPeriodFrom",
            ),
            _date(defaults["training_period_to"], "trainingPeriodTo"),
            _date(
                payload.get("validationPeriodFrom", payload.get("validation_period_from")),
                "validationPeriodFrom",
            ),
            _date(
                payload.get("validationPeriodTo", payload.get("validation_period_to")),
                "validationPeriodTo",
            ),
            _date(payload["testPeriodFrom"], "testPeriodFrom")
            if payload.get("testPeriodFrom")
            else None,
            _date(payload["testPeriodTo"], "testPeriodTo") if payload.get("testPeriodTo") else None,
            str(defaults["code_version"]),
            dict(payload.get("hyperparameters", payload.get("hyperparametersJson", {})) or {}),
            metrics,
            lineage,
            deployment_mode=deployment_mode,
            dataset_manifest_hash=(
                str(dataset_manifest_hash) if dataset_manifest_hash is not None else None
            ),
            artifact_checksum=(str(artifact_checksum) if artifact_checksum is not None else None),
            source_kind=lineage.source_kind,
            activation_gate_status="BLOCKED" if blockers else "ELIGIBLE",
            activation_gate_blockers=blockers,
            author=actor,
        )
        if run.deployment_mode != POC_SHADOW:
            raise ValidationError("only POC_SHADOW deployment mode is supported")
        if run.training_period_from > run.training_period_to:
            raise ValidationError("training period is not chronological")
        if run.validation_period_from > run.validation_period_to:
            raise ValidationError("validation period is not chronological")
        run.validation = {
            "activationGateStatus": run.activation_gate_status,
            "activationBlockers": run.activation_gate_blockers,
        }
        self.repository.add(run)
        self._audit("REGISTERED", run, actor, None, run.as_dict(), reason, trace_id)
        return run

    def get(self, model_id: str, model_version: str) -> RunRecord:
        return self.repository.get(f"{model_id}:{model_version}")

    def list_runs(self) -> list[RunRecord]:
        return self.repository.all()

    def audits(self) -> list[AuditEntry]:
        return self.repository.audits()

    def champion(self) -> RunRecord | None:
        return self.repository.get(self._champion_key) if self._champion_key else None

    def validate_lineage(
        self,
        model_id: str,
        model_version: str,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
    ) -> RunRecord:
        run = self.get(model_id, model_version)
        old = run.as_dict()
        try:
            validate_temporal_integrity(run.lineage)
            run.lineage.validate()
            result = {
                "valid": True,
                "contaminationFindings": [],
                "errors": [],
                "activationGateStatus": run.activation_gate_status,
                "activationBlockers": run.activation_gate_blockers,
            }
        except (ValueError, TypeError) as exc:
            result = {
                "valid": False,
                "contaminationFindings": [],
                "errors": [str(exc)],
                "activationGateStatus": run.activation_gate_status,
                "activationBlockers": run.activation_gate_blockers,
            }
            run.validation = result
            self.repository.save(run)
            self._audit(
                "LINEAGE_REJECTED", run, actor, old, run.as_dict(), reason or str(exc), trace_id
            )
            raise ValidationError(str(exc)) from exc
        run.validation = result
        if run.status == ModelStatus.REGISTERED.value:
            run.status = ModelStatus.VALIDATING.value
        self.repository.save(run)
        self._audit("LINEAGE_VALIDATED", run, actor, old, run.as_dict(), reason, trace_id)
        return run

    def _transition(
        self, run: RunRecord, target: str, *, actor: str, trace_id: str, reason: str | None
    ) -> RunRecord:
        if run.source_kind == "DEMO_SYNTHETIC_LABELS" or run.status == "DEMO_ONLY":
            raise ConflictError("DEMO_ONLY models cannot enter the governed release workflow")
        old = run.as_dict()
        allowed = {
            "REGISTERED": {"VALIDATING"},
            "VALIDATING": {"SUBMITTED"},
            "SUBMITTED": {"APPROVED"},
            "APPROVED": {"CHAMPION"},
            "CHAMPION": {"RETIRED"},
            "RETIRED": set(),
        }
        if target not in allowed.get(run.status, set()):
            raise ConflictError(f"invalid transition {run.status} -> {target}")
        if target == "APPROVED":
            if actor == run.author:
                raise ConflictError("auto-approval is forbidden")
            run.approved_by, run.approved_at = actor, datetime.now(timezone.utc)
        run.status = target
        self.repository.save(run)
        self._audit(target, run, actor, old, run.as_dict(), reason, trace_id)
        return run

    def submit(
        self,
        model_id: str,
        model_version: str,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
    ) -> RunRecord:
        run = self.get(model_id, model_version)
        if run.source_kind == "DEMO_SYNTHETIC_LABELS" or run.status == "DEMO_ONLY":
            raise ConflictError("DEMO_ONLY models cannot be submitted")
        if not run.validation.get("valid"):
            raise ConflictError("lineage must be validated before submission")
        return self._transition(run, "SUBMITTED", actor=actor, trace_id=trace_id, reason=reason)

    def approve(
        self,
        model_id: str,
        model_version: str,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
    ) -> RunRecord:
        run = self.get(model_id, model_version)
        if run.source_kind == "DEMO_SYNTHETIC_LABELS" or run.status == "DEMO_ONLY":
            raise ConflictError("DEMO_ONLY models cannot be approved")
        return self._transition(
            run,
            "APPROVED",
            actor=actor,
            trace_id=trace_id,
            reason=reason,
        )

    def promote(
        self,
        model_id: str,
        model_version: str,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
    ) -> RunRecord:
        run = self.get(model_id, model_version)
        if run.source_kind == "DEMO_SYNTHETIC_LABELS" or run.status == "DEMO_ONLY":
            raise ConflictError("ML_ACTIVATION_BLOCKED: DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE")
        blockers = activation_blockers(
            deployment_mode=run.deployment_mode,
            source_kind=run.source_kind,
            dataset_manifest_hash=run.dataset_manifest_hash,
            artifact_checksum=run.artifact_checksum,
            lineage_examples=run.lineage.examples,
            metrics=run.metrics,
        )
        evidence_validator = getattr(self.repository, "activation_evidence_blockers", None)
        if evidence_validator is None:
            blockers.append("PERSISTED_ACTIVATION_EVIDENCE_UNAVAILABLE")
        else:
            blockers.extend(evidence_validator(run))
        blockers = list(dict.fromkeys(blockers))
        run.activation_gate_blockers = blockers
        run.activation_gate_status = "BLOCKED" if blockers else "ELIGIBLE"
        run.validation = {
            **run.validation,
            "activationGateStatus": run.activation_gate_status,
            "activationBlockers": blockers,
        }
        self.repository.save(run)
        if blockers:
            raise ConflictError("ML_ACTIVATION_BLOCKED: " + ", ".join(blockers))
        if run.status != "APPROVED" or not run.approved_by:
            raise ConflictError("only an APPROVED model can be promoted")
        if run.approved_by == actor:
            raise ConflictError("approver cannot promote their own approval")
        old = run.as_dict()
        promote_registry = getattr(self.repository, "promote_registry", None)
        if promote_registry is not None:
            promote_registry(run, actor)
        if self._champion_key and self._champion_key != run.key:
            current = self.repository.get(self._champion_key)
            current_old = current.as_dict()
            current.status = "RETIRED"
            self.repository.save(current)
            self._audit(
                "RETIRED",
                current,
                actor,
                current_old,
                current.as_dict(),
                "replaced by champion",
                trace_id,
            )
            self._previous_champion_key = current.key
        run.status = "CHAMPION"
        self._champion_key = run.key
        self.repository.save(run)
        self._audit("PROMOTED", run, actor, old, run.as_dict(), reason, trace_id)
        return run

    def retire(
        self,
        model_id: str,
        model_version: str,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
    ) -> RunRecord:
        run = self.get(model_id, model_version)
        result = self._transition(run, "RETIRED", actor=actor, trace_id=trace_id, reason=reason)
        if self._champion_key == run.key:
            self._champion_key = None
        return result

    def rollback(
        self,
        *,
        actor: str,
        trace_id: str,
        reason: str | None = None,
        to_model_version: str | None = None,
    ) -> RunRecord:
        if not self._champion_key:
            raise ConflictError("there is no champion to roll back")
        target_key = to_model_version or self._previous_champion_key
        if not target_key:
            raise ConflictError("no previously approved model is available for rollback")
        target = self.repository.get(
            target_key if ":" in target_key else f"sales-propensity:{target_key}"
        )
        if target.status != "RETIRED":
            raise ConflictError("rollback target must be RETIRED")
        current = self.repository.get(self._champion_key)
        current_old, target_old = current.as_dict(), target.as_dict()
        rollback_registry = getattr(self.repository, "rollback_registry", None)
        if rollback_registry is not None:
            rollback_registry(target, current)
        current.status, target.status = "RETIRED", "CHAMPION"
        self.repository.save(current)
        self.repository.save(target)
        self._previous_champion_key = current.key
        self._champion_key = target.key
        self._audit("ROLLED_BACK", current, actor, current_old, current.as_dict(), reason, trace_id)
        self._audit(
            "CHAMPION_RESTORED", target, actor, target_old, target.as_dict(), reason, trace_id
        )
        return target

    def evaluate(
        self,
        scores: Iterable[float],
        labels: Iterable[int | bool],
        *,
        k: int | float = 10,
        treatment: Iterable[int | bool] | None = None,
    ) -> dict[str, Any]:
        report = evaluate_metrics(
            list(scores),
            list(labels),
            k=k,
            treatment=list(treatment) if treatment is not None else None,
        )
        return {
            "metrics": report.as_dict(),
            "claim": "POC_SHADOW; descriptive metrics only; no production performance claim",
        }

    def evaluate_labels(
        self, labels: Iterable[Mapping[str, Any]], *, evaluated_as_of: date | datetime
    ) -> dict[str, Any]:
        observations: list[LabelObservation] = []
        for item in labels:
            definition = item.get("definition") or {}
            observations.append(
                LabelObservation(
                    _date(item.get("observationAsOf"), "observationAsOf"),
                    item.get("label", item.get("outcomeValue")),
                    _date(item.get("labelAvailableFrom"), "labelAvailableFrom")
                    if item.get("labelAvailableFrom")
                    else None,
                    LabelDefinition(
                        str(definition.get("name", "outcome")),
                        int(definition.get("horizonDays", 0)),
                        definition.get("maturityDays"),
                    ),
                )
            )
        report = assess_label_maturity(observations, evaluated_as_of)
        return {
            "status": report.status.value,
            "matureCount": report.mature_count,
            "immatureCount": report.immature_count,
            "missingCount": report.missing_count,
            "trainingReady": report.training_ready,
        }

    def record_label_evaluation(
        self,
        *,
        actor: str,
        trace_id: str,
        source_kind: str,
        result: Mapping[str, Any],
    ) -> None:
        self.repository.audit(
            AuditEntry(
                action="LABEL_MATURITY_EVALUATED",
                user_id=actor,
                object_type="MLLabelEvaluation",
                object_id=trace_id,
                object_version="1.0",
                old_value=None,
                new_value={"sourceKind": source_kind, **dict(result)},
                reason="POC_SHADOW label maturity assessment",
                trace_id=trace_id,
            )
        )


# Friendly aliases used by callers that prefer shorter names.
MLOpsService = MLOpsGovernanceService
ModelGovernanceService = MLOpsGovernanceService
InMemoryRepository = InMemoryModelRepository

__all__ = [
    "AuditEntry",
    "ConflictError",
    "GovernanceError",
    "GovernanceRepository",
    "InMemoryModelRepository",
    "MLOpsGovernanceService",
    "MLOpsService",
    "ModelGovernanceService",
    "NotFoundError",
    "RunRecord",
    "SqlAlchemyModelRepository",
    "ValidationError",
    "lineage_from_payload",
]
