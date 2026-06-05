#!/bin/bash
# /ship Step 0 — Tool-enforcement audit.
# Fails closed if any tool /ship or /lint prescribes is not bound in CI.
#
# Why this exists: PR #29 (211 dormant AP checkstyle violations) and PR #30
# (Node format:check listed in /ship but no package.json declared it, no CI
# workflow ran it) both surfaced the same root cause — a tool prescribed in
# a process doc that CI never enforces accumulates silent drift. This audit
# catches that pattern at /ship time before it becomes a months-late audit.
#
# Exit 0 = all prescribed tools are bound. Exit 1 = at least one gap; fix and rerun.
# No --skip-audit flag by design (per feedback_dormant_lint_tools).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

AUDIT_FAILED=0
FAIL() { echo "  MISSING: $1"; AUDIT_FAILED=1; }

echo "/ship audit — verifying prescribed tools are bound in CI..."

# 1. Node: every package with "lint" must also have format:check + format + prettier devDep
NODE_PACKAGES=(
  apps/fnol/frontend/package.json
  apps/customer-portal/package.json
  apps/customer-portal/frontend/package.json
  apps/agent-portal/frontend/package.json
  dashboard/frontend/package.json
)
for pkg in "${NODE_PACKAGES[@]}"; do
  [ -f "$pkg" ] || { FAIL "$pkg does not exist"; continue; }
  grep -q '"lint"' "$pkg" || continue
  grep -q '"format:check"' "$pkg" || FAIL "format:check script in $pkg"
  grep -q '"format"' "$pkg"       || FAIL "format script in $pkg"
  grep -q '"prettier"' "$pkg"     || FAIL "prettier devDep in $pkg"
done

# 2. Python: ruff + black configured in every pyproject.toml
PY_PROJECTS=(
  apps/shared-data-api/pyproject.toml
  apps/fnol/pyproject.toml
  dashboard/pyproject.toml
)
for pp in "${PY_PROJECTS[@]}"; do
  [ -f "$pp" ] || { FAIL "$pp does not exist"; continue; }
  grep -qE '^\[tool\.ruff'  "$pp" || FAIL "[tool.ruff] section in $pp"
  grep -qE '^\[tool\.black' "$pp" || FAIL "[tool.black] section in $pp"
done

# 3. Java: maven-checkstyle-plugin bound to a Maven phase in agent-portal pom.xml
AP_POM=apps/agent-portal/pom.xml
if [ -f "$AP_POM" ]; then
  grep -q '<artifactId>maven-checkstyle-plugin</artifactId>' "$AP_POM" \
    || FAIL "maven-checkstyle-plugin declared in $AP_POM"
  grep -q '<phase>verify</phase>' "$AP_POM" \
    || FAIL "checkstyle phase binding (<phase>verify</phase>) in $AP_POM"
else
  FAIL "$AP_POM does not exist"
fi

# 4. CI workflow enforces what /ship prescribes
# Per ADR-012, CI is consolidated into a single .github/workflows/ci.yml with
# per-app conditional jobs. format:check appears in 4 Node-using jobs (FNOL,
# Customer Portal, Agent Portal, dashboard); mvn verify appears in the
# agent-portal job. Checking for at least one occurrence of each is sufficient
# — if any per-app job's step were missing format:check, this script would
# need to grow per-job assertions, but a missing top-level step is the more
# common drift pattern.
CI_WORKFLOW=.github/workflows/ci.yml
if [ -f "$CI_WORKFLOW" ]; then
  grep -q 'format:check' "$CI_WORKFLOW" || FAIL "format:check step in $CI_WORKFLOW"
  grep -qE 'mvn(w)?[^A-Za-z].*verify' "$CI_WORKFLOW" \
    || FAIL "mvn verify step in $CI_WORKFLOW"
else
  FAIL "$CI_WORKFLOW does not exist"
fi

# Result
if [ "$AUDIT_FAILED" -eq 1 ]; then
  echo ""
  echo "/ship audit FAILED — fix the gaps above and rerun."
  echo "See feedback_dormant_lint_tools for the meta-lesson."
  exit 1
fi

echo "/ship audit PASSED — all prescribed tools are bound in CI."
exit 0
