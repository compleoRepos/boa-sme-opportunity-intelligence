# Operations readiness domain

> **Statut courant : monitoring persistant et readiness intégrés.** Les adaptateurs PostgreSQL, l’API interne et les contrôles E2E sont en place ; l’alerting externe et l’homologation production restent non implémentés. Voir [`../finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

This workstream defines pure, deterministic monitoring and readiness objects. It does not persist metrics, emit alerts, promote models, or perform automatic retraining; adapters can persist the immutable snapshots and structured audit events.

## Monitoring domains

`DriftMonitor` records observations for **DATA**, **FEATURE**, and **PREDICTION** drift. Each observation carries its metric, method, reference version, population/segment, sample size, timestamp, and configurable `WARNING`/`CRITICAL` thresholds. A `CRITICAL` observation is blocking and can be used by the serving layer to select the configured `RULES_ONLY` fallback. Thresholds do not imply a performance claim: the method and reference population remain explicit evidence.

`OperationalMonitor` records latency, errors, request volume, and the **RULES_ONLY rate**. Error and fallback rates are calculated from explicit counts, with a zero-denominator result of `0.0`; invalid counts are rejected. Latency and error/fallback rates use upper-bound thresholds. Volume uses `LowerBoundThresholds`, where a value below the critical bound is critical and a value below the warning bound is warning. `MonitoringHistory` provides a bounded, append-oriented in-memory history suitable for an adapter-backed store.

## Structured audit and observability

`AuditEvent` is a structured event with event type, subject, status, payload, timestamp, and optional trace identifier. `ObservabilityEvent` defines the required end-to-end fields:

| Field | Meaning |
|---|---|
| `traceId` | Correlation identifier for one request or scoring flow |
| `service` | Emitting service name |
| `endpoint` | Route or operation name |
| `status` | HTTP or domain status |
| `latency` | Measured elapsed time |
| `modelVersion` | Model identifier when ML is involved |
| `scoringPolicyVersion` | Policy/fusion version |
| `fallbackMode` | Explicit mode, including `RULES_ONLY` when used |

The contract serializes in API-friendly camelCase and can be reconstructed without losing the timestamp.

## Readiness gate

`ReadinessAggregator` evaluates explicit evidence for contracts, historical data, model validation, feature lineage, drift monitoring, operational monitoring, rules-only fallback, structured audit, observability, rollback, and approval. Missing evidence is always a failure; it is never inferred from a requested status. Therefore `READY_FOR_PRODUCTION` is impossible while any required prerequisite is absent or failed. `production_readiness` is the safe convenience entry point, while `READY_FOR_SHADOW` can be requested only after the same explicit component evaluation.

The domain is intentionally pure. Persistence, alert delivery, access control, retention, and runtime fallback selection remain integration responsibilities and should consume the serialized snapshots and audit payloads rather than recomputing them.
