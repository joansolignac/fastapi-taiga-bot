# syntax=docker/dockerfile:1

# --- Builder: resolves and installs dependencies with uv, using uv's own
# managed Python build so the image never depends on the base distro's
# Python version matching the project's `requires-python = ">=3.14"`.
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

COPY .python-version ./
RUN uv python install

# Install dependencies before copying the source, so this (slow) layer is
# only rebuilt when pyproject.toml/uv.lock actually change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

# --- Runtime: no uv, no build toolchain — just the managed Python, the
# venv uv built, and the application code.
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY --from=builder --chown=appuser:appuser /python /python
COPY --from=builder --chown=appuser:appuser /app /app

WORKDIR /app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}"
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=3)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
