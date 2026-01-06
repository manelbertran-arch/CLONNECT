#!/bin/bash
set -e

PORT=${PORT:-8000}

# Fix permissions for mounted volume (runs as root before switching user)
if [ -d /app/data ]; then
    echo "Fixing data directory permissions..."
    mkdir -p /app/data/followers /app/data/products /app/data/creators /app/data/analytics \
             /app/data/nurturing /app/data/gdpr /app/data/payments /app/data/calendar /app/data/escalations \
             /app/data/content_index /app/data/tone_profiles

    # Copy initial data from image if not already in volume
    # This handles the case where Railway mounts a persistent volume
    if [ -d /app/initial_data ]; then
        echo "Syncing initial data to volume..."

        # Copy content_index (creator citations) - always sync new files
        if [ -d /app/initial_data/content_index ]; then
            cp -r /app/initial_data/content_index/* /app/data/content_index/ 2>/dev/null || true
            echo "  - Synced content_index"
        fi

        # Copy tone_profiles (creator voice) - always sync new files
        if [ -d /app/initial_data/tone_profiles ]; then
            cp -r /app/initial_data/tone_profiles/* /app/data/tone_profiles/ 2>/dev/null || true
            echo "  - Synced tone_profiles"
        fi

        # Copy creator configs - always sync new files
        if [ -d /app/initial_data/creators ]; then
            cp -r /app/initial_data/creators/* /app/data/creators/ 2>/dev/null || true
            echo "  - Synced creators"
        fi

        # Copy products - always sync new files
        if [ -d /app/initial_data/products ]; then
            cp -r /app/initial_data/products/* /app/data/products/ 2>/dev/null || true
            echo "  - Synced products"
        fi
    fi

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
