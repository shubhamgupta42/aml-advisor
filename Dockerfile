# AML Advisor — single-stage Docker build
#
# Builds a container that runs the FastAPI service on port 8000.
# The vector store is built INSIDE the image at build time (deterministic, fast cold-start).
#
# Build:   docker build -t aml-advisor:latest .
# Run:     docker run --rm -p 8000:8000 --env-file .env aml-advisor:latest
# Health:  curl http://localhost:8000/healthz
#
# Notes:
# - Python 3.12 (ML stack does not yet support 3.13/3.14).
# - The image bundles synthetic MDDs only; no proprietary content.
# - Models (bge-small embeddings, bge-reranker-base) are downloaded at first call;
#   for production we'd pre-warm them at build time to make cold-start deterministic.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache

WORKDIR /app

# System deps. build-essential is required for sentence-transformers wheels on slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first to leverage layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source.
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Build the vector store at image build time so the first /retrieve call is fast.
RUN python scripts/ingest_mdds.py || (echo "ingest failed — continuing; will rebuild at runtime" && true)

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Bind to 0.0.0.0 so the container is reachable from the host.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
