FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Cyrillic font for PDF export of the смета
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN uv sync --no-dev
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "maxicalc.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
