"""Regression guard for the LLM factory's timeout plumbing.

PR #59 burned ~3 round-trips because `ChatOllama(timeout=N)` is silently
absorbed by pydantic `extra="allow"` — the kwarg never reaches httpx and
every cold-start chat call false-fails on the default httpx 5-second
read timeout. The supported path is `client_kwargs={"timeout": N}`,
which langchain-ollama forwards into both sync and async client
constructors.

This test exists so the NEXT silent-absorption gotcha surfaces as a
failing test rather than a 502 in production. If a refactor drops
`client_kwargs`, renames it, or stops forwarding `settings.llm_timeout_seconds`
into it, the assertion fails before the change ships.
"""

from __future__ import annotations

import pytest
from langchain_ollama import ChatOllama

from log_dashboard.agent.llm import _build_real_model, _DryRunChatModel, build_chat_model
from log_dashboard.config import Settings


def test_build_real_model_forwards_timeout_via_client_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_LLM_DRY_RUN", "false")
    monkeypatch.setenv("DASHBOARD_LLM_TIMEOUT_SECONDS", "47")

    settings = Settings()  # type: ignore[call-arg]
    model = _build_real_model(settings)

    assert isinstance(model, ChatOllama)
    assert model.client_kwargs == {"timeout": 47}


def test_build_chat_model_dry_run_returns_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run gate keeps the factory from constructing ChatOllama at all,
    so `client_kwargs` plumbing is irrelevant in that branch."""
    monkeypatch.setenv("DASHBOARD_LLM_DRY_RUN", "true")
    settings = Settings()  # type: ignore[call-arg]
    model = build_chat_model(settings)
    assert isinstance(model, _DryRunChatModel)
