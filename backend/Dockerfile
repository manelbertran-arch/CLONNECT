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

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-lite.txt

# Stage 2: Runtime
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd -r clonnect && useradd -r -g clonnect clonnect

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=clonnect:clonnect . .

# Copy and make start script executable
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh

# Create data directories
RUN mkdir -p data/followers data/products data/creators data/analytics \
    data/nurturing data/gdpr data/payments data/calendar data/escalations \
    && chown -R clonnect:clonnect data

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
#USER clonnect  # Removed - start.sh handles user switch

# Expose port (default, Railway will override with PORT env var)
EXPOSE 8000

# Run the application via start script
CMD ["/app/scripts/start.sh"]
# Force rebuild viernes, 19 de diciembre de 2025, 17:50:14 CET
