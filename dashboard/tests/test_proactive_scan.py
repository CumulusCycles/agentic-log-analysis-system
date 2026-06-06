"""Tests for the proactive background scan loop (PR 4c).

Coverage:
  - FindingsBuffer ring + recent() ordering + maxlen
  - _severity_for ladder (error > warn > info)
  - _run_one_scan: NO_ANOMALIES sentinel → None
  - _run_one_scan: real answer → Finding with derived severity + citations
  - _run_one_scan: vectorstore=None short-circuits
  - _run_one_scan: graph exception → None (loop survives)
  - run_proactive_scan_loop: dry-run skip path
  - run_proactive_scan_loop: writes last_scan_at + next_scan_at
  - run_proactive_scan_loop: appends findings on real iterations
  - run_proactive_scan_loop: clean CancelledError propagation
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from log_dashboard.agent.proactive import (
    PROACTIVE_JWT_SUB,
    FindingsBuffer,
    _new_finding_id,
    _run_one_scan,
    _severity_for,
    run_proactive_scan_loop,
)
from log_dashboard.agent.proactive_prompt import NO_ANOMALIES_SENTINEL
from log_dashboard.config import Settings
from log_dashboard.schemas import Citation, LogLevel, ProactiveFinding


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        jwt_secret="t",
        admin_username="a",
        admin_password="b",
        proactive_scan_interval_seconds=60,
        proactive_scan_lookback_minutes=30,
        proactive_scan_max_findings=5,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _citation(level: LogLevel, app: str = "fnol") -> Citation:
    return Citation(
        id=f"{app}:0000000000000000",
        timestamp=datetime(2026, 6, 6, tzinfo=UTC),
        level=level,
        app=app,
        event="request",
        raw="hello",
        score=0.5,
    )


class _StubSessionIndex:
    """Minimal stand-in for SessionIndex.touch — records the call."""

    def __init__(self) -> None:
        self.touches: list[str] = []

    async def touch(self, thread_id: str) -> None:
        self.touches.append(thread_id)


class _StubGraph:
    """Records the last (state, config) it was invoked with and returns a
    pre-baked result dict. Drives `_run_one_scan` deterministically."""

    def __init__(
        self,
        *,
        answer: str,
        citations: list[Any] | None = None,
        dry_run: bool = False,
        raises: BaseException | None = None,
    ) -> None:
        # Build a state dict shaped like the graph's real output: messages
        # ending in an AIMessage with `content=answer`, plus a citations
        # list shaped like CitedLogEntry (the extract helper reads attrs).
        from langchain_core.messages import AIMessage

        self._answer = answer
        self._citations = citations or []
        self._dry_run = dry_run
        self._raises = raises
        self.invoked: list[tuple[dict, dict]] = []
        self._ai_message = AIMessage(content=answer)

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        self.invoked.append((state, config or {}))
        if self._raises is not None:
            raise self._raises
        return {
            "messages": [*state["messages"], self._ai_message],
            "citations": self._citations,
            "dry_run": self._dry_run,
            "tool_budget_exhausted": False,
        }


class _CitedEntry(SimpleNamespace):
    """Tiny record class shaped like the agent's CitedLogEntry — what
    `extract_citations` reads off the state.

    Fields: id, timestamp (ISO str), level, app, event, raw, score.
    """


# ---------------- FindingsBuffer ----------------


def test_findings_buffer_recent_returns_newest_first() -> None:
    buf = FindingsBuffer()
    f1 = _make_finding(severity="info", finding_id="proactive:f1")
    f2 = _make_finding(severity="warn", finding_id="proactive:f2")
    f3 = _make_finding(severity="error", finding_id="proactive:f3")
    buf.append(f1)
    buf.append(f2)
    buf.append(f3)
    recent = buf.recent(2)
    assert [f.id for f in recent] == ["proactive:f3", "proactive:f2"]


def test_findings_buffer_recent_zero_returns_empty() -> None:
    buf = FindingsBuffer()
    buf.append(_make_finding())
    assert buf.recent(0) == []
    assert buf.recent(-3) == []


def test_findings_buffer_maxlen_bounds_growth() -> None:
    buf = FindingsBuffer(maxlen=3)
    for i in range(10):
        buf.append(_make_finding(finding_id=f"proactive:{i}"))
    assert len(buf) == 3
    recent = buf.recent(5)
    # Last three appended were 7, 8, 9. Newest first: 9, 8, 7.
    assert [f.id for f in recent] == ["proactive:9", "proactive:8", "proactive:7"]


# ---------------- _severity_for ----------------


def test_severity_for_any_error_wins() -> None:
    cits = [_citation(LogLevel.INFO), _citation(LogLevel.WARN), _citation(LogLevel.ERROR)]
    assert _severity_for(cits) == "error"


def test_severity_for_warn_when_no_error() -> None:
    cits = [_citation(LogLevel.INFO), _citation(LogLevel.WARN), _citation(LogLevel.INFO)]
    assert _severity_for(cits) == "warn"


def test_severity_for_info_when_only_info() -> None:
    assert _severity_for([_citation(LogLevel.INFO)]) == "info"


def test_severity_for_info_when_empty() -> None:
    # Defensive: an agent answer with no citations is "info" — not a server
    # event, just the model's narrative observation.
    assert _severity_for([]) == "info"


# ---------------- _run_one_scan ----------------


@pytest.mark.asyncio
async def test_run_one_scan_returns_none_when_vectorstore_unavailable() -> None:
    graph = _StubGraph(answer="should not run")
    session_index = _StubSessionIndex()
    settings = _settings()
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=None,
        settings=settings,
        session_index=session_index,  # type: ignore[arg-type]
    )
    assert result is None
    # Degraded mode short-circuits BEFORE the graph is touched.
    assert graph.invoked == []
    assert session_index.touches == []


@pytest.mark.asyncio
async def test_run_one_scan_returns_none_on_sentinel() -> None:
    graph = _StubGraph(answer=NO_ANOMALIES_SENTINEL)
    session_index = _StubSessionIndex()
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=object(),  # truthy placeholder
        settings=_settings(),
        session_index=session_index,  # type: ignore[arg-type]
    )
    assert result is None
    # Graph WAS invoked (we only short-circuit on the sentinel content).
    assert len(graph.invoked) == 1
    # The session_id must be tagged with the proactive jwt_sub.
    state, config = graph.invoked[0]
    assert state["jwt_sub"] == PROACTIVE_JWT_SUB
    assert config["metadata"]["proactive_scan"] is True


@pytest.mark.asyncio
async def test_run_one_scan_returns_none_on_sentinel_with_trailing_whitespace() -> None:
    """A trailing newline after the sentinel is benign — strip + startswith."""
    graph = _StubGraph(answer=f"  {NO_ANOMALIES_SENTINEL}\n")
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=object(),
        settings=_settings(),
        session_index=_StubSessionIndex(),  # type: ignore[arg-type]
    )
    assert result is None


@pytest.mark.asyncio
async def test_run_one_scan_returns_finding_on_real_answer() -> None:
    cited = _CitedEntry(
        id="fnol:abcdef0123456789",
        timestamp="2026-06-06T12:00:00+00:00",
        level=LogLevel.ERROR,
        app="fnol",
        event="chaos_honored",
        raw="status=500",
        score=0.8,
    )
    settings = _settings(proactive_scan_lookback_minutes=42, dashboard_llm_dry_run=False)
    graph = _StubGraph(answer="Found 3 ERROR chaos_honored events in fnol.", citations=[cited])
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=object(),
        settings=settings,
        session_index=_StubSessionIndex(),  # type: ignore[arg-type]
    )
    assert isinstance(result, ProactiveFinding)
    assert result.id.startswith("proactive:")
    assert result.severity == "error"
    assert len(result.citations) == 1
    assert result.citations[0].id == "fnol:abcdef0123456789"
    assert result.summary.startswith("Found 3 ERROR")
    assert result.dry_run is False
    # Started ≤ completed.
    assert result.scan_started_at <= result.scan_completed_at

    # Verify the graph was invoked with the LangSmith metadata the scan loop
    # promises: filterable in the LangSmith UI without conflating with admin
    # chat sessions, AND tagged with the configured lookback window so traces
    # are interpretable retroactively.
    assert len(graph.invoked) == 1
    _, config = graph.invoked[0]
    assert config["metadata"]["proactive_scan"] is True
    assert config["metadata"]["lookback_minutes"] == 42
    assert config["metadata"]["jwt_sub"] == PROACTIVE_JWT_SUB
    assert config["metadata"]["dry_run"] is False
    # Each scan mints its own session_id; thread_id wraps jwt_sub + session_id.
    assert config["configurable"]["thread_id"].startswith(f"{PROACTIVE_JWT_SUB}:")


@pytest.mark.asyncio
async def test_run_one_scan_sanitises_credential_in_agent_answer() -> None:
    """`extract_answer` runs `sanitize_log_raw` on the final AIMessage content.
    Verify a credential-shaped token in the agent's answer is redacted before
    it lands in `ProactiveFinding.summary` — defence-in-depth against an LLM
    that accidentally echoes a secret it received via tool output."""
    answer_with_secret = (
        "Found a leak in fnol logs: Authorization: Bearer abcdefghij1234567890 — investigate."
    )
    graph = _StubGraph(answer=answer_with_secret)
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=object(),
        settings=_settings(),
        session_index=_StubSessionIndex(),  # type: ignore[arg-type]
    )
    assert isinstance(result, ProactiveFinding)
    # The raw token MUST NOT appear in the surfaced summary. The exact redaction
    # marker comes from `credentials.sanitize_log_raw`; assert on absence of
    # the secret rather than presence of a specific replacement so the test
    # stays decoupled from the sanitiser's redaction format.
    assert "abcdefghij1234567890" not in result.summary
    assert "Bearer abcdefghij1234567890" not in result.summary


@pytest.mark.asyncio
async def test_run_one_scan_returns_none_on_graph_exception() -> None:
    """If the graph raises (network blip, malformed state, etc.), the scan
    swallows the exception and returns None so the loop keeps running."""

    class _Boom(Exception):
        pass

    graph = _StubGraph(answer="unused", raises=_Boom("the graph blew up"))
    result = await _run_one_scan(
        graph=graph,  # type: ignore[arg-type]
        vectorstore=object(),
        settings=_settings(),
        session_index=_StubSessionIndex(),  # type: ignore[arg-type]
    )
    assert result is None


# ---------------- run_proactive_scan_loop ----------------


@pytest.mark.asyncio
async def test_loop_skips_when_dry_run_enabled(monkeypatch) -> None:
    """DRY_RUN=true makes the loop wake, log skipped, and continue. The
    graph must NOT be invoked."""
    graph = _StubGraph(answer="never called")
    session_index = _StubSessionIndex()
    buffer = FindingsBuffer()
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_graph=graph,
            vectorstore=object(),
            session_index=session_index,
            findings_buffer=buffer,
        )
    )
    settings = _settings(
        proactive_scan_interval_seconds=60,
        dashboard_llm_dry_run=True,
    )

    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        # Yield to scheduler so the loop's CancelledError can fire.
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("log_dashboard.agent.proactive.asyncio.sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_proactive_scan_loop(app, settings)  # type: ignore[arg-type]

    # First iteration's sleep happened, dry-run branch fired, loop tried to
    # sleep again and we cancelled it. Graph never touched.
    assert graph.invoked == []
    assert buffer.last_scan_at is not None
    assert buffer.next_scan_at is not None
    assert sleeps == [60.0, 60.0]


@pytest.mark.asyncio
async def test_loop_appends_finding_on_real_iteration(monkeypatch) -> None:
    """DRY_RUN=false + real graph answer → finding lands in the buffer."""
    cited = _CitedEntry(
        id="fnol:0123456789abcdef",
        timestamp="2026-06-06T12:00:00+00:00",
        level=LogLevel.WARN,
        app="fnol",
        event="chaos_honored",
        raw="status=503",
        score=0.5,
    )
    graph = _StubGraph(answer="WARN cluster in fnol.", citations=[cited])
    session_index = _StubSessionIndex()
    buffer = FindingsBuffer()
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_graph=graph,
            vectorstore=object(),
            session_index=session_index,
            findings_buffer=buffer,
        )
    )
    settings = _settings(dashboard_llm_dry_run=False)

    iterations = 0

    async def _fake_sleep(seconds: float) -> None:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("log_dashboard.agent.proactive.asyncio.sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_proactive_scan_loop(app, settings)  # type: ignore[arg-type]

    assert len(buffer) == 1
    finding = buffer.recent(1)[0]
    assert finding.severity == "warn"
    assert buffer.last_scan_at is not None
    assert buffer.next_scan_at is not None
    # Graph saw the proactive jwt_sub.
    assert graph.invoked[0][0]["jwt_sub"] == PROACTIVE_JWT_SUB


@pytest.mark.asyncio
async def test_loop_survives_iteration_failure(monkeypatch) -> None:
    """A scan that raises must not stop the loop — it logs + continues."""

    class _Boom(Exception):
        pass

    graph = _StubGraph(answer="never used", raises=_Boom("oops"))
    session_index = _StubSessionIndex()
    buffer = FindingsBuffer()
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_graph=graph,
            vectorstore=object(),
            session_index=session_index,
            findings_buffer=buffer,
        )
    )
    settings = _settings(dashboard_llm_dry_run=False)

    iterations = 0

    async def _fake_sleep(seconds: float) -> None:
        nonlocal iterations
        iterations += 1
        # Let the loop run 3 iterations to confirm survival across multiple
        # failures, then cancel.
        if iterations >= 4:
            raise asyncio.CancelledError

    monkeypatch.setattr("log_dashboard.agent.proactive.asyncio.sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_proactive_scan_loop(app, settings)  # type: ignore[arg-type]

    # Three iterations attempted, all failed, buffer stays empty, loop
    # never crashed.
    assert len(graph.invoked) == 3
    assert len(buffer) == 0


@pytest.mark.asyncio
async def test_loop_skips_when_agent_state_unavailable(monkeypatch) -> None:
    """If lifespan ordering ever leaves `agent_graph` unset by the time the
    task fires, the loop logs and keeps going rather than NPE'ing."""
    buffer = FindingsBuffer()
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_graph=None,
            vectorstore=object(),
            session_index=None,
            findings_buffer=buffer,
        )
    )
    settings = _settings(dashboard_llm_dry_run=False)

    iterations = 0

    async def _fake_sleep(seconds: float) -> None:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("log_dashboard.agent.proactive.asyncio.sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_proactive_scan_loop(app, settings)  # type: ignore[arg-type]

    assert len(buffer) == 0
    assert buffer.last_scan_at is not None


def test_new_finding_id_uniqueness() -> None:
    """Two consecutive calls produce distinct IDs (uuid4 collision is
    astronomically unlikely)."""
    a = _new_finding_id()
    b = _new_finding_id()
    assert a != b
    assert a.startswith("proactive:") and b.startswith("proactive:")


# ---------------- helpers ----------------


def _make_finding(
    *,
    severity: str = "info",
    finding_id: str = "proactive:test",
) -> ProactiveFinding:
    now = datetime(2026, 6, 6, tzinfo=UTC)
    return ProactiveFinding(
        id=finding_id,
        scan_started_at=now,
        scan_completed_at=now,
        summary="hello",
        severity=severity,  # type: ignore[arg-type]
        citations=[],
        dry_run=False,
    )
