"""Unit tests for `agent/responses.py` helpers.

Focused on the Phase 8 / ADR-017 changes:
- `is_llm_api_error` — broadened from the Phase 7 `openai.APIError` check
  to httpx subclasses + `ollama.ResponseError` matched by module + class
  name (no import dependency).
- `count_tokens` — heuristic `len(text) // 4`, dropped the `model` arg.
"""

from __future__ import annotations

import httpx
import pytest

from log_dashboard.agent.responses import count_tokens, is_llm_api_error

# ---------------------------------------------------------------------------
# is_llm_api_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("could not connect"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.WriteTimeout("write timed out"),
        httpx.PoolTimeout("pool exhausted"),
    ],
)
def test_is_llm_api_error_true_for_httpx_transport_errors(exc) -> None:
    """Each httpx transport-failure subclass ChatOllama can raise should
    surface as a 502 via the routers."""
    assert is_llm_api_error(exc) is True


def test_is_llm_api_error_true_for_httpx_status_error() -> None:
    """Non-2xx replies from Ollama come through as `HTTPStatusError`."""
    request = httpx.Request("POST", "http://ollama:11434/api/generate")
    response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("boom", request=request, response=response)
    assert is_llm_api_error(exc) is True


def test_is_llm_api_error_true_for_timeouterror() -> None:
    """Builtin `TimeoutError` (which `asyncio.TimeoutError` aliases in
    Python 3.12+) — generic timeout from any blocking call inside the
    LLM round-trip."""
    assert is_llm_api_error(TimeoutError()) is True


def test_is_llm_api_error_true_for_connectionerror() -> None:
    """OS-level connection failures (e.g., from refused sockets)."""
    assert is_llm_api_error(ConnectionError("refused")) is True


def test_is_llm_api_error_true_for_ollama_response_error() -> None:
    """The `ollama` python client raises `ResponseError` on non-200
    replies. We match by module + class name to avoid an import-time
    dependency on the `ollama` package."""
    response_error_cls = type("ResponseError", (Exception,), {"__module__": "ollama"})
    exc = response_error_cls("model not found")
    assert is_llm_api_error(exc) is True


def test_is_llm_api_error_true_for_ollama_submodule_response_error() -> None:
    """`ollama.client.ResponseError` and similar submodule paths must
    also match (the `startswith("ollama.")` branch)."""
    response_error_cls = type("ResponseError", (Exception,), {"__module__": "ollama.client"})
    exc = response_error_cls("boom")
    assert is_llm_api_error(exc) is True


def test_is_llm_api_error_false_for_unrelated_module_named_response_error() -> None:
    """A third-party package whose module name STARTS WITH `ollama` but
    isn't the real Ollama client (e.g., `ollama_utils.ResponseError`)
    must NOT be misclassified. Guards against the over-loose
    `startswith("ollama")` match."""
    response_error_cls = type("ResponseError", (Exception,), {"__module__": "ollama_utils"})
    exc = response_error_cls("unrelated")
    assert is_llm_api_error(exc) is False


def test_is_llm_api_error_false_for_value_error() -> None:
    """Programming / schema errors must bubble to the global 500 handler,
    not be silently mapped to 'upstream LLM unavailable'."""
    assert is_llm_api_error(ValueError("bad input")) is False


def test_is_llm_api_error_false_for_generic_exception() -> None:
    """Catch-all bare Exception is not an LLM transport error."""
    assert is_llm_api_error(Exception("anything")) is False


def test_llm_api_error_types_tuple_contents() -> None:
    """The module-level `_LLM_API_ERROR_TYPES` tuple is the single source
    of truth for what counts as an LLM transport failure. Asserting its
    contents directly pins the expected set — a future refactor that
    accidentally drops a type (or adds one without updating tests + docs)
    will fail this test rather than silently change routing behavior."""
    import httpx

    from log_dashboard.agent.responses import _LLM_API_ERROR_TYPES

    expected: set[type[BaseException]] = {
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.HTTPStatusError,
        TimeoutError,
        ConnectionError,
    }
    assert set(_LLM_API_ERROR_TYPES) == expected


def test_is_llm_api_error_does_not_catch_bare_httpx_http_error() -> None:
    """The base `httpx.HTTPError` is intentionally NOT caught — only the
    specific transport subclasses ChatOllama actually raises. A future
    non-LLM httpx caller in the graph (e.g., a tool that fetches an
    upstream URL) would raise something not in the narrowed set, and we
    want it to surface as a real 500, not a mis-mapped 502."""

    class _CustomHttpError(httpx.HTTPError):
        """Subclass of HTTPError that isn't one of the narrowed types."""

    exc = _CustomHttpError("hypothetical")
    assert is_llm_api_error(exc) is False


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


def test_count_tokens_zero_for_empty_string() -> None:
    assert count_tokens("") == 0


def test_count_tokens_heuristic_is_len_div_4() -> None:
    """The heuristic is intentionally coarse (`len(text) // 4`) — Phase 8
    drops `tiktoken` because the count is now a safety bound, not a
    billing meter."""
    assert count_tokens("a" * 100) == 25
    assert count_tokens("a" * 4001) == 1000


def test_count_tokens_accepts_single_argument() -> None:
    """Phase 8 dropped the `model` parameter; only `text` remains."""
    assert count_tokens("hello world") == len("hello world") // 4
