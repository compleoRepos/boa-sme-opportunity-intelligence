#!/usr/bin/env sh
set -eu

: "${APP_MODULE:?APP_MODULE must identify the FastAPI application, for example services.customer.app.main:app}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8080}"

exec python -m uvicorn "$APP_MODULE" \
  --host "$HOST" \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" \
  --no-server-header
