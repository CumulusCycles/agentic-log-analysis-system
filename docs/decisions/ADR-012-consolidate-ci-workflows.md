# ADR-012: Consolidate CI into a Single Workflow with Paths-Filter Conditional Jobs

**Status:** Accepted (supersedes parts of [ADR-009](ADR-009-github-actions-ci.md))

## Decisions

1. CI is one workflow file: `.github/workflows/ci.yml`. The five prior per-app
   files (`ci-shared-data-api.yml`, `ci-fnol.yml`, `ci-customer-portal.yml`,
   `ci-agent-portal.yml`, `ci-dashboard.yml`) are removed.
2. `ci.yml` contains a `changes` job that runs `dorny/paths-filter@v3` against
   the PR diff. The job exposes seven outputs: one per app (`shared-data-api`,
   `fnol`, `customer-portal`, `agent-portal`, `dashboard`) plus `shared-apps`
   (`docker-compose.yml` + `.env.example` + `.claude/rules/apps.md` +
   `.github/workflows/**`) and `shared-dashboard` (the same shared infra paths
   but with `.claude/rules/dashboard.md` substituted).
3. Each per-app job has `needs: changes` and gates itself on `if:
   needs.changes.outputs.<app> == 'true' || needs.changes.outputs.shared-<group>
   == 'true'`. App jobs that don't apply are skipped — skipped jobs report a
   success status to branch protection, matching the prior per-app workflows'
   non-trigger behavior.
4. Per-app job names are preserved (`shared-data-api`, `fnol`,
   `customer-portal`, `agent-portal`, `dashboard`) — same as the prior
   per-app workflows' single-job names. The step content of each job is
   copied verbatim from the corresponding prior workflow. Per-job
   `concurrency:` groups keep the existing fast-PR-doesn't-queue behavior
   (`group: <app>-${{ github.ref }}`).
5. Workflow-level `paths:` filter is the union of all prior per-app filters:
   `apps/**`, `dashboard/**`, `docker-compose.yml`, `.env.example`,
   `.claude/rules/apps.md`, `.claude/rules/dashboard.md`,
   `.github/workflows/**`. Doc-only PRs (touching only `docs/**`, `.claude/**`
   non-rules, `CLAUDE.md`, `PLAN.md`, `README.md`) do not trigger the workflow
   at all, matching the prior behavior.
6. README replaces five per-app shields.io badges with a single `ci` badge
   pointing at `ci.yml`. **Per-app badge granularity at the README level is
   intentionally dropped.**
7. Branch-protection check-name contexts change from the bare per-app names
   (`shared-data-api`, etc.) to the prefixed form (`ci / shared-data-api`,
   etc.). The `changes` job is **not** required — it's a setup job; its
   success is implied by any downstream app job running and passing.
   Verify exact check names with
   `gh api repos/<owner>/<repo>/commits/<sha>/check-runs --jq '.check_runs[]
   | .name'` before applying protection.

## Rationale

ADR-009's core rationale was "per-app visibility on the README is the original
goal of adopting CI in the first place." That call was correct in context
(adopting CI from zero with a portfolio repo in mind). Three follow-on
observations changed the tradeoff:

1. **Run count.** Cross-cutting changes (`docker-compose.yml`,
   `.env.example`, `.claude/rules/apps.md`) trigger every per-app workflow.
   With 5 workflows and ~32 PRs to date, the Actions tab accumulates a lot
   of run records (≥100 historical runs by 2026-06-05). The per-app structure
   amplifies what is conceptually one CI run into five.
2. **Per-app badges have practical limits.** A reader scanning the README sees
   five identical green/red badges for a healthy repo — the granularity rarely
   surfaces actionable information. When debugging is needed, the Actions tab
   (which still shows per-job status) is the destination, not the badge.
3. **The branch-protection nuance is unchanged.** Whether checks are bare
   names (prior architecture) or `ci /`-prefixed (this architecture), the
   "required-check-must-report-or-block" problem is the same. We accept the
   prefix change as a one-time documentation update; future protection
   application uses the new form.

The consolidation **preserves** everything ADR-009 got right that wasn't
specific to per-app file structure: paths filtering, single-job-per-app step
content, `pull_request` + `push: main` + `workflow_dispatch` triggers, no
E2E in CI, read-only `GITHUB_TOKEN`, no PR-side annotations. Decisions 2–7
of ADR-009 carry forward verbatim. Decisions 1 and 8 are replaced by this
ADR's decisions 1 and 6 respectively.

## Consequences

- `.github/workflows/` shrinks from 5 files to 1.
- README badge row shrinks from 5 per-app badges to 1 `ci` badge (plus the
  existing License + Platform badges).
- A typical single-app PR triggers 1 workflow run with 1 app job executing
  (the others skip). Previously: 1 workflow run with 1 job. Net: same.
- A cross-cutting PR triggers 1 workflow run with all 5 app jobs executing.
  Previously: 5 workflow runs, each with 1 job. Net: 5 → 1 run record.
- Doc-only PRs trigger zero workflows. Previously: same. Net: same.
- The `changes` job adds ~10s overhead per run (checkout + paths-filter). This
  is paid once per workflow run regardless of how many app jobs follow.
- Branch-protection memory ([[project_go_public_branch_protection]]) +
  CI-pattern memory ([[reference_per_app_ci_workflow_pattern]] — slug
  retained, content updated) updated to reflect the new check-name format.
- `CLAUDE.md` Quick Reference's CI bullet glob `.github/workflows/ci-*.yml`
  is updated to `.github/workflows/ci.yml`.
- ADR-009 is marked Superseded by ADR-012 in its header — its file remains
  for traceability.

## What this ADR does NOT change

- Per-app step content (lint, typecheck, build, tests) — copied verbatim.
- Per-app concurrency groups — preserved at the job level.
- The local `/ship` pipeline.
- The decision to keep E2E local-only.
- `permissions: contents: read` posture.
- `pull_request` / `push: main` / `workflow_dispatch` trigger surface.

## Amendment — 2026-06-08

Decision 5 above (workflow-level `paths:` filter so doc-only PRs do not
trigger the workflow at all) is **rescinded**. The workflow now triggers on
every `pull_request` and `push: main` without a paths filter.

**Why:** when the repo went public on 2026-06-08, branch protection with
required status checks was applied to `main`. A workflow that doesn't
trigger means the required checks never report, and the PR is blocked
indefinitely waiting for them. Doc-only PRs (e.g., the project-wide
markdown audit in PR #49) were previously fine because there was no
required-check gate; once required checks gate `main`, the non-trigger
becomes a hang.

**How the docs-only PR case still works:** the `changes` job runs on
every PR. For a docs-only diff, all five per-app outputs evaluate to
`false`; each per-app job's `if:` condition is false; each job skips.
Skipped jobs report a success status to branch protection. Required
checks all report success → PR is mergeable.

**Cost:** ~5s of `changes`-job overhead per docs-only PR (checkout +
`dorny/paths-filter@v3`). Below the noise floor for a portfolio repo.

Decisions 1–4 and 6–7 remain in force.
