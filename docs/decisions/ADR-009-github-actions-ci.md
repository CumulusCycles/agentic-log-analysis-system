# ADR-009: Adopt GitHub Actions for CI (Per-App Workflows + README Badges)

**Status:** Superseded by [ADR-012](ADR-012-consolidate-ci-workflows.md) — 2026-06-05

ADR-012 consolidates the five per-app workflow files into a single
`.github/workflows/ci.yml` with `dorny/paths-filter@v3` gating per-app jobs,
and collapses the five per-app README badges into one `ci` badge. ADR-009's
decisions 2, 3, 4, 5, 6, 7 (path filtering, one job per app, no E2E, GH token
posture, dashboard timing) carry forward into ADR-012. Decisions 1 (per-app
files) and 8 (per-app badges) are reversed.

Original decisions retained below for historical context.

## Decisions

1. CI runs on GitHub-hosted Ubuntu runners. One workflow file per app under `.github/workflows/ci-<app>.yml` (`ci-shared-data-api.yml`, `ci-fnol.yml`, `ci-customer-portal.yml`, `ci-agent-portal.yml`; `ci-dashboard.yml` lands with Phase 7). Each workflow's triggers are: `pull_request` to `main` (the PR-time gate), `push` to `main` (so the per-app status badge tracks `main` HEAD after merge), `workflow_dispatch` (manual rerun).
2. Each workflow scopes itself via `on.pull_request.paths` and `on.push.paths` — same path list mirrors the `/ship` shared-contract rule plus `.github/workflows/**`: that app's `apps/<app>/**`, `docker-compose.yml`, `.env.example`, `.claude/rules/apps.md`, `.github/workflows/**`. A workflow that doesn't trigger simply doesn't run; there's no skipped-job noise in the PR checks UI (this is the structural advantage over the v1 single-workflow + `dorny/paths-filter` design).
3. Each workflow contains exactly one job (named for the app) that runs lint + typecheck/build + unit tests for that app. The job's pass/fail IS the per-app CI status — that's what shields.io reads to render the README badge.
4. CI does **not** run: Playwright E2E (requires the live Docker stack — see decision 5), container image builds, image pushes, deployment. E2E remains local-only via `/ship`.
5. E2E in CI was considered and deferred. The two viable paths are (a) skipping it (defeats the purpose) or (b) a self-hosted runner with Docker (ties CI to a maintained machine + ongoing infra burden). The scoped `/ship` rule already enforces E2E locally when the shared contract moves, and the PR test-plan discipline keeps the gate honest.
6. Default `GITHUB_TOKEN` is used with `permissions: contents: read` only. No fine-grained PAT, no organization-level secrets, no PR-comment or check-run permissions (no `dorny/test-reporter` or similar PR-side annotations — the badges + the workflow status are the surface).
7. The dashboard workflow (`ci-dashboard.yml`) is added in the Phase 7 PR that scaffolds `dashboard/`. The dashboard badge in README appears at the same time. No empty workflow file or placeholder badge before then.
8. README carries a per-app status badge for each per-app workflow, plus static License (MIT) and Platform (linux/arm64) badges. Each per-app badge URL: `https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-<app>.yml?branch=main&label=<app>`. The `branch=main` filter is why each workflow needs the `push: main` trigger — without it, `branch=main` has no run history and shields.io renders "no status."

## Rationale

The original single-workflow architecture (v1, PRs #11–#15) used a matrix of per-app jobs gated by `dorny/paths-filter`. That gave us per-app PR checks but only one workflow-level CI signal — there was no way to render per-app badges in the README. Per-app *visibility on the README* was the original goal of adopting CI in the first place (see PR #11 thread); the v1 architecture buried it.

Per-app workflow files fix that directly. Each workflow has its own URL, its own status, its own badge. The PR-time check rows still show per-app status (just one check per app from one workflow, instead of one check per app from one matrix), and now the README does too.

`push: main` triggers come back per workflow — but path-scoped, so only the workflow whose app actually changed re-runs after merge. For a typical PR that touches one app, that's one workflow running twice (PR + post-merge). Same total cost as the v1 single-workflow + `push: main` design, lower than v1-without-`push: main` would be once you account for the badge requirement. Trade is intentional: badge accuracy on `main` is the deliverable.

Path-filter at the trigger level (`on.pull_request.paths`) is structurally simpler than the v1 `dorny/paths-filter` job + per-job `if:` indirection: a workflow that doesn't match its path list never runs, never reports a "skipped" check, never adds noise. This also resolves the v1 §8 "skipped status does not satisfy a required check" problem — there's no skipped check to satisfy in the first place.

## Consequences

- Four new workflow files: `ci-shared-data-api.yml`, `ci-fnol.yml`, `ci-customer-portal.yml`, `ci-agent-portal.yml`. The v1 `.github/workflows/ci.yml` is removed.
- README gains four per-app status badges in addition to License + Platform.
- `CLAUDE.md` Quick Reference's CI bullet is updated to reference `.github/workflows/ci-*.yml` (glob) instead of the now-deleted single file.
- Every PR shows 1–4 check rows (one per affected app's workflow). PRs that don't touch any app code or shared infra trigger zero CI workflows.
- Branch protection on `main` (when added) lists each per-app workflow's job name as a required check (`shared-data-api`, `fnol`, `customer-portal`, `agent-portal`, eventually `dashboard`). One nuance to handle at protection-enable time: a workflow that doesn't trigger (paths didn't match) doesn't produce a required check. Either (a) drop the path scoping at trigger level so every workflow runs on every PR (simpler, higher CI cost), or (b) configure required checks with the "Auto-merge with expected checks" semantics that don't require a check to run, only to succeed if it did. Decision deferred to the moment protection is enabled.
- When Phase 7 scaffolds the dashboard, that PR adds `ci-dashboard.yml` + the dashboard badge to README in one shot.
- Local `/ship` workflow is unchanged. CI is the *additional*, post-push verification layer (PR-time + post-merge for the affected app's workflow); the pre-push gate stays in place.
- Future regressions of the "no remote CI/CD" line should be checked against this ADR. The line was right for app deployment; it was wrong for CI.
