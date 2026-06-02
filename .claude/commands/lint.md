# /lint

Run linting and formatting checks across the affected app.

## Steps
1. Identify which app is in focus or ask if unclear
2. Run the appropriate lint command:
   - Python apps: `uv run ruff check .` and `uv run black --check .`
   - Node apps: `pnpm lint` and `pnpm format:check`
   - Java: `./mvnw checkstyle:check`
3. Report any errors or warnings
4. Offer to auto-fix if fixable issues found
