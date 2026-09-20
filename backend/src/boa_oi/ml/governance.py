from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

POC_SHADOW = "POC_SHADOW"
RANKING_ONLY = "RANKING_ONLY"
BOA_HISTORICAL_OBSERVED = "BOA_HISTORICAL_OBSERVED"
LOCAL_COMMERCIAL_OUTCOME = "LOCAL_COMMERCIAL_OUTCOME"
SYNTHETIC = "SYNTHETIC"


def canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def dataset_manifest_blockers(
    *,
    source_kind: str,
    feature_snapshot_ids: Sequence[str],
    labels: Sequence[Mapping[str, Any]],
    training_cutoff: str,
) -> list[str]:
    blockers: list[str] = []
    if source_kind != BOA_HISTORICAL_OBSERVED:
        blockers.append("BOA_HISTORICAL_LABELS_UNAVAILABLE")
    if not feature_snapshot_ids:
        blockers.append("FEATURE_SNAPSHOTS_MISSING")
    if not labels:
        blockers.append("LABEL_SNAPSHOTS_MISSING")
    for label in labels:
        if label.get("sourceKind") != BOA_HISTORICAL_OBSERVED:
            blockers.append("LABEL_SOURCE_NOT_BOA_HISTORICAL")
        if label.get("candidateOnly", True):
            blockers.append("CANDIDATE_LABEL_NOT_APPROVED")
        if not label.get("windowClosed", False):
            blockers.append("LABEL_WINDOW_NOT_CLOSED")
        if label.get("outcomeValue") not in (True, False):
            blockers.append("BINARY_LABEL_MISSING")
        if label.get("featureSnapshotId") not in feature_snapshot_ids:
            blockers.append("FEATURE_LABEL_LINK_MISSING")
        available = str(label.get("labelAvailableFrom") or "")
        if available and available <= training_cutoff:
            blockers.append("LABEL_AVAILABLE_BEFORE_OR_AT_CUTOFF")
    return list(dict.fromkeys(blockers))


def evaluation_blockers(
    *,
    source_kind: str,
    metrics: Mapping[str, Any],
    calibration: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if source_kind != BOA_HISTORICAL_OBSERVED:
        blockers.append("BOA_HISTORICAL_LABELS_UNAVAILABLE")
    if not acceptance_criteria:
        blockers.append("BOA_ACCEPTANCE_CRITERIA_NOT_APPROVED")
    if not metrics or any(value == "N/A" for value in metrics.values()):
        blockers.append("EVALUATION_METRICS_NOT_EXPLOITABLE")
    if calibration.get("status") != "VALIDATED":
        blockers.append("CALIBRATION_NOT_VALIDATED")
    if calibration.get("brierScore") in (None, "N/A"):
        blockers.append("BRIER_SCORE_MISSING")
    if calibration.get("expectedCalibrationError") in (None, "N/A"):
        blockers.append("ECE_MISSING")
    return list(dict.fromkeys(blockers))


def activation_blockers(
    *,
    deployment_mode: str,
    source_kind: str,
    dataset_manifest_hash: str | None,
    artifact_checksum: str | None,
    lineage_examples: Sequence[Any],
    metrics: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if deployment_mode != POC_SHADOW:
        blockers.append("DEPLOYMENT_MODE_NOT_SHADOW")
    if source_kind != BOA_HISTORICAL_OBSERVED:
        blockers.append("BOA_HISTORICAL_LABELS_UNAVAILABLE")
    if not dataset_manifest_hash or len(dataset_manifest_hash) != 64:
        blockers.append("DATASET_MANIFEST_HASH_MISSING")
    if not artifact_checksum or len(artifact_checksum) != 64:
        blockers.append("MODEL_ARTIFACT_CHECKSUM_MISSING")
    if not lineage_examples:
        blockers.append("POINT_IN_TIME_EXAMPLES_MISSING")
    if not metrics or any(value == "N/A" for value in metrics.values()):
        blockers.append("EVALUATION_NOT_VALIDATED")
    if metrics.get("calibrationStatus") != "VALIDATED":
        blockers.append("CALIBRATION_NOT_VALIDATED")
    for key, blocker in (
        ("brierScore", "BRIER_SCORE_NOT_VALIDATED"),
        ("expectedCalibrationError", "ECE_NOT_VALIDATED"),
    ):
        value = metrics.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
        ):
            blockers.append(blocker)
    return list(dict.fromkeys(blockers))


__all__ = [
    "BOA_HISTORICAL_OBSERVED",
    "LOCAL_COMMERCIAL_OUTCOME",
    "POC_SHADOW",
    "RANKING_ONLY",
    "SYNTHETIC",
    "activation_blockers",
    "canonical_digest",
    "dataset_manifest_blockers",
    "evaluation_blockers",
]
