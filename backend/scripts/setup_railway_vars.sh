#!/bin/bash
# Railway environment variables for Scout production deployment
# Review and run these commands manually:

echo "=== Scout Production Variables for Railway ==="
echo ""
echo "# Run these in the Railway project directory:"
echo ""

# Read keys from local .env
DEEPINFRA_KEY=$(grep DEEPINFRA_API_KEY .env | cut -d= -f2)
GROQ_KEY=$(grep GROQ_API_KEY .env | cut -d= -f2)

echo "railway variables set SCOUT_MODEL=meta-llama/Llama-4-Scout-17B-16E-Instruct"
echo "railway variables set SCOUT_PROVIDER=deepinfra"
echo "railway variables set USE_SCOUT_MODEL=true"
echo "railway variables set DEEPINFRA_API_KEY=$DEEPINFRA_KEY"
echo "railway variables set GROQ_API_KEY=$GROQ_KEY"
echo ""
echo "# Verify with:"
echo "railway variables | grep -E 'SCOUT|DEEPINFRA|GROQ'"
