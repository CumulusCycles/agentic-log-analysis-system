FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

WORKDIR /app
RUN useradd -u 1000 -m app \
    && mkdir -p /app/logs \
    && chown -R app:app /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

CMD ["uvicorn", "shared_data_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
