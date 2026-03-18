#!/bin/bash
# After git push, wait for deploy and run health check

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only run after git push to main
if ! echo "$COMMAND" | grep -qE 'git\s+push.*main'; then
  exit 0
fi

echo "⏳ Waiting 30s for Railway deploy..." >&2
sleep 30

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://www.clonnectapp.com/health")

if [ "$HTTP_CODE" = "200" ]; then
  jq -n '{
    hookSpecificOutput: {
      additionalContext: "✅ Health check passed (HTTP 200) after deploy"
    }
  }'
else
  jq -n --arg msg "⚠️ Health check returned HTTP $HTTP_CODE after deploy — check Railway logs" '{
    hookSpecificOutput: {
      additionalContext: $msg
    }
  }'
fi
