from __future__ import annotations

from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import LabelCatalogEntry, LabelCatalogVersion
from boa_oi.platform import Principal, current_principal
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def principal(role: str) -> Principal:
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=("rm-01",),
        branch_ids=("BR-01",),
        customer_scopes=("assigned",),
    )


@pytest.fixture()
def label_context(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'config'")
        cast(Table, LabelCatalogEntry.__mapper__.local_table).create(connection)
        cast(Table, LabelCatalogVersion.__mapper__.local_table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    entry_id = deterministic_uuid("label", "STATUS", "OPEN")
    with factory.begin() as session:
        session.add(
            LabelCatalogEntry(
                id=entry_id,
                namespace="STATUS",
                code="OPEN",
                locale="fr-FR",
                label="Ouvert",
                current_version=1,
                active=True,
                updated_by="seed",
                justification="Version initiale du test",
            )
        )
        session.add(
            LabelCatalogVersion(
                id=deterministic_uuid("label-version", "STATUS", "OPEN", "1"),
                catalog_entry_id=entry_id,
                version=1,
                label="Ouvert",
                active=True,
                created_by="seed",
                justification="Version initiale du test",
            )
        )
    app = application_for("rule-management-service")
    app.state.session_factory = factory
    yield app, factory
    app.dependency_overrides.clear()


def test_commercial_role_reads_active_label_catalog(label_context) -> None:
    app, _factory = label_context
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")

    response = TestClient(app).get("/internal/v1/labels")

    assert response.status_code == 200
    assert response.json()["labels"] == {"OPEN": "Ouvert"}
    assert response.json()["data"][0]["version"] == 1


def test_admin_update_creates_immutable_version_and_noop_is_idempotent(label_context) -> None:
    app, factory = label_context
    app.dependency_overrides[current_principal] = lambda: principal("ADMIN")
    client = TestClient(app)
    payload = {
        "label": "À traiter",
        "active": True,
        "expectedVersion": 1,
        "justification": "Terminologie validée par le métier",
    }

    updated = client.put("/internal/v1/labels/STATUS/OPEN", json=payload)
    replay = client.put(
        "/internal/v1/labels/STATUS/OPEN",
        json={**payload, "expectedVersion": 2},
    )
    history = client.get("/internal/v1/labels/STATUS/OPEN/versions")

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert replay.status_code == 200
    assert replay.json()["version"] == 2
    assert [item["version"] for item in history.json()["data"]] == [2, 1]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(LabelCatalogVersion)) == 2


def test_commercial_role_cannot_modify_labels(label_context) -> None:
    app, _factory = label_context
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")

    response = TestClient(app).put(
        "/internal/v1/labels/STATUS/OPEN",
        json={
            "label": "Texte interdit",
            "active": True,
            "expectedVersion": 1,
            "justification": "Tentative non autorisée",
        },
    )

    assert response.status_code == 403


def test_label_update_rejects_blank_text_and_short_reason(label_context) -> None:
    app, _factory = label_context
    app.dependency_overrides[current_principal] = lambda: principal("ADMIN")

    response = TestClient(app).put(
        "/internal/v1/labels/STATUS/OPEN",
        json={
            "label": "   ",
            "active": True,
            "expectedVersion": 1,
            "justification": "court",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_stale_admin_update_is_rejected_without_lost_update(label_context) -> None:
    app, _factory = label_context
    app.dependency_overrides[current_principal] = lambda: principal("ADMIN")
    client = TestClient(app)
    first = client.put(
        "/internal/v1/labels/STATUS/OPEN",
        json={
            "label": "Premier texte",
            "active": True,
            "expectedVersion": 1,
            "justification": "Première modification concurrente",
        },
    )
    stale = client.put(
        "/internal/v1/labels/STATUS/OPEN",
        json={
            "label": "Second texte",
            "active": True,
            "expectedVersion": 1,
            "justification": "Seconde modification devenue obsolète",
        },
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "LABEL_VERSION_CONFLICT"
    current = client.get("/internal/v1/labels").json()["labels"]
    assert current["OPEN"] == "Premier texte"
