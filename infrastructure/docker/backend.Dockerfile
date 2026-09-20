# syntax=docker/dockerfile:1.7
FROM python:3.12-alpine@sha256:c4634f578a412db396771b61b064c6e546c9d6414c7fb5b1b05d5871f1885f7b

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend/src:/app

RUN apk add --no-cache ca-certificates curl tini \
    && addgroup -S -g 10001 boa \
    && adduser -S -D -H -u 10001 -G boa -s /sbin/nologin boa

WORKDIR /app
COPY backend/ /app/backend/
COPY database/ /app/database/
COPY infrastructure/docker/backend-entrypoint.sh /opt/boa/backend-entrypoint.sh
COPY infrastructure/docker/healthcheck.py /opt/boa/healthcheck.py

# Accepte un backend géré par pyproject, requirements global ou requirements par service.
RUN set -eux; \
    python -m pip install 'fastapi>=0.115,<1' 'uvicorn[standard]>=0.30,<1' 'httpx>=0.27,<1' 'psycopg[binary]>=3.2,<4' 'sqlalchemy>=2,<3' 'alembic>=1.13,<2' 'prometheus-client>=0.20,<1'; \
    if [ -f /app/backend/pyproject.toml ]; then python -m pip install --no-cache-dir /app/backend; \
    elif [ -f /app/backend/requirements.txt ]; then python -m pip install --no-cache-dir -r /app/backend/requirements.txt; \
    fi; \
    find /app/backend/services -mindepth 2 -maxdepth 2 -name requirements.txt -print 2>/dev/null \
      | sort \
      | while read -r req; do python -m pip install --no-cache-dir -r "$req"; done; \
    chmod 0555 /opt/boa/backend-entrypoint.sh /opt/boa/healthcheck.py; \
    chown -R boa:boa /app

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/sbin/tini", "--", "/opt/boa/backend-entrypoint.sh"]
