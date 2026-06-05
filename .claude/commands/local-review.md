# /local-review

Run a parallel multi-agent review of the local branch diff or a GitHub PR. Documented fallback for `/ultrareview` when the cloud command can't run (auth blocked, ZDR org, Bedrock/Vertex/Foundry runtime).

## When to use

- `/ultrareview` returns "GitHub repository access check failed" or otherwise can't start the remote session
- Repo is on a runtime where `/ultrareview` is unavailable
- You want a free, in-context review with no Claude.ai web dependency

## What it does NOT replicate from /ultrareview

- **No independent reproduction.** `/ultrareview`'s signature is that every finding is reproduced in a sandbox before being reported. `/local-review` does NOT reproduce — findings are based on code reading alone.
- **No fleet-per-dimension.** One agent per review angle, not many.
- This does NOT satisfy the agentreviewer policy named-target requirement. If `/ultrareview` becomes available again, prefer it for high-stakes PRs.

## Arguments

- `/local-review` (no args) → review the diff between the current branch and `main` (uncommitted + staged + committed-since-main)
- `/local-review <PR#>` → review the diff of a GitHub PR (works on open OR merged PRs)
- `/local-review <base-ref>` → review the diff against an arbitrary base ref (e.g., `origin/develop`)

## Steps

1. **Resolve scope.**
   - No arg: `git diff main...HEAD`
   - PR#: `gh pr view <PR#> --json baseRefName,headRefName,mergeCommit,state`. For merged PRs use the merge commit (`git diff <merge-commit>^ <merge-commit>`). For open PRs use the head ref against the base ref. Use `git show --stat` to enumerate changed files.
   - Base-ref: `git diff <ref>...HEAD`

2. **Confirm scope with the user.** Print the file list (under 30 files inline; over 30 says `<N> files — see git diff --stat`) and ask `Proceed with review of these <N> files? (y/n)`. If user says no, stop.

3. **Launch 4 `Explore` agents in parallel** (single message, four Agent tool calls in one block) with these focused prompts. Each gets the same file-list context but a distinct review angle.

   **Agent 1 — Design / architecture:**
   - Bundle boundaries, coupling, schema drift
   - Whether new abstractions are pulling weight
   - Missing extension points or premature ones
   - ADR consistency: does the code match documented decisions?

   **Agent 2 — Security:**
   - Credential leak audit: every log call, every error message, every response body
   - Auth gating on new routes
   - Input validation at API boundaries
   - Bearer-token / API-key handling in URLs, query params, headers, logs
   - Frontend: sensitive data rendered in the DOM?

   **Agent 3 — Correctness / async / concurrency:**
   - Race conditions (TOCTOU on separate awaits)
   - Lock omissions, lock-then-await-then-mutate patterns
   - Task lifecycle: leaks, orphans, missing `asyncio.CancelledError` re-raise
   - `gather(return_exceptions=True)` cancellation propagation bugs
   - Boundary conditions, off-by-one, integer overflow

   **Agent 4 — Test coverage / test quality:**
   - Untested branches in new production code (file:line ranges)
   - Stubs that are too clever and don't exercise the real path
   - Missing parameterized cases
   - Mocking that monkey-patches around the bug rather than testing it
   - Frontend: state machine transitions exercised?

4. **Each agent reports in this format:**
   - Bulleted findings, severity-ordered (Critical / High / Medium / Low)
   - Each finding: `file:line — one-line summary. Why it matters: <specific consequence>. Fix: <direction, not full patch>`
   - Per `feedback_review_style_no_praise`: no "looks good overall" closer; list actionable items only. If a section has no findings, say "none" and move on.
   - Under 800 words per agent.

5. **Aggregate findings.** Group cross-agent agreement (same finding from multiple angles → higher confidence). De-duplicate. Order by severity. Present a single triage list to the user.

6. **Triage with the user.** For each Critical / High finding, ask: fix in code (push commit), fix in a follow-up PR (separate branch), or push back with rationale. Don't act without confirmation on a per-finding basis.

## Cost / time

- Launches 4 parallel subagents. Wall clock ~5-10 minutes (parallel, not sequential).
- Counts against the normal Claude Code usage allowance — no separate billing.
- Bounded by the read-only Explore agent scope: no edits, no shell side effects beyond `git`/`gh` reads.

## See also

- `/ultrareview` (built-in) — the preferred cloud reviewer when available
- `.claude/rules/workflow.md` §Agentreviewer — the policy this command falls back from
- Memory: `project_agentreviewer_policy` — when to invoke which reviewer
