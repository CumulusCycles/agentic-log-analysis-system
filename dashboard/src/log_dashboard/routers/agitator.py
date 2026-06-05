"""Agitator routes — operator-driven scenario runs.

Five endpoints, all admin-JWT protected:

- GET    /api/agitator/scenarios       — list available scenarios for the UI
- GET    /api/agitator/env              — report ENABLE_CHAOS so the UI gates cards
- POST   /api/agitator/runs             — start a new scenario run
- GET    /api/agitator/runs             — list the most recent 50 runs
- GET    /api/agitator/runs/{run_id}    — poll one run's progress
- POST   /api/agitator/runs/{run_id}/cancel — cancel an in-flight run

The router is the only place that schedules `asyncio.create_task(scenario.run())`
and finalises the registry record on completion / cancellation / failure.
Scenarios themselves never touch the registry's lifecycle methods (`add`,
`finalize`) — only counter updates (`mark_sent`, `mark_failure`).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..agitator.auth import AgitatorAuthError, bootstrap_session
from ..agitator.runs import (
    ConcurrentRunCapError,
    RegistryFullError,
    RunRecord,
    RunRegistry,
    ScenarioAlreadyRunningError,
)
from ..agitator.scenarios import SCENARIOS
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..logging_setup import get_logger
from ..schemas import (
    AgitatorEnvOut,
    RunCreateRequest,
    RunListResponse,
    RunRecordOut,
    ScenarioParamOut,
    ScenarioSpecOut,
)

router = APIRouter(tags=["agitator"])
log = get_logger("agitator")


def _get_registry(request: Request) -> RunRegistry:
    registry: RunRegistry | None = getattr(request.app.state, "agitator_runs", None)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agitator not initialised",
        )
    return registry


def _record_to_out(record: RunRecord) -> RunRecordOut:
    return RunRecordOut(
        run_id=record.run_id,
        scenario=record.scenario_name,
        params=record.params,
        state=record.state,
        started_at=record.started_at,
        ended_at=record.ended_at,
        sent=record.sent,
        succeeded=record.succeeded,
        failed=record.failed,
        last_status_code=record.last_status_code,
        last_error=record.last_error,
    )


@router.get("/scenarios", response_model=list[ScenarioSpecOut])
async def list_scenarios(
    _: dict[str, Any] = Depends(get_current_admin),
) -> list[ScenarioSpecOut]:
    return [
        ScenarioSpecOut(
            name=cls.spec.name,
            display_name=cls.spec.display_name,
            description=cls.spec.description,
            target_app=cls.spec.target_app,
            requires_chaos=cls.spec.requires_chaos,
            params=[
                ScenarioParamOut(
                    name=p.name, minimum=p.minimum, maximum=p.maximum, default=p.default
                )
                for p in cls.spec.params
            ],
        )
        for cls in SCENARIOS.values()
    ]


@router.get("/env", response_model=AgitatorEnvOut)
async def get_env(
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> AgitatorEnvOut:
    return AgitatorEnvOut(enable_chaos=settings.enable_chaos)


@router.post("/runs", response_model=RunRecordOut, status_code=status.HTTP_201_CREATED)
async def start_run(
    body: RunCreateRequest,
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> RunRecordOut:
    scenario_cls = SCENARIOS.get(body.scenario)
    if scenario_cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown scenario: {body.scenario}",
        )

    if scenario_cls.spec.requires_chaos and not settings.enable_chaos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.scenario} requires ENABLE_CHAOS=true",
        )

    # Coerce + bound params against the spec.
    coerced: dict[str, int] = {}
    spec_params_by_name = {p.name: p for p in scenario_cls.spec.params}
    for name, value in body.params.items():
        spec = spec_params_by_name.get(name)
        if spec is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown param: {name}",
            )
        if not isinstance(value, int) or not (spec.minimum <= value <= spec.maximum):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"param {name} must be int in [{spec.minimum}, {spec.maximum}]",
            )
        coerced[name] = value
    # Fill defaults for any params the operator didn't override.
    for p in scenario_cls.spec.params:
        coerced.setdefault(p.name, p.default)

    registry = _get_registry(request)

    # Single login burst at run start. AgitatorAuthError → 502. Bootstrap
    # BEFORE try_start so we don't insert a registry record we can't fulfil.
    try:
        session = await bootstrap_session(settings)
    except AgitatorAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    run_id = str(uuid.uuid4())
    record = RunRecord(
        run_id=run_id,
        scenario_name=body.scenario,
        params=coerced,
        started_at=datetime.now(tz=UTC),
    )

    scenario = scenario_cls(
        settings=settings,
        session=session,
        registry=registry,
        run_id=run_id,
        params=coerced,
    )

    async def _wrapped() -> None:
        try:
            await scenario.run()
        except asyncio.CancelledError:
            await registry.finalize(run_id, "cancelled")
            log.info(
                "agitator_run_complete",
                run_id=run_id,
                scenario=body.scenario,
                state="cancelled",
            )
            raise
        except Exception as exc:  # noqa: BLE001 — must surface scenario failures
            await registry.finalize(run_id, "failed", error=str(exc))
            log.warning(
                "agitator_run_complete",
                run_id=run_id,
                scenario=body.scenario,
                state="failed",
                error_class=type(exc).__name__,
            )
            return
        await registry.finalize(run_id, "succeeded")
        log.info(
            "agitator_run_complete",
            run_id=run_id,
            scenario=body.scenario,
            state="succeeded",
        )

    # try_start atomically: cap check + same-scenario check + eviction +
    # add + task creation + task assignment. All four sequencing bugs from
    # the PR #35 review (TOCTOU on cap, TOCTOU on same-scenario, eviction
    # dangling reference, task-assignment gap) collapse into this one call.
    try:
        await registry.try_start(
            record,
            max_concurrent=settings.agitator_max_concurrent_runs,
            task_factory=lambda: asyncio.create_task(_wrapped()),
        )
    except ConcurrentRunCapError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{exc}; wait or cancel",
        ) from exc
    except ScenarioAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RegistryFullError as exc:
        # Defensive — concurrent cap should make this unreachable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="registry full of running records",
        ) from exc

    log.info(
        "agitator_run_started",
        run_id=run_id,
        scenario=body.scenario,
        params=coerced,
    )
    return _record_to_out(record)


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
) -> RunListResponse:
    registry = _get_registry(request)
    records = await registry.list_recent()
    return RunListResponse(runs=[_record_to_out(r) for r in records])


@router.get("/runs/{run_id}", response_model=RunRecordOut)
async def get_run(
    run_id: str,
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
) -> RunRecordOut:
    registry = _get_registry(request)
    record = await registry.get(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown run: {run_id}",
        )
    return _record_to_out(record)


@router.post("/runs/{run_id}/cancel", response_model=RunRecordOut)
async def cancel_run(
    run_id: str,
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
) -> RunRecordOut:
    registry = _get_registry(request)
    record = await registry.cancel(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown run: {run_id}",
        )
    return _record_to_out(record)
