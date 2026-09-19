from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

DEFAULT_CUSTOMERS = 50_000
DEFAULT_DATABASE = "boa_load_50k"
SEED = "boa-sme-oi-load-50k-v1"


class ScenarioSpec(TypedDict):
    name: str
    url: str
    headers: dict[str, str]
    concurrency: int
    requests: int
    p95_target_ms: float | None


def admin_url(database: str | None = None) -> URL:
    raw = os.getenv("LOAD_ADMIN_DATABASE_URL")
    if not raw:
        raise RuntimeError("LOAD_ADMIN_DATABASE_URL is required")
    url = make_url(raw)
    return url.set(database=database) if database else url


def recreate_database(database: str) -> None:
    engine = create_engine(admin_url("postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database AND pid <> pg_backend_pid()"
            ),
            {"database": database},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    engine.dispose()


def drop_database(database: str) -> None:
    engine = create_engine(admin_url("postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database AND pid <> pg_backend_pid()"
            ),
            {"database": database},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
    engine.dispose()


def migrate(database: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        admin_url(database).render_as_string(hide_password=False).replace("%", "%%")
    )
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        cwd="database",
        env=env,
        stdout=sys.stderr,
    )


def prepare_fixture(database: str, customers: int) -> dict[str, Any]:
    if customers < 1:
        raise ValueError("customers must be positive")
    recreate_database(database)
    migrate(database)
    engine = create_engine(admin_url(database), pool_pre_ping=True)
    started = time.perf_counter()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO customer.relationship_managers
                    (subject_id, display_name, branch_code, active, id, created_by)
                SELECT
                    'rm-load-' || lpad(i::text, 2, '0'),
                    'CC synthétique de charge ' || lpad(i::text, 2, '0'),
                    'BR-' || lpad((((i - 1) / 5) + 1)::text, 2, '0'),
                    true,
                    md5('load-rm-' || i::text)::uuid,
                    'load-test-50k'
                FROM generate_series(1, 25) AS source(i)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO customer.customers
                    (customer_ref, legal_name, sector_code, segment_code, scenario_code,
                     incorporated_on, status, rm_id, id, created_by)
                SELECT
                    'LOAD-' || lpad(i::text, 6, '0'),
                    'PME synthétique de charge ' || lpad(i::text, 6, '0'),
                    (ARRAY['INDUSTRIE','IMPORT_EXPORT','DISTRIBUTION','SERVICES',
                           'BTP','AGRICULTURE','COMMERCE','TECHNOLOGIE'])[((i - 1) % 8) + 1],
                    CASE WHEN i % 3 = 0 THEN 'MEDIUM' ELSE 'SMALL' END,
                    'LOAD_PROFILE_' || (((i - 1) % 8) + 1)::text,
                    make_date(2000 + (i % 20), 1 + (i % 12), 1 + (i % 27)),
                    'ACTIVE',
                    md5('load-rm-' || (((i - 1) % 25) + 1)::text)::uuid,
                    md5('load-customer-' || i::text)::uuid,
                    'load-test-50k'
                FROM generate_series(1, :customers) AS source(i)
                """
            ),
            {"customers": customers},
        )
        connection.execute(
            text(
                """
                INSERT INTO customer.portfolio_assignments
                    (id, customer_id, relationship_manager_id, branch_code, valid_from,
                     valid_to, actor, reason, portfolio_id, assignment_type, is_primary,
                     source_system, source_event_id, source_payload_hash, source_watermark)
                SELECT
                    md5('load-assignment-' || i::text)::uuid,
                    md5('load-customer-' || i::text)::uuid,
                    md5('load-rm-' || (((i - 1) % 25) + 1)::text)::uuid,
                    'BR-' || lpad(((((i - 1) % 25) / 5) + 1)::text, 2, '0'),
                    TIMESTAMPTZ '2025-01-01 00:00:00+00',
                    NULL,
                    'load-test-50k',
                    'Affectation synthétique de charge',
                    'LOAD-PORTFOLIO-' || lpad((((i - 1) % 25) + 1)::text, 2, '0'),
                    'PRIMARY',
                    true,
                    'LOAD_TEST',
                    'LOAD-EVENT-' || lpad(i::text, 6, '0'),
                    md5('load-payload-' || i::text),
                    'LOAD-WATERMARK-1'
                FROM generate_series(1, :customers) AS source(i)
                """
            ),
            {"customers": customers},
        )
        connection.execute(
            text(
                """
                INSERT INTO opportunity.opportunity_rules
                    (opportunity_type, version, configuration_json, active, id, created_by)
                VALUES
                    ('WORKING_CAPITAL', 'load-v1', '{}', true,
                     md5('load-rule')::uuid, 'load-test-50k')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO opportunity.opportunities
                    (opportunity_ref, customer_id, customer_ref, customer_name,
                     opportunity_type, status, horizon, confidence_score, confidence_level,
                     confidence_components_json, priority_score, priority_level,
                     priority_components_json, why_json, what_text, when_text,
                     recommended_products_json, explanation_json, generated_at,
                     engine_version, rule_version, rule_id, deduplication_key, id,
                     created_by, scoring_policy_id, scoring_policy_version, rules_weight,
                     ml_weight, fallback_mode, fallback_cause_json, expires_at)
                SELECT
                    'LOAD-OPP-' || lpad(i::text, 6, '0'),
                    md5('load-customer-' || i::text)::uuid,
                    'LOAD-' || lpad(i::text, 6, '0'),
                    'PME synthétique de charge ' || lpad(i::text, 6, '0'),
                    (ARRAY['WORKING_CAPITAL','TRADE_FINANCE','INVESTMENT_FINANCING',
                           'CASH_MANAGEMENT'])[((i - 1) % 4) + 1],
                    'OPEN',
                    'NEXT_90_DAYS',
                    (0.55 + ((i % 40)::numeric / 100)),
                    CASE WHEN i % 4 = 0 THEN 'HIGH' ELSE 'MEDIUM' END,
                    json_build_array(json_build_object('source', 'RULES_ONLY', 'weight', 1.0)),
                    (40 + (i % 60))::numeric,
                    CASE
                        WHEN i % 10 IN (0, 1) THEN 'P1'
                        WHEN i % 10 IN (2, 3, 4) THEN 'P2'
                        WHEN i % 10 IN (5, 6, 7) THEN 'P3'
                        ELSE 'P4'
                    END,
                    json_build_array(json_build_object('component', 'RULES', 'value', (i % 100))),
                    json_build_array('Signal synthétique de charge à examiner'),
                    'Examiner le besoin commercial avec le client PME.',
                    'Dans les 90 prochains jours.',
                    json_build_array(json_build_object(
                        'code', 'WORKING_CAPITAL_FACILITY',
                        'name', 'Facilité de fonds de roulement'
                    )),
                    json_build_object(
                        'mode', 'RULES_ONLY',
                        'disclaimer', 'Test de charge synthétique, aucune décision de crédit'
                    ),
                    TIMESTAMPTZ '2026-09-19 12:00:00+00' - ((i % 30) || ' days')::interval,
                    'load-test-rules-only',
                    'load-v1',
                    md5('load-rule')::uuid,
                    'load-dedup-' || i::text,
                    md5('load-opportunity-' || i::text)::uuid,
                    'load-test-50k',
                    'commercial-rules-only-load',
                    1,
                    1.0,
                    0.0,
                    'RULES_ONLY',
                    jsonb_build_object('code', 'LOAD_TEST_NO_ML'),
                    TIMESTAMPTZ '2026-12-31 23:59:59+00'
                FROM generate_series(1, :customers) AS source(i)
                """
            ),
            {"customers": customers},
        )
        for table_name in (
            "customer.relationship_managers",
            "customer.customers",
            "customer.portfolio_assignments",
            "opportunity.opportunity_rules",
            "opportunity.opportunities",
        ):
            connection.execute(text(f"ANALYZE {table_name}"))
    elapsed = time.perf_counter() - started
    with engine.connect() as connection:
        counts = {
            name: connection.scalar(text(f"SELECT count(*) FROM {table_name}"))
            for name, table_name in {
                "relationshipManagers": "customer.relationship_managers",
                "customers": "customer.customers",
                "portfolioAssignments": "customer.portfolio_assignments",
                "opportunityRules": "opportunity.opportunity_rules",
                "opportunities": "opportunity.opportunities",
            }.items()
        }
        size_bytes = connection.scalar(text("SELECT pg_database_size(current_database())"))
    engine.dispose()
    return {
        "seed": SEED,
        "durationSeconds": round(elapsed, 3),
        "counts": counts,
        "databaseSizeBytes": int(size_bytes or 0),
    }


def percentile(values: list[float], proportion: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, math.ceil(proportion * len(ordered)) - 1))
    return ordered[position]


async def wait_ready(client: httpx.AsyncClient, url: str, timeout_seconds: float = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"service not ready: {url}")


async def benchmark_scenario(
    client: httpx.AsyncClient,
    *,
    name: str,
    url: str,
    headers: dict[str, str],
    concurrency: int,
    requests: int,
    expected_status: int = 200,
    p95_target_ms: float | None = None,
    max_error_rate: float = 0.01,
) -> dict[str, Any]:
    for _ in range(min(5, requests)):
        warmup = await client.get(url, headers=headers)
        if warmup.status_code != expected_status:
            raise RuntimeError(
                f"warmup failed for {name}: {warmup.status_code} {warmup.text[:300]}"
            )
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    sizes: list[int] = []
    statuses: Counter[int] = Counter()

    async def one() -> None:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(url, headers=headers)
                statuses[response.status_code] += 1
                sizes.append(len(response.content))
            except httpx.HTTPError:
                statuses[0] += 1
            latencies.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(requests)))
    wall = time.perf_counter() - started
    errors = requests - statuses[expected_status]
    error_rate = errors / requests
    target_percentile = 0.99 if name.startswith("health-") else 0.95
    measured_target_percentile = percentile(latencies, target_percentile)
    threshold_pass = error_rate < max_error_rate
    if p95_target_ms is not None:
        threshold_pass = threshold_pass and measured_target_percentile < p95_target_ms
    return {
        "name": name,
        "url": url,
        "concurrency": concurrency,
        "requests": requests,
        "statusCounts": {str(key): value for key, value in sorted(statuses.items())},
        "errorRate": round(error_rate, 6),
        "throughputRequestsPerSecond": round(requests / wall, 3),
        "latencyMs": {
            "min": round(min(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
        "responseBytes": {
            "min": min(sizes) if sizes else 0,
            "median": int(percentile([float(value) for value in sizes], 0.50)) if sizes else 0,
            "max": max(sizes) if sizes else 0,
        },
        "target": {
            "latencyPercentile": f"p{round(target_percentile * 100)}",
            "latencyMs": p95_target_ms,
            "maxErrorRate": max_error_rate,
        },
        "status": "PASS" if threshold_pass else "FAIL",
    }


def principal_header(
    subject: str,
    roles: list[str],
    *,
    relationship_managers: list[str] | None = None,
    branches: list[str] | None = None,
) -> dict[str, str]:
    payload = {
        "subject": subject,
        "username": subject,
        "roles": roles,
        "relationshipManagerIds": relationship_managers or [],
        "branchIds": branches or [],
    }
    return {"X-Dev-Principal": json.dumps(payload, separators=(",", ":"))}


def summarize_plan(plan: list[dict[str, Any]]) -> dict[str, Any]:
    root = plan[0]["Plan"]
    node_types: Counter[str] = Counter()
    indexes: set[str] = set()

    def visit(node: dict[str, Any]) -> None:
        node_types[str(node.get("Node Type"))] += 1
        if node.get("Index Name"):
            indexes.add(str(node["Index Name"]))
        for child in node.get("Plans", []):
            visit(child)

    visit(root)
    return {
        "planningTimeMs": plan[0].get("Planning Time"),
        "executionTimeMs": plan[0].get("Execution Time"),
        "actualRows": root.get("Actual Rows"),
        "sharedHitBlocks": root.get("Shared Hit Blocks"),
        "sharedReadBlocks": root.get("Shared Read Blocks"),
        "nodeTypes": dict(node_types),
        "indexes": sorted(indexes),
    }


def database_evidence(database: str) -> dict[str, Any]:
    engine = create_engine(admin_url(database), pool_pre_ping=True)
    queries = {
        "opportunityPriorityPage": """
            SELECT id FROM opportunity.opportunities
            WHERE status = 'OPEN' AND priority_level = 'P1'
            ORDER BY priority_score DESC, id LIMIT 26
        """,
        "customerSearch": """
            SELECT c.id
            FROM customer.customers c
            JOIN customer.portfolio_assignments pa ON pa.customer_id = c.id
            JOIN customer.relationship_managers rm ON rm.id = pa.relationship_manager_id
            WHERE pa.valid_from <= now() AND pa.valid_to IS NULL
              AND (c.customer_ref ILIKE '%LOAD-0001%'
                   OR c.legal_name ILIKE '%LOAD-0001%'
                   OR c.sector_code ILIKE '%LOAD-0001%')
            ORDER BY c.customer_ref, c.id LIMIT 26
        """,
        "relationshipManagerScope": """
            SELECT c.id
            FROM customer.customers c
            JOIN customer.portfolio_assignments pa ON pa.customer_id = c.id
            JOIN customer.relationship_managers rm ON rm.id = pa.relationship_manager_id
            WHERE pa.valid_from <= now() AND pa.valid_to IS NULL
              AND rm.subject_id = 'rm-load-01'
        """,
    }
    plans: dict[str, Any] = {}
    with engine.connect() as connection:
        counts = {
            name: int(connection.scalar(text(f"SELECT count(*) FROM {table_name}")) or 0)
            for name, table_name in {
                "relationshipManagers": "customer.relationship_managers",
                "customers": "customer.customers",
                "portfolioAssignments": "customer.portfolio_assignments",
                "opportunities": "opportunity.opportunities",
            }.items()
        }
        for name, sql in queries.items():
            raw = connection.scalar(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"))
            plans[name] = summarize_plan(raw)
        db = (
            connection.execute(
                text(
                    """
                SELECT current_setting('server_version') AS version,
                       current_setting('shared_buffers') AS shared_buffers,
                       current_setting('max_connections') AS max_connections,
                       pg_database_size(current_database()) AS size_bytes
                """
                )
            )
            .mappings()
            .one()
        )
        stats = (
            connection.execute(
                text(
                    """
                SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
                       temp_files, temp_bytes, deadlocks
                FROM pg_stat_database WHERE datname = current_database()
                """
                )
            )
            .mappings()
            .one()
        )
    engine.dispose()
    return {
        "counts": counts,
        "configuration": dict(db),
        "statistics": dict(stats),
        "queryPlans": plans,
    }


def memory_limit_bytes() -> int | None:
    for candidate in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        path = Path(candidate)
        if path.exists():
            raw = path.read_text().strip()
            if raw != "max":
                return int(raw)
    return None


async def run_benchmarks(database: str, output: Path) -> dict[str, Any]:
    customer_url = os.getenv("LOAD_CUSTOMER_URL", "http://load-customer:8080")
    opportunity_url = os.getenv("LOAD_OPPORTUNITY_URL", "http://load-opportunity:8080")
    portfolio_url = os.getenv("LOAD_PORTFOLIO_URL", "http://load-portfolio:8080")
    timeout = httpx.Timeout(60.0)
    limits = httpx.Limits(max_connections=40, max_keepalive_connections=20)
    admin = principal_header("load-admin", ["ADMIN"])
    cc = principal_header(
        "rm-load-01",
        ["RELATIONSHIP_MANAGER"],
        relationship_managers=["rm-load-01"],
        branches=["BR-01"],
    )
    branch = principal_header(
        "branch-load-01",
        ["BRANCH_MANAGER"],
        branches=["BR-01"],
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        for base in (customer_url, opportunity_url, portfolio_url):
            await wait_ready(client, f"{base}/ready")
        specs: list[ScenarioSpec] = [
            {
                "name": "health-customer",
                "url": f"{customer_url}/health",
                "headers": {},
                "concurrency": 5,
                "requests": 50,
                "p95_target_ms": 500,
            },
            {
                "name": "health-opportunity",
                "url": f"{opportunity_url}/health",
                "headers": {},
                "concurrency": 5,
                "requests": 50,
                "p95_target_ms": 500,
            },
            {
                "name": "opportunities-admin-page-25",
                "url": (
                    f"{opportunity_url}/internal/v1/opportunities"
                    "?pageSize=25&status=OPEN&priorityLevel=P1"
                ),
                "headers": admin,
                "concurrency": 10,
                "requests": 200,
                "p95_target_ms": 1500,
            },
            {
                "name": "opportunities-cc-scoped-page-25",
                "url": f"{opportunity_url}/internal/v1/opportunities?pageSize=25&status=OPEN",
                "headers": cc,
                "concurrency": 10,
                "requests": 200,
                "p95_target_ms": 1500,
            },
            {
                "name": "customer-search-cc",
                "url": f"{customer_url}/internal/v1/customers?pageSize=25&q=LOAD-0001",
                "headers": cc,
                "concurrency": 10,
                "requests": 200,
                "p95_target_ms": 1500,
            },
            {
                "name": "customer-detail-cc",
                "url": f"{customer_url}/internal/v1/customers/LOAD-000001",
                "headers": cc,
                "concurrency": 5,
                "requests": 100,
                "p95_target_ms": 2000,
            },
            {
                "name": "opportunity-detail-cc",
                "url": f"{opportunity_url}/internal/v1/opportunities/LOAD-OPP-000001",
                "headers": cc,
                "concurrency": 5,
                "requests": 100,
                "p95_target_ms": 2000,
            },
            {
                "name": "opportunity-explanation-cc",
                "url": f"{opportunity_url}/internal/v1/opportunities/LOAD-OPP-000001/explanation",
                "headers": cc,
                "concurrency": 5,
                "requests": 100,
                "p95_target_ms": 2000,
            },
            {
                "name": "dashboard-cc-2000-customers",
                "url": f"{portfolio_url}/internal/v1/dashboards/me",
                "headers": cc,
                "concurrency": 2,
                "requests": 20,
                "p95_target_ms": None,
            },
            {
                "name": "dashboard-branch-10000-customers",
                "url": f"{portfolio_url}/internal/v1/dashboards/branch",
                "headers": branch,
                "concurrency": 1,
                "requests": 5,
                "p95_target_ms": None,
            },
        ]
        scenarios = [await benchmark_scenario(client, **spec) for spec in specs]
    evidence = database_evidence(database)
    counts = evidence.pop("counts")
    payload = {
        "schemaVersion": "1.1",
        "runId": f"load-50k-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitCommit": os.getenv("LOAD_GIT_COMMIT", "unknown"),
        "scope": {
            "customers": counts["customers"],
            "portfolioAssignments": counts["portfolioAssignments"],
            "opportunities": counts["opportunities"],
            "relationshipManagers": counts["relationshipManagers"],
            "branches": 5,
            "dataKind": "DETERMINISTIC_SYNTHETIC_LOAD_FIXTURE",
            "notMeasured": [
                "historical banking transactions for all 50,000 customers",
                "full analytics/rules/ML batch generation for 50,000 customers",
                "AWS infrastructure",
                "production capacity or production SLO certification",
            ],
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "runnerCpuCount": os.cpu_count(),
            "runnerMemoryLimitBytes": memory_limit_bytes(),
            "serviceLimits": {
                "customer": {"cpu": 0.35, "memoryBytes": 335_544_320},
                "opportunity": {"cpu": 0.75, "memoryBytes": 536_870_912},
                "portfolio": {"cpu": 0.35, "memoryBytes": 335_544_320},
                "postgres": {"cpu": 1.25, "memoryBytes": 1_468_006_400},
            },
        },
        "thresholdSource": "docs/test-plan.md section 14",
        "scenarios": scenarios,
        "database": evidence,
        "status": "PASS" if all(item["status"] == "PASS" for item in scenarios) else "FAIL",
        "disclaimer": (
            "Engineering load evidence on deterministic synthetic data. "
            "No ML production-performance claim and no credit decision are inferred."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproducible 50k SME load benchmark")
    parser.add_argument("command", choices=("prepare", "run", "cleanup"))
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--customers", type=int, default=DEFAULT_CUSTOMERS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/load/RESULTATS-CHARGE-50000.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        result = prepare_fixture(args.database, args.customers)
    elif args.command == "run":
        result = asyncio.run(run_benchmarks(args.database, args.output))
    else:
        drop_database(args.database)
        result = {"database": args.database, "dropped": True}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
