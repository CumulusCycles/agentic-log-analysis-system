"""Agitator — operator-driven load generator bundled into the dashboard.

See ADR-014 for the bundle-not-separate-container rationale and the
operator-button-only invariant. Every outbound request tags `X-Source:
synthetic` so the apps' loggers attribute the traffic to the Agitator and
the dashboard's 7d ingest gate (now `prod,synthetic`) admits it.
"""
