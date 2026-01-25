# Clonnect Creators - Production Dockerfile
# Multi-stage build for optimized image size

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements-lite.txt .

# Force rebuild - change this value to invalidate pip cache
ENV FORCE_REBUILD="2026-01-24-pytorch-cpu"

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-lite.txt

# Stage 1.5: Pre-download ML models (cached in image)
FROM builder as model-downloader
ENV PATH="/opt/venv/bin:$PATH"
# Pre-download sentence-transformers models to avoid runtime download
# This adds ~200MB to image but saves 3-5 minutes on cold start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')"

# Stage 2: Runtime
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd -r clonnect && useradd -r -g clonnect clonnect

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-downloaded models to app directory (accessible by clonnect user)
COPY --from=model-downloader /root/.cache/huggingface /app/.cache/huggingface
COPY --from=model-downloader /root/.cache/torch /app/.cache/torch

# Set cache directories for HuggingFace and Torch (so models are found at runtime)
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface

# Copy application code
COPY --chown=clonnect:clonnect . .

# Copy and make start script executable
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh

# Create data directories and fix model cache permissions
RUN mkdir -p data/followers data/products data/creators data/analytics \
    data/nurturing data/gdpr data/payments data/calendar data/escalations \
    data/content_index data/tone_profiles \
    && chown -R clonnect:clonnect data \
    && chown -R clonnect:clonnect /app/.cache

# Copy initial data that should persist (content_index, tone_profiles, etc.)
# These will be copied to /app/data at startup if not already there
RUN mkdir -p /app/initial_data && \
    cp -r data/content_index /app/initial_data/ 2>/dev/null || true && \
    cp -r data/tone_profiles /app/initial_data/ 2>/dev/null || true && \
    cp -r data/creators /app/initial_data/ 2>/dev/null || true && \
    cp -r data/products /app/initial_data/ 2>/dev/null || true && \
    cp -r data/nurturing /app/initial_data/ 2>/dev/null || true

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port (default, Railway will override with PORT env var)
EXPOSE 8000

# Run the application via start script
CMD ["/app/scripts/start.sh"]
