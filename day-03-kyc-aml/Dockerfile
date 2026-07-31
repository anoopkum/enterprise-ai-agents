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

# PII-FREE regulatory KB subset only (aml_rules + kyc_guidelines, synthetic rules/
# guidelines with no personal data). This is what the startup seed embeds into the
# vector index. Real customer data / documents are NEVER copied here.
COPY --chown=appuser:appgroup data/sample_synthetic/ ./data/
ENV DATA_DIR=/app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info", "--access-log"]
