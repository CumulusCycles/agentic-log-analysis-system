# File Naming Convention

All files in this repository must follow the conventions below. This document is the
source of truth; Claude Code enforces it via `.claude/rules/file-naming.md`.

---

## General Principles

1. **Lowercase only** — no `CamelCase`, `Title_Case`, or `SCREAMING_SNAKE` in filenames
   unless listed under [Exempt names](#exempt-names).
2. **kebab-case by default** — separate words with hyphens (`user-profile.tsx`,
   `logging-strategy.md`).
3. **No spaces or special characters** — use ASCII letters, digits, hyphens, underscores,
   and dots only where a pattern below allows.
4. **One convention per layer** — do not mix kebab-case and snake_case in the same
   directory category.
5. **Apply on create** — name new files correctly the first time. If you rename a file
   for convention compliance, update all references in the same change.

---

## Exempt Names

These fixed names are intentional and must not be renamed:

| Name | Location | Reason |
| --- | --- | --- |
| `README.md` | Any directory | Universal convention |
| `LICENSE` | Repo root | Universal convention |
| `CLAUDE.md` | Repo root | Claude Code project memory |
| `PLAN.md` | Repo root | Build task list (referenced across tooling) |
| `CLAUDE_RESOURCES.md` | Repo root | Claude Code resource index |
| `SKILL.md` | `.claude/skills/*/` | Required by Claude Code |
| `.env.example` | Repo root | Standard env template name |
| `.gitignore` | Repo root | Git convention |
| `.gitattributes` | Repo root | Git convention |
| `.mcp.json` | Repo root | Claude Code MCP config |
| `settings.json` | `.claude/` | Claude Code settings |
| `settings.local.json` | `.claude/` | Claude Code local settings |

---

## By File Type

### Markdown documentation (`docs/`, root meta docs)

| Rule | Example |
| --- | --- |
| kebab-case | `development-workflow.md`, `project-brief.md` |
| ADRs: `ADR-NNN-kebab-slug.md` | `ADR-003-logging-strategy.md` |
| Subdirs: kebab-case | `docs/architecture/system-overview.md` |

### Claude Code — commands (`.claude/commands/`)

| Rule | Example |
| --- | --- |
| kebab-case `.md` | `security-review.md` → `/security-review` |
| Name = filename without extension | `ship.md` → `/ship` |

### Claude Code — agents (`.claude/agents/`)

| Rule | Example |
| --- | --- |
| kebab-case `.md` | `docker-agent.md`, `python-agent.md` |
| `name` in frontmatter: lowercase hyphens | `name: git-agent` |

### Claude Code — rules (`.claude/rules/`)

| Rule | Example |
| --- | --- |
| kebab-case `.md` | `file-naming.md`, `workflow.md` |

### Claude Code — skills (`.claude/skills/`)

| Rule | Example |
| --- | --- |
| Directory: kebab-case | `docker-validate/`, `log-analysis/` |
| Entry file: `SKILL.md` (fixed) | `.claude/skills/log-analysis/SKILL.md` |

### Claude Code — hook scripts (`.claude/hooks/`)

| Rule | Example |
| --- | --- |
| snake_case `.sh` | `.claude/hooks/pre_bash_guard.sh`, `.claude/hooks/post_format.sh` |
| Pattern: `{event}_{purpose}.sh` | `.claude/hooks/post_compose_validate.sh` |

Hook scripts are referenced from `.claude/settings.json`; update paths when renaming.

### Application source (future: `apps/`, `dashboard/`)

Follow the toolchain default for each stack:

| Stack | Files | Tests |
| --- | --- | --- |
| Python (Shared Data API, FNOL, dashboard backend) | `snake_case.py` | `test_snake_case.py` |
| Node / React (FNOL frontend, Customer Portal, Agent Portal frontend, dashboard frontend) | Components: `PascalCase.tsx`; modules/utils: `kebab-case.ts` (all React apps — see `apps.md`) | `*.test.ts` / `*.spec.ts` |
| Java (Agent Portal backend) | `PascalCase.java` per type | `*Test.java` |
| Config | kebab-case or tool default | `docker-compose.yml`, `pyproject.toml` |

### Docker & infrastructure

| Rule | Example |
| --- | --- |
| kebab-case service names in Compose | `shared-data-api`, `log-dashboard` |
| Standard Compose filename | `docker-compose.yml` |

---

## Anti-patterns

Do **not** use:

- Wrong Markdown case: `DevelopmentWorkflow.md`, `ProjectBrief.md` (use kebab-case unless [exempt](#exempt-names))
- Wrong hook script case: `pre-bash-guard.sh` under `.claude/hooks/` (use `snake_case.sh`, e.g. `pre_bash_guard.sh`)
- Wrong skill layout: `my-skill/skill.md` (use `my-skill/SKILL.md`)
- Version suffixes in names (`plan-v2-final.md`)
- Spaces in filenames (`project brief.md`)

---

## Compliance Checklist

Before opening a PR (or when running `/ship`):

- [ ] New files match the rules for their directory and stack
- [ ] No new `SCREAMING_SNAKE` or `Title_Case` Markdown outside [exempt names](#exempt-names)
- [ ] Claude Code paths (`commands`, `agents`, `rules`, `skills`, `hooks`) follow tables above
- [ ] References updated if any file was renamed

---

## References

- [Claude Code skills & commands](https://code.claude.com/docs/en/skills)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Google Shell Style Guide — source filenames](https://google.github.io/styleguide/shellguide.html)
- [ADR naming (joelparkerhenderson / community patterns)](https://github.com/joelparkerhenderson/architecture_decision_record)
