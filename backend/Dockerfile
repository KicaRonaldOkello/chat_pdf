# Build: docker build -f backend/Dockerfile -t chat-pdf-api ./backend
FROM python:3.12-slim-bookworm

# ── system deps for unstructured PDF parsing ────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr ghostscript \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ── uv package manager ──────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── dependencies (cached layer) ─────────────────────────────────────────
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ── application code ────────────────────────────────────────────────────
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8000

# Run migrations before starting
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

ENTRYPOINT ["/app/entrypoint.sh"]
