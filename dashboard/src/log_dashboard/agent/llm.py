"""Chat-model factory — the switch between real Ollama and the dry-run fake.

`build_chat_model(settings)` returns one of two things:

- `settings.dashboard_llm_dry_run=True`: `_DryRunChatModel` — a state-aware
  fake that emits ONE tool call when no tool results are present, and the
  canned final answer once a `ToolMessage` has been seen. The graph runs
  ingest → analyze → correlate → predict → respond exactly once,
  exercising every node without any network call. Phase 7's safe-by-default
  rationale (ADR-015 §5) was cost-asymmetry against OpenAI; Phase 8 /
  ADR-017 rescinds that — the mechanism is preserved as a test-harness
  convenience (tests don't pay the 5-30s of local LLM latency per call).
- `settings.dashboard_llm_dry_run=False` (runtime default post-Phase-8):
  real `ChatOllama` against `settings.dashboard_llm_model` reached at
  `settings.ollama_base_url`.

The factory is the ONLY place dry-run vs real is decided.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable

from ..config import Settings

# Dry-run canned final answer. Surfaced verbatim to the chat UI; the React
# page also shows a "DRY RUN" banner when `ChatResponse.dry_run=True`.
_DRY_RUN_CANNED = (
    "DRY_RUN: agent did not contact the LLM. "
    "Set DASHBOARD_LLM_DRY_RUN=false in .env to enable real LLM responses."
)

_DRY_RUN_TOOL_CALL = {
    "name": "query_logs",
    "args": {"query": "errors", "top_k": 3},
    "id": "dry_run_call_1",
    "type": "tool_call",
}


class _DryRunChatModel(BaseChatModel):
    """State-aware fake chat model for dry-run mode.

    The graph calls this model from BOTH `analyze` and `predict` nodes. The
    naive `GenericFakeChatModel` with a scripted iterator doesn't work
    here because the factory is invoked fresh per node (the iterator
    restarts), so every call would request a tool, causing an infinite
    loop bounded only by `tool_budget_remaining`.

    Inspecting the input messages instead lets us produce the right
    response without sharing state across factory invocations:

    * Input contains a `ToolMessage` → tools have already run → return the
      canned final answer (no tool_calls) → `respond` finalises.
    * Input has no `ToolMessage` yet → first LLM call → request one
      `query_logs` tool call → `correlate` dispatches.

    Provider-agnostic — works identically when the real model is
    `ChatOpenAI` (Phase 7) or `ChatOllama` (Phase 8 / ADR-017).
    """

    @property
    def _llm_type(self) -> str:
        return "dry-run-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable:  # type: ignore[override]
        # Fake doesn't actually need the tools list — it scripts the tool
        # call by name. Return self so the graph's `.bind_tools(...)` chain
        # works without branching on dry-run.
        return self

    @staticmethod
    def _respond(messages: list[BaseMessage]) -> AIMessage:
        for msg in messages:
            if isinstance(msg, ToolMessage):
                return AIMessage(content=_DRY_RUN_CANNED)
        return AIMessage(content="", tool_calls=[_DRY_RUN_TOOL_CALL])


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Return the chat model the agent should use this request."""
    if settings.dashboard_llm_dry_run:
        return _DryRunChatModel()
    return _build_real_model(settings)


def _build_real_model(settings: Settings) -> BaseChatModel:
    """Real `ChatOllama` against the local Ollama container.

    Import is deferred so dry-run-only tests don't pay the
    `langchain_ollama` import cost.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.dashboard_llm_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        # Without this, an Ollama hang would block graph.ainvoke indefinitely.
        # 30s covers a slow generation on a saturated M1 Max; longer-form
        # reasoning hits the `timeout` boundary, surfaces as
        # is_llm_api_error, and the router maps it to 502 instead of
        # hanging the response. Standard LangChain ChatModel parameter
        # (forwarded to the langchain-ollama transport).
        timeout=30,
    )
