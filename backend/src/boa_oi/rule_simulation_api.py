from __future__ import annotations

from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.models.entities import RuleSimulation
from boa_oi.platform import Principal, create_service_app, get_session, require_roles
from boa_oi.rules.schemas import SimulationRequest
from boa_oi.rules.service import find_rule, latest_version, serialize_rule, transition
from boa_oi.rules.simulation import simulate_persisted_history

app = create_service_app(
    "rule-simulation-service",
    "Historical Rule Studio simulation and impact analysis over persisted Analytics features.",
)
PREFIX = "/internal/v1/rules"
SIMULATION_ROLES = ("BUSINESS_ANALYST", "RULE_APPROVER", "ADMIN", "SERVICE", "DATA_ANALYST")


@app.post(f"{PREFIX}/{{rule_id}}/simulate", tags=["Simulation"])
def simulate(
    rule_id: str,
    payload: SimulationRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*SIMULATION_ROLES)),
) -> dict[str, Any]:
    rule = find_rule(session, rule_id, lock=True)
    version = latest_version(session, rule)
    simulation = simulate_persisted_history(
        session,
        rule,
        version,
        period_from=payload.period.from_,
        period_to=payload.period.to,
        population=payload.population,
        actor=principal.username or principal.subject,
    )
    session.flush()
    transition(session, rule_id, "simulate", principal.username or principal.subject)
    session.flush()
    return {
        "simulationId": str(simulation.id),
        "rule": serialize_rule(session, rule),
        **simulation.result_json,
    }


@app.get(f"{PREFIX}/{{rule_id}}/simulations", tags=["Simulation"])
def simulations(
    rule_id: str,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_roles(*SIMULATION_ROLES)),
) -> dict[str, Any]:
    rule = find_rule(session, rule_id)
    versions = {item.id: item.version for item in rule_versions(session, rule.id)}
    rows = list(
        session.scalars(
            select(RuleSimulation)
            .where(RuleSimulation.rule_version_id.in_(versions))
            .order_by(RuleSimulation.created_at.desc())
        )
    )
    return {
        "ruleId": rule.rule_id,
        "simulations": [
            {
                "simulationId": str(item.id),
                "ruleVersion": versions[item.rule_version_id],
                "period": {"from": item.period_from.isoformat(), "to": item.period_to.isoformat()},
                "population": item.population_json,
                "createdAt": item.created_at.isoformat(),
                "createdBy": item.created_by,
                **item.result_json,
            }
            for item in rows
        ],
    }


def rule_versions(session: Session, rule_id: Any) -> list[Any]:
    from boa_oi.models.entities import RuleVersion

    return list(session.scalars(select(RuleVersion).where(RuleVersion.rule_id == rule_id)))


__all__ = ["app"]
