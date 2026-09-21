from __future__ import annotations

from datetime import date, timedelta
from typing import cast
from uuid import UUID

import pytest
from boa_oi.ml_training.service import (
    ALGORITHM,
    STEPS,
    create_training_job,
    execute_training_job,
    request_cancellation,
)
from boa_oi.mlops.routes import GovernancePayload
from boa_oi.models.entities import (
    MLDatasetManifest,
    MLGovernanceAuditLog,
    MLTrainingExample,
    MLTrainingJob,
)
from boa_oi.platform import Problem
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def training_factory(monkeypatch: pytest.MonkeyPatch) -> sessionmaker[Session]:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'ml'")
        for model in (
            MLDatasetManifest,
            MLTrainingExample,
            MLTrainingJob,
            MLGovernanceAuditLog,
        ):
            cast(Table, model.__mapper__.local_table).create(connection)
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_manifest(
    factory: sessionmaker[Session],
    *,
    version: str,
    status: str = "TRAINING_READY",
    count: int = 240,
    positives: int = 48,
    source_kind: str = "DEMO_SYNTHETIC_LABELS",
) -> UUID:
    manifest_id = deterministic_uuid("test-ml-manifest", version)
    with factory.begin() as session:
        session.add(
            MLDatasetManifest(
                id=manifest_id,
                manifest_version=version,
                source_kind=source_kind,
                purpose=(
                    "DEMONSTRATION_ONLY" if source_kind == "DEMO_SYNTHETIC_LABELS" else "TRAINING"
                ),
                target_outcome="ANY_COMMERCIAL_OPPORTUNITY",
                label_definition_version="commercial-conversion-90d-v1",
                horizon_days=90,
                population_json={"segment": "PME", "featureSetVersion": "sales-features-v2"},
                exclusions_json=[],
                training_cutoff=date(2026, 9, 1),
                feature_snapshot_ids_json=[],
                label_snapshot_ids_json=[],
                row_count=count,
                manifest_hash=f"{len(version):064x}"[-64:],
                status=status,
                blockers_json=["BOA_HISTORICAL_LABELS_UNAVAILABLE"] if status == "BLOCKED" else [],
                created_by="test",
            )
        )
        for index in range(count):
            observed = date(2026, 1, 1) + timedelta(days=index)
            label = index < positives
            session.add(
                MLTrainingExample(
                    id=deterministic_uuid("test-ml-example", version, index),
                    manifest_id=manifest_id,
                    entity_ref=f"SME-{index:05d}",
                    split="TRAIN" if index < int(count * 0.8) else "TEST",
                    observation_as_of=observed,
                    label_available_from=observed + timedelta(days=90),
                    feature_values_json={
                        "growth": 0.8 if label else 0.2,
                        "signal": 0.7 if label else 0.1,
                    },
                    label=label,
                    source_kind=source_kind,
                )
            )
    return manifest_id


def create_job(
    factory: sessionmaker[Session], manifest_id: UUID, key: str = "training-key-0001"
) -> UUID:
    with factory.begin() as session:
        job, created = create_training_job(
            session,
            manifest_id=manifest_id,
            algorithm=ALGORITHM,
            seed=42,
            justification="Entraînement explicite pour la démonstration contrôlée",
            author="karim.bennani",
            idempotency_key=key,
            correlation_id="trace-training",
        )
        assert created
        return job.id


def test_training_progresses_through_all_steps_and_produces_demo_only_payload(
    training_factory: sessionmaker[Session],
) -> None:
    manifest_id = add_manifest(training_factory, version="demo-complete")
    job_id = create_job(training_factory, manifest_id)

    execute_training_job(training_factory, job_id)

    with training_factory() as session:
        row = session.get(MLTrainingJob, job_id)
        assert row is not None
        assert row.status == "SUCCEEDED"
        assert row.percentage == 100
        assert [step["name"] for step in row.steps_json] == [step[0] for step in STEPS]
        assert all(step["status"] == "COMPLETED" for step in row.steps_json)
        assert row.result_json["registryStatus"] == "DEMO_ONLY"
        assert row.result_json["promotable"] is False
        assert row.result_json["promotionBlockers"] == ["DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE"]
        assert row.result_json["hyperparameters"]["cpuOnly"] is True
        assert row.result_json["artifact"]["algorithm"] == ALGORITHM
        assert row.result_json["metrics"]["sampleCount"] == 48
        assert GovernancePayload.model_validate(row.result_json).registryStatus == "DEMO_ONLY"


def test_training_stops_cleanly_below_minimum_examples(
    training_factory: sessionmaker[Session],
) -> None:
    manifest_id = add_manifest(training_factory, version="too-small", count=199, positives=40)
    job_id = create_job(training_factory, manifest_id, "training-key-small")

    execute_training_job(training_factory, job_id)

    with training_factory() as session:
        row = session.get(MLTrainingJob, job_id)
        assert row is not None
        assert row.status == "INSUFFICIENT_DATA"
        assert row.result_json is None
        assert row.error_json["code"] == "INSUFFICIENT_DATA"
        assert row.error_json["details"]["minimumExamples"] == 200
        assert row.error_json["details"]["minimumPositives"] == 30


def test_blocked_manifest_never_produces_a_model(
    training_factory: sessionmaker[Session],
) -> None:
    manifest_id = add_manifest(training_factory, version="blocked", status="BLOCKED")
    job_id = create_job(training_factory, manifest_id, "training-key-blocked")

    execute_training_job(training_factory, job_id)

    with training_factory() as session:
        row = session.get(MLTrainingJob, job_id)
        assert row is not None
        assert row.status == "INSUFFICIENT_DATA"
        assert row.result_json is None
        assert row.error_json["code"] == "MANIFEST_BLOCKED"


def test_idempotency_replays_same_job_and_rejects_different_body(
    training_factory: sessionmaker[Session],
) -> None:
    manifest_id = add_manifest(training_factory, version="idempotent")
    with training_factory.begin() as session:
        first, created = create_training_job(
            session,
            manifest_id=manifest_id,
            algorithm=ALGORITHM,
            seed=42,
            justification="Justification stable et auditée",
            author="karim.bennani",
            idempotency_key="same-key-0001",
            correlation_id="trace-one",
        )
        replay, replay_created = create_training_job(
            session,
            manifest_id=manifest_id,
            algorithm=ALGORITHM,
            seed=42,
            justification="Justification stable et auditée",
            author="karim.bennani",
            idempotency_key="same-key-0001",
            correlation_id="trace-two",
        )
        assert created and not replay_created
        assert replay.id == first.id
        with pytest.raises(Problem) as raised:
            create_training_job(
                session,
                manifest_id=manifest_id,
                algorithm=ALGORITHM,
                seed=43,
                justification="Justification stable et auditée",
                author="karim.bennani",
                idempotency_key="same-key-0001",
                correlation_id="trace-three",
            )
        assert raised.value.status_code == 409
        assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_one_active_job_per_manifest_and_cancellation_is_persisted(
    training_factory: sessionmaker[Session],
) -> None:
    manifest_id = add_manifest(training_factory, version="concurrency")
    job_id = create_job(training_factory, manifest_id, "training-key-active")
    with training_factory.begin() as session:
        with pytest.raises(Problem) as raised:
            create_training_job(
                session,
                manifest_id=manifest_id,
                algorithm=ALGORITHM,
                seed=7,
                justification="Deuxième tentative concurrente explicitement refusée",
                author="karim.bennani",
                idempotency_key="training-key-conflict",
                correlation_id="trace-conflict",
            )
        assert raised.value.status_code == 409
        assert raised.value.code == "TRAINING_IN_PROGRESS"
        row = request_cancellation(session, job_id, "karim.bennani", "trace-cancel")
        assert row.cancellation_requested is True

    execute_training_job(training_factory, job_id)
    with training_factory() as session:
        row = session.get(MLTrainingJob, job_id)
        assert row is not None
        assert row.status == "CANCELLED"
        assert session.scalar(
            select(MLGovernanceAuditLog).where(
                MLGovernanceAuditLog.action == "TRAINING_CANCELLATION_REQUESTED"
            )
        )
