"""The proactive-scan prompt template.

Held in its own module so the wording can evolve without churning
`proactive.py` and so it's easy to import in tests.

The `NO_ANOMALIES` sentinel lets the agent declare a quiet scan without
producing a noise finding — `_run_one_scan` returns `None` when the answer
starts with that exact string and the ring buffer stays empty.
"""

from __future__ import annotations

NO_ANOMALIES_SENTINEL = "NO_ANOMALIES"


PROACTIVE_SCAN_PROMPT = (
    "You are reviewing the last {lookback_minutes} minutes of application "
    "logs from a 4-app insurance system (Shared Data API, FNOL, Customer "
    "Portal, Agent Portal). The Chroma corpus admits all log levels — INFO "
    "establishes the steady-state baseline, WARN/ERROR mark deviations.\n\n"
    "Suggested approach:\n"
    " 1. Use `query_logs` to retrieve recent INFO entries and form a sense "
    "of what normal looks like (request rates, common events, response "
    "shapes per app).\n"
    " 2. Use `query_logs` again to look for WARN/ERROR clusters, "
    "cross-app cascades, or error-rate spikes that deviate from the "
    "baseline you just established.\n"
    " 3. Assess: is the deviation real (rate elevated vs. baseline, "
    "response time abnormal, an event-type missing that normally fires) "
    "or is it noise within the normal envelope?\n\n"
    "If nothing is worth surfacing to an operator, respond with EXACTLY "
    "this single line and nothing else:\n\n"
    "  " + NO_ANOMALIES_SENTINEL + "\n\n"
    "Otherwise, respond with a 1-2 sentence summary describing the "
    "anomaly. Reference the specific signal (event names, error classes, "
    "elevated counts vs. baseline). The system will extract your "
    "citations automatically from the tool results — do NOT manually list "
    "log IDs in your summary. Do not include remediation steps; the "
    "operator will drill in via the Error Detail page."
)


def render_prompt(lookback_minutes: int) -> str:
    """Render the prompt with the configured lookback window."""
    return PROACTIVE_SCAN_PROMPT.format(lookback_minutes=lookback_minutes)
