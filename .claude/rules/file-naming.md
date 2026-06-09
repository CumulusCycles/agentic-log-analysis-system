# Project Rules — File Naming

**Mandatory.** Follow `docs/tech/file-naming-convention.md` for every new file, rename, and
reference update.

---

## When This Applies

- Creating any file in the repo
- Renaming or moving files
- Scaffolding apps under `apps/` or `dashboard/`
- Adding or editing Claude Code resources under `.claude/`
- Pre-ship and `/ship` doc checks

---

## Quick Rules (enforce without exception)

| Location | Convention | Example |
| --- | --- | --- |
| `docs/**/*.md` | kebab-case | `development-workflow.md` |
| `docs/decisions/` | `ADR-NNN-kebab-slug.md` | `ADR-001-local-docker-only.md` |
| `.claude/commands/` | kebab-case `.md` | `self-review.md` |
| `.claude/agents/` | kebab-case `.md` | `git-agent.md` |
| `.claude/rules/` | kebab-case `.md` | `file-naming.md` |
| `.claude/skills/*/` | kebab-case dir + `SKILL.md` | `.claude/skills/log-analysis/SKILL.md` |
| `.claude/hooks/` | snake_case `.sh` | `.claude/hooks/pre_bash_guard.sh` |
| `site/` | kebab-case `.html` + `index.html` | `site/docker-architecture.html`, `site/index.html` |
| Root exempt only | See convention doc | `CLAUDE.md`, `PLAN.md`, `README.md`, and others — full list in `docs/tech/file-naming-convention.md` |

---

## Agent Behavior

1. **Before writing a new file** — choose a name that matches the table above; if unsure,
   read `docs/tech/file-naming-convention.md`.
2. **If an existing file violates the convention** — rename it and update all references
   in the same task (imports, links, `settings.json` hook paths, `CLAUDE.md`, `README.md`).
3. **Do not introduce** `SCREAMING_SNAKE` or `Title_Case` Markdown outside the exempt list.
4. **Hook scripts** — always `snake_case.sh`, never `kebab-case.sh`.
5. **On /ship** — confirm no new paths violate the convention; fix or flag violations before commit.

---

## Stack Reminders (when `apps/` and `dashboard/` exist)

- Python: `snake_case.py`
- React components: `PascalCase.tsx`
- TypeScript modules/utils: `kebab-case.ts` (all React apps)
- Java types: `PascalCase.java`
- Docker Compose services: kebab-case

Full detail: `docs/tech/file-naming-convention.md`.
