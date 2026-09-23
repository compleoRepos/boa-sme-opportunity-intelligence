from __future__ import annotations

from typing import Any

from scripts.run_pipeline_benchmark import PipelineConfig, execute_pipeline


def test_pipeline_benchmark_records_every_stage_and_batch() -> None:
    calls: list[tuple[str, dict[str, Any], str]] = []

    def fake_post(url: str, payload: dict[str, Any], key: str) -> tuple[int, float]:
        calls.append((url, payload, key))
        return 202, 10.0

    result = execute_pipeline(
        PipelineConfig(
            customer_count=125,
            batch_size=50,
            as_of="2026-09-30",
            run_id="unit-run",
            analytics_url="http://analytics",
            signal_url="http://signals",
            opportunity_url="http://opportunities",
            feature_store_url="http://features",
            ml_engine_url="http://ml",
            source="UNIT_TEST",
            source_revision="abc123",
            source_branch="test",
            code_digest="digest",
            code_tree="CLEAN",
        ),
        post=fake_post,
    )

    assert result["status"] == "PASS"
    assert result["source"] == {
        "runtime": "UNIT_TEST",
        "revision": "abc123",
        "branch": "test",
        "codeDigest": "digest",
        "codeTree": "CLEAN",
    }
    assert result["batchCount"] == 3
    assert result["averageBatchDurationMs"] > 0
    assert result["throughputCustomersPerSecond"] > 0
    assert [(batch["start"], batch["end"]) for batch in result["batches"]] == [
        (1, 50),
        (51, 100),
        (101, 125),
    ]
    assert len(calls) == 15
    assert result["stages"]["analytics"] == {
        "totalDurationMs": 30.0,
        "averageBatchDurationMs": 10.0,
        "p95BatchDurationMs": 10.0,
        "batchCount": 3,
    }
    assert calls[0][1]["customerIds"][0] == "SME-00001"
    assert calls[-1][1]["customerIds"][-1] == "SME-00125"
