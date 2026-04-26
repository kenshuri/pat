FROM python:3.13-slim

WORKDIR /app

# Copie uv depuis son image officielle
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Installe les dépendances en premier (layer cache Docker)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Copie le code source
COPY . .
