#!/bin/bash
DASHBOARD_PORT=${DASHBOARD_PORT:-8501}
echo "Starting Clonnect Admin Dashboard on port $DASHBOARD_PORT"
exec streamlit run admin/dashboard.py --server.port $DASHBOARD_PORT --server.address 0.0.0.0 --server.headless true
