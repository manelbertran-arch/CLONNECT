#!/bin/bash

# Clonnect Creators - Run Script

# Cargar variables de entorno
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

case "$1" in
    api)
        echo "🚀 Iniciando API..."
        uvicorn api.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} --reload
        ;;
    dashboard)
        echo "📊 Iniciando Dashboard..."
        streamlit run dashboard/app.py --server.port ${DASHBOARD_PORT:-8501}
        ;;
    both)
        echo "🚀 Iniciando API y Dashboard..."
        uvicorn api.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} &
        sleep 2
        streamlit run dashboard/app.py --server.port ${DASHBOARD_PORT:-8501}
        ;;
    test)
        echo "🧪 Ejecutando tests..."
        pytest tests/ -v
        ;;
    *)
        echo "Uso: ./scripts/run.sh [api|dashboard|both|test]"
        echo ""
        echo "  api       - Inicia la API FastAPI"
        echo "  dashboard - Inicia el dashboard Streamlit"
        echo "  both      - Inicia ambos"
        echo "  test      - Ejecuta los tests"
        exit 1
        ;;
esac
