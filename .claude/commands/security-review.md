# /security-review

Scan code written in this session for security issues before shipping. Fix everything found.

## Steps
1. Run `git diff` to identify all changed files
2. Scan for secrets and credentials:
   - Hardcoded API keys, passwords, tokens, or connection strings
   - Any value that should be in `.env` but is inline in code
   - `.env` files accidentally staged (`git status`)
3. Scan for injection vulnerabilities:
   - SQL injection — raw string interpolation in queries (use parameterized queries)
   - Command injection — user input passed to shell commands
   - Path traversal — unsanitized file paths from user input
4. Scan for auth and access control gaps:
   - Endpoints missing authentication checks
   - Missing ownership validation (user A accessing user B's data)
   - Dev-only endpoints reachable without a guard
5. Scan for exposed internals:
   - Stack traces or internal paths in API error responses
   - Debug endpoints or verbose logging enabled in production paths
   - CORS configured to allow all origins (`*`) with credentials
6. Fix every issue found — do not report without fixing
7. Summarize what was found and fixed; explicitly state "nothing found" if clean
