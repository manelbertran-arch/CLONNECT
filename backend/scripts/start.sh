#!/bin/bash
set -e

echo "=========================================="
echo "START.SH EXECUTING - $(date)"
echo "=========================================="

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
            echo "  - Found initial_data/content_index, contents:"
            ls -la /app/initial_data/content_index/
            cp -rv /app/initial_data/content_index/* /app/data/content_index/ 2>&1 || echo "  - cp failed: $?"
            echo "  - After sync, content_index contains:"
            ls -la /app/data/content_index/
        else
            echo "  - WARNING: /app/initial_data/content_index does not exist!"
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

        # Copy nurturing configs - FORCE sync to update sequence configs
        # Use -rf to OVERWRITE existing files (volume may have old configs)
        if [ -d /app/initial_data/nurturing ]; then
            cp -rf /app/initial_data/nurturing/* /app/data/nurturing/ 2>/dev/null || true
            echo "  - Synced nurturing configs (force overwrite)"
            echo "  - Nurturing files after sync:"
            ls -la /app/data/nurturing/
            # Debug: show actual config content for stefano_auto
            if [ -f /app/data/nurturing/stefano_auto_sequences.json ]; then
                echo "  - stefano_auto_sequences.json content:"
                cat /app/data/nurturing/stefano_auto_sequences.json
            fi
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
