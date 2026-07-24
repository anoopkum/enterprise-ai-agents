FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── dependency layer ──────────────────────────────────────────────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── final stage ───────────────────────────────────────────────────────────────
FROM deps AS final

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Source only. Real KYC documents (DATA_DIR) are NEVER baked into the image — they
# stay on a mounted volume / external store; regulatory KB is seeded at startup.
COPY --chown=appuser:appgroup src/ ./src/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info", "--access-log"]
