# Stage 1 — React build
FROM node:22-alpine AS frontend

RUN corepack enable
WORKDIR /build

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY frontend ./
RUN pnpm run build


# Stage 2 — Python deps via uv
FROM python:3.12-slim AS pybuilder

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev


# Stage 3 — runtime
FROM python:3.12-slim AS runtime

WORKDIR /app
RUN useradd -u 1000 -m app \
    && chown -R app:app /app

COPY --from=pybuilder --chown=app:app /app /app
COPY --from=frontend  --chown=app:app /build/dist /app/frontend/dist

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 4000

CMD ["uvicorn", "log_dashboard.main:app", "--host", "0.0.0.0", "--port", "4000"]
