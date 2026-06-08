"""Shared helpers for the dashboard backend test suite.

Module name prefixed with `_` so pytest's auto-collection does not treat
it as a test file. Imported by `test_proactive_scan.py` and
`test_vectorstore.py` for the Settings alias-translation helper.
"""

from __future__ import annotations

from typing import Any

from log_dashboard.config import Settings


def to_alias_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Translate Settings field-name kwargs to alias form.

    pydantic-settings gives env-via-alias precedence over field-name init
    kwargs (with `populate_by_name=True`). The test conftest sets several
    alias env vars (`DASHBOARD_LLM_DRY_RUN`, `OLLAMA_BASE_URL`, etc.), so
    a field-name kwarg like `dashboard_llm_dry_run=False` would silently
    lose to the env value. Translate to alias-form here so test overrides
    actually win.

    Fields without an explicit alias pass through unchanged (the `f.alias
    or n` fallback covers them).
    """
    field_to_alias = {n: (f.alias or n) for n, f in Settings.model_fields.items()}
    return {field_to_alias.get(k, k): v for k, v in kwargs.items()}
