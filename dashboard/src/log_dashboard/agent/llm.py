"""Chat-model factory — the single switch between paid OpenAI and dry-run fake.

`build_chat_model(settings)` returns one of two things:

- `settings.dashboard_llm_dry_run=True` (the default per Settings —
  safe-by-default): `_DryRunChatModel` — a state-aware fake that emits
  ONE tool call when no tool results are present, and the canned final
  answer once a `ToolMessage` has been seen. The graph runs analyze →
  correlate → predict → respond exactly once, exercising every node
  without any network call.
- `settings.dashboard_llm_dry_run=False`: real `ChatOpenAI` against
  `settings.openai_chat_model` with `settings.openai_api_key`.

The factory is the ONLY place dry-run vs paid is decided. Tests can leave
the default; CI cannot accidentally hit OpenAI.
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
    "DRY_RUN: agent did not contact OpenAI. "
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
    return _build_paid_model(settings)


def _build_paid_model(settings: Settings) -> BaseChatModel:
    """Real ChatOpenAI. Import is deferred so dry-run-only tests don't pay
    the import cost (langchain_openai pulls a non-trivial dep tree)."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
