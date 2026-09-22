from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PostResult = tuple[int, float]
PostFunction = Callable[[str, dict[str, Any], str], PostResult]


@dataclass(frozen=True)
class PipelineConfig:
    customer_count: int
    batch_size: int
    as_of: str
    run_id: str
    analytics_url: str
    signal_url: str
    opportunity_url: str
    feature_store_url: str
    ml_engine_url: str
    source: str
    source_revision: str
    source_branch: str
    code_digest: str
    code_tree: str


def _customer_ids(start: int, end: int) -> list[str]:
    return [f"SME-{index:05d}" for index in range(start, end + 1)]


def _post_json(url: str, payload: dict[str, Any], key: str) -> PostResult:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Correlation-ID": f"pipeline-{key}",
            "Idempotency-Key": f"pipeline-{key}",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=900) as response:
            response.read()
            status = response.status
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"POST {url} returned HTTP {error.code}: {detail}") from error
    duration_ms = round((time.monotonic() - started) * 1000, 3)
    if status not in (200, 201, 202):
        raise RuntimeError(f"POST {url} returned unexpected HTTP {status}")
    return status, duration_ms


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def execute_pipeline(config: PipelineConfig, post: PostFunction | None = None) -> dict[str, Any]:
    post = post or _post_json
    started = time.monotonic()
    batches: list[dict[str, Any]] = []
    stage_durations: dict[str, list[float]] = {
        "analytics": [],
        "signals": [],
        "opportunities": [],
        "featureStore": [],
        "ml": [],
    }
    stage_definitions: tuple[tuple[str, str, str, Callable[[list[str]], dict[str, Any]]], ...] = (
        (
            "analytics",
            config.analytics_url.rstrip("/") + "/internal/v1/analytics/recompute",
            "analytics",
            lambda ids: {
                "customerIds": ids,
                "asOf": config.as_of,
                "periods": ["7D", "30D", "90D", "180D", "365D"],
            },
        ),
        (
            "signals",
            config.signal_url.rstrip("/") + "/internal/v1/signals/evaluate",
            "signals",
            lambda ids: {"customerIds": ids, "asOf": config.as_of, "periods": ["90D"]},
        ),
        (
            "opportunities",
            config.opportunity_url.rstrip("/") + "/internal/v1/opportunities/generate",
            "opportunities",
            lambda ids: {"customerIds": ids, "asOf": config.as_of},
        ),
        (
            "featureStore",
            config.feature_store_url.rstrip("/") + "/internal/v1/features/materialize",
            "features",
            lambda ids: {"customerIds": ids, "asOf": config.as_of},
        ),
        (
            "ml",
            config.ml_engine_url.rstrip("/") + "/internal/v1/ml/scores/batch",
            "ml",
            lambda ids: {"customerIds": ids, "asOf": config.as_of},
        ),
    )

    for start in range(1, config.customer_count + 1, config.batch_size):
        end = min(start + config.batch_size - 1, config.customer_count)
        ids = _customer_ids(start, end)
        stage_results: dict[str, dict[str, Any]] = {}
        for stage, url, key_suffix, payload_factory in stage_definitions:
            status, duration_ms = post(
                url,
                payload_factory(ids),
                f"{config.run_id}-{key_suffix}-{start}",
            )
            stage_durations[stage].append(duration_ms)
            stage_results[stage] = {"httpStatus": status, "durationMs": duration_ms}
            print(
                f"batch={start:05d}-{end:05d} stage={stage} "
                f"status={status} durationMs={duration_ms}",
                flush=True,
            )
        batches.append({"start": start, "end": end, "stages": stage_results})

    total_duration_ms = round((time.monotonic() - started) * 1000, 3)
    return {
        "schemaVersion": "1.0",
        "runId": config.run_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "source": {
            "runtime": config.source,
            "revision": config.source_revision,
            "branch": config.source_branch,
            "codeDigest": config.code_digest,
            "codeTree": config.code_tree,
        },
        "asOfDate": config.as_of,
        "customerCount": config.customer_count,
        "batchSize": config.batch_size,
        "batchCount": len(batches),
        "totalDurationMs": total_duration_ms,
        "averageBatchDurationMs": round(total_duration_ms / max(1, len(batches)), 3),
        "throughputCustomersPerSecond": round(
            config.customer_count / max(0.001, total_duration_ms / 1000), 3
        ),
        "target": {
            "name": "500 PME en moins de 30 minutes",
            "maximumDurationMs": 1_800_000,
            "status": "HYPOTHÈSE À VALIDER AVEC BOA",
            "metInThisSyntheticRun": total_duration_ms <= 1_800_000,
        },
        "stages": {
            stage: {
                "totalDurationMs": round(sum(values), 3),
                "averageBatchDurationMs": round(sum(values) / len(values), 3),
                "p95BatchDurationMs": _percentile(values, 0.95),
                "batchCount": len(values),
            }
            for stage, values in stage_durations.items()
        },
        "batches": batches,
        "limitations": [
            "Données synthétiques uniquement; aucune donnée BOA réelle.",
            "Mesure mono-instance locale, séquentielle et non représentative "
            "d'une capacité de production.",
            "Aucune décision de crédit; le ML reste POC_SHADOW et sans poids opérationnel.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and measure the synthetic SME pipeline.")
    parser.add_argument("--customer-count", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--as-of", default="2026-09-30")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--analytics-url", default="http://127.0.0.1:9006")
    parser.add_argument("--signal-url", default="http://127.0.0.1:9007")
    parser.add_argument("--opportunity-url", default="http://127.0.0.1:9008")
    parser.add_argument("--feature-store-url", default="http://127.0.0.1:9014")
    parser.add_argument("--ml-engine-url", default="http://127.0.0.1:9015")
    parser.add_argument("--source", default="LOCAL_NATIVE_NO_DOCKER")
    parser.add_argument("--source-revision", default="UNKNOWN")
    parser.add_argument("--source-branch", default="UNKNOWN")
    parser.add_argument("--code-digest", default="UNKNOWN")
    parser.add_argument("--code-tree", choices=("CLEAN", "DIRTY"), default="DIRTY")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.customer_count < 1 or args.batch_size < 1:
        parser.error("customer-count and batch-size must be positive")

    result = execute_pipeline(
        PipelineConfig(
            customer_count=args.customer_count,
            batch_size=args.batch_size,
            as_of=args.as_of,
            run_id=args.run_id,
            analytics_url=args.analytics_url,
            signal_url=args.signal_url,
            opportunity_url=args.opportunity_url,
            feature_store_url=args.feature_store_url,
            ml_engine_url=args.ml_engine_url,
            source=args.source,
            source_revision=args.source_revision,
            source_branch=args.source_branch,
            code_digest=args.code_digest,
            code_tree=args.code_tree,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Pipeline terminé: customers={args.customer_count} batches={result['batchCount']} "
        f"durationMs={result['totalDurationMs']} evidence={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
