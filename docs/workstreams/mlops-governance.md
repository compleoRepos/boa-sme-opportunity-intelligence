# MLOps governance domain

> **Statut courant : socle persistant intégré et validé.** Les objets purs décrits ici sont désormais reliés à PostgreSQL, au registre d’inférence et aux routes gouvernées. L’entraînement BOA réel reste non implémenté. Voir [`../finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

This workstream defines **pure, deterministic domain objects** for training lineage and model governance. It does not train a model, call an external registry, claim performance, or promote a model automatically.

## Temporal integrity and lineage

`FeatureLineage` records `featureTimestamp`, `observationAsOf`, source, and an optional source record. A feature is valid only when `featureTimestamp <= observationAsOf`; `validate_temporal_integrity` raises `FeatureContaminationError` and reports contamination rather than silently dropping a row. `TrainingLineage` binds examples, feature-set version, source snapshots, code revision, label definition, and training cutoff.

## Dataset policy

`TemporalSplit` assigns observations chronologically to `TRAIN`, `VALIDATION`, and `TEST`. Boundaries are explicit and a row after the configured test boundary is rejected. `LabelDefinition`, `LabelObservation`, and `assess_label_maturity` distinguish mature, immature, and missing labels; incomplete label maturity is not training-ready.

## Evaluation policy

`evaluate_metrics` exposes Precision@K, Recall@K, PR-AUC, calibration error, lift, and optional treatment/control uplift. A metric returns `N/A` when its inputs are absent, malformed, degenerate, or insufficient for that calculation. These calculations are descriptive utilities only: no result is a performance claim.

## Registry lifecycle

`ModelRegistry` enforces the lifecycle `REGISTERED -> VALIDATING -> SUBMITTED -> APPROVED -> CHAMPION -> RETIRED`. Promotion requires a recorded approval actor and is rejected for any other state. Replacing a champion retires the previous version; `rollback` can restore that retired previous champion. All objects are in-memory/pure domain state and require an adapter before persistence.
