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

# 4. CI workflows enforce what /ship prescribes
NODE_CI_WORKFLOWS=(
  .github/workflows/ci-fnol.yml
  .github/workflows/ci-customer-portal.yml
  .github/workflows/ci-agent-portal.yml
  .github/workflows/ci-dashboard.yml
)
for wf in "${NODE_CI_WORKFLOWS[@]}"; do
  [ -f "$wf" ] || { FAIL "$wf does not exist"; continue; }
  grep -q "format:check" "$wf" || FAIL "format:check step in $wf"
done

AP_CI=.github/workflows/ci-agent-portal.yml
if [ -f "$AP_CI" ]; then
  grep -qE 'mvn(w)?[^A-Za-z].*verify' "$AP_CI" \
    || FAIL "mvn verify step in $AP_CI"
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
