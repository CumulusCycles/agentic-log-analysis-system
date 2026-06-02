# /self-review

Review code just written against current best practices, fix any issues found, then report what changed.
Run this after writing code and before running /test.

## Steps
1. Run `git diff` to see exactly what was written
2. Identify the languages, frameworks, and libraries in the diff
3. For each, query the appropriate MCP server for current best practices:
   - Dashboard backend code (LangGraph, LangChain, Chroma, LangSmith, FastAPI) → **docs-langchain**
   - All other code (React, Express, Spring Boot, SQLAlchemy, Mongoose, Vite, etc.) → **context7**
4. Review the diff against those best practices, checking for:
   - Incorrect or deprecated API usage
   - Missing error handling at system boundaries
   - Security issues (injection, hardcoded secrets, exposed internals)
   - Type safety gaps
   - Naming or structure inconsistencies with the rest of the file
   - Anything that would fail the project's lint or build checks
5. Fix every issue found — do not report without fixing
6. Run `git diff` again and summarize what was changed and why
7. If nothing needed fixing, say so explicitly
