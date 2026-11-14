FROM ghcr.io/astral-sh/uv:0.8.20@sha256:4e3bde91035d8d11cc1d5e4d1c273b895bb293575b8d23c3e5c6058eed2f1bb9 AS uv
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOME=/tmp

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=bind,from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-install-project
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid 1000 --no-create-home \
        --shell /usr/sbin/nologin app

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY infra/floci_bootstrap.py ./infra/floci_bootstrap.py
COPY infra/rds/us-east-1-bundle.pem ./infra/rds/us-east-1-bundle.pem

USER 1000:1000

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
