#!/bin/bash
# Post-push health check hook for Claude Code
# After git push to main, waits then checks production health.
# Non-blocking — reports result but doesn't prevent push.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only process git push commands targeting main
if [[ ! "$COMMAND" =~ git[[:space:]]+push ]]; then
  exit 0
fi

if [[ ! "$COMMAND" =~ main ]]; then
  exit 0
fi

echo "Push to main detected. Health check will run after deploy..." >&2

# Wait for Railway to pick up the deploy
sleep 30

# Check health
HEALTH=$(curl -s --max-time 10 "https://www.clonnectapp.com/health" 2>/dev/null)
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)

if [ "$STATUS" = "healthy" ]; then
  echo "Production health check: HEALTHY" >&2
else
  echo "WARNING: Production health check returned '$STATUS'. Check Railway logs." >&2
fi

exit 0
