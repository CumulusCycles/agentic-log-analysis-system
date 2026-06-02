# /build

Run a production build for the current app and report any errors.

## Steps
1. Identify which app is in focus or ask if unclear
2. Run the appropriate build command:
   - Python apps: `uv sync && uv run mypy .` — FastAPI is interpreted, so dependency resolution + type-check stands in as the build gate
   - Node/React apps: `pnpm build`
   - Java: `./mvnw package -DskipTests`
   - Optional container build for any service: `docker compose build <service>` — catches Dockerfile and image-install failures the per-stack commands above will miss
3. Report success or list all build errors
4. If successful, confirm ready to /test then /ship
