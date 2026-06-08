# ADR-009: Adopt GitHub Actions for CI (Per-App Workflows + README Badges)

**Status:** Superseded by [ADR-012](ADR-012-consolidate-ci-workflows.md) — 2026-06-05

> **Original decision (now superseded):** CI ran as five per-app workflow files under `.github/workflows/ci-<app>.yml` (`ci-shared-data-api`, `ci-fnol`, `ci-customer-portal`, `ci-agent-portal`, `ci-dashboard`), each with `on.pull_request.paths` + `on.push.paths` scoping. Each workflow ran exactly one job whose pass/fail backed a per-app shields.io README badge. CI did not run Playwright E2E, container builds, or image pushes; the local `/ship` gate carried E2E.
>
> **What replaced it:** [ADR-012](ADR-012-consolidate-ci-workflows.md) consolidated the five files into a single `.github/workflows/ci.yml` containing a `dorny/paths-filter@v3` `changes` job + five conditional per-app jobs (same job names, same steps, per-job concurrency). The five per-app README badges collapsed into one `ci` badge. The supporting decisions from ADR-009 (path filtering, one job per app, no E2E in CI, `GITHUB_TOKEN` posture, dashboard timing) carry forward into ADR-012 verbatim.
>
> Branch-protection check names now use the `ci / <app>` prefix because the workflow has multiple jobs; required checks were updated accordingly.
>
> Retained for project history.
