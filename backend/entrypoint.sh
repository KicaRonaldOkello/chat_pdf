#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Container entrypoint.  Migrations are run by the deploy workflow via
# `docker exec chat_pdf_api alembic upgrade head` after the container starts.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "==> Starting uvicorn on port ${APP_PORT:-8000} …"
exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}"
