#!/bin/bash
set -e

PORT=${PORT:-8000}

# Fix permissions for mounted volume (runs as root before switching user)
if [ -d /app/data ]; then
    echo "Fixing data directory permissions..."
    mkdir -p /app/data/followers /app/data/products /app/data/creators /app/data/analytics \
             /app/data/nurturing /app/data/gdpr /app/data/payments /app/data/calendar /app/data/escalations
    chown -R clonnect:clonnect /app/data 2>/dev/null || true
    chmod -R 755 /app/data 2>/dev/null || true
fi

echo "Starting Clonnect Creators API on port $PORT"

# If running as root, switch to clonnect user
if [ "$(id -u)" = "0" ]; then
    exec su -s /bin/bash clonnect -c "uvicorn api.main:app --host 0.0.0.0 --port $PORT"
else
    exec uvicorn api.main:app --host 0.0.0.0 --port $PORT
fi
