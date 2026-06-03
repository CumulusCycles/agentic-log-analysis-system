# ADR-009: Adopt GitHub Actions for CI (Lint + Unit Tests + Build)

**Status:** Accepted

## Decisions

1. CI runs on GitHub-hosted Ubuntu runners. Triggers: `pull_request` to `main`, `push` to `main` (so badges and main-state reflect post-merge truth), `workflow_dispatch` (manual rerun).
2. CI scope mirrors the `/ship` rule shipped in PR #10, with one addition: each app's job runs when its `apps/<name>/**` files changed, OR when shared-contract files changed (`apps/shared-data-api/**`, `docker-compose.yml`, `.env.example`, `.claude/rules/apps.md`), OR when **`.github/workflows/**`** changed. The workflow file itself is added to the CI trigger so changes to the CI pipeline get validated against every app on the same PR. This is intentionally absent from `/ship`'s shared-contract list (which is about *runtime* contracts that can break consumers); workflow files affect *CI behavior*, not runtime, so they belong here but not there. On `push` to `main` and `workflow_dispatch`, every job runs.
3. Each app's job runs lint + typecheck/build + unit tests against the current source. Pass/fail is reported as one PR check row per app.
4. CI does **not** run: Playwright E2E (requires the live Docker stack — see decision 5), container image builds, image pushes, deployment. E2E remains local-only via `/ship`.
5. E2E in CI was considered and deferred. The two viable paths are (a) skipping it (defeats the purpose) or (b) a self-hosted runner with Docker (ties CI to a maintained machine + ongoing infra burden). The scoped `/ship` rule already enforces E2E locally when the shared contract moves, and the PR test-plan discipline keeps the gate honest.
6. Default `GITHUB_TOKEN` is used with least-privilege permissions (`contents: read`, `pull-requests: write`, `checks: write`). No fine-grained PAT, no organization-level secrets, no rotation maintenance.
7. The dashboard job is defined now with a filesystem existence check in the `changes` job (`dashboard_exists` output testing for `dashboard/pyproject.toml`). The dashboard job's `if:` gates on that output, so the job activates automatically once Phase 7 scaffolds the directory — no follow-up CI PR required when Phase 7 lands.
8. Branch protection on `main` (require CI checks before merge) is **recommended** but configured outside this PR, in repo Settings → Branches. The workflow file is the prerequisite; flipping the protection switch is a one-click follow-up.

## Rationale

Reverses the over-broad rule in `CLAUDE.md` that conflated *app deployment* (still disallowed — local Docker Compose only) with *remote CI* (now permitted). They are independent decisions; bundling them prevented a useful machine-enforced PR gate.

GH Actions adds three things local `/ship` cannot:

- **Independent verification on a clean checkout.** Local runs benefit from existing virtualenvs, cached node_modules, and accumulated state. CI proves the repo is buildable from zero — catches missing files, stale lockfiles, dependency drift, and "works on my machine" issues that `/ship` is structurally blind to.
- **Machine-enforced merge gate.** Once branch protection is enabled, a red PR cannot be merged. No more honor-system "did I run the tests?"
- **Persistent run history.** Every PR and push leaves an artifact under the Actions tab — useful for triaging post-merge regressions.

The path-filter scoping is deliberate: it mirrors the `/ship` rule exactly so CI cost matches local cost. Small PRs trigger small CI. SDA / shared-infra PRs trigger the full sweep. There is no situation where CI runs *more* than `/ship` did locally — the two stay in lockstep.

E2E is deferred for the cost/benefit reason in decision 5. Spinning up Docker on a GitHub-hosted runner for each PR is technically possible but slow (~3–5 min just for stack bring-up). Self-hosted is faster but introduces infra to maintain. Neither is justified while the manual `/ship` E2E gate works and the apps' wire format is stable.

## Consequences

- New file `.github/workflows/ci.yml` containing one matrix workflow with five per-app jobs (SDA, FNOL, CP, AP, dashboard) plus a paths-filter detection job.
- `CLAUDE.md` Quick Reference's "No cloud deployment" bullet is rewritten to distinguish app runtime (still local-only) from CI (GH Actions, scoped to lint + unit + build).
- Every PR shows 1–5 check rows (one per changed app, or all five when shared-infra changed). Click any check to see the build log; a failed test name appears in the log near the failure.
- README CI status badges and `dorny/test-reporter`-style inline PR annotations are intentionally **out of scope for this PR** — they depend on the workflow existing on `main` first. Both are small follow-up PRs.
- When Phase 7 scaffolds the dashboard, its CI job activates automatically the next time `dashboard/pyproject.toml` exists on `main` — no workflow edit needed.
- Local `/ship` workflow is unchanged. CI is the *additional*, after-push verification layer; the pre-push gate stays in place.
- The branch protection setting is documented as a recommended manual follow-up. Without it, CI is informational, not enforcing. With it, the workflow becomes a true merge gate.
- Future regressions of the "no remote CI/CD" line should be checked against this ADR. The line was right for app deployment; it was wrong for CI.
