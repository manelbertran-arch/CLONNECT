#!/bin/bash
# After git push, wait for deploy and run health + RAG checks

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only run after git push to main
if ! echo "$COMMAND" | grep -qE 'git\s+push.*main'; then
  exit 0
fi

echo "⏳ Waiting 30s for Railway deploy..." >&2
sleep 30

# Check 1: HTTP health endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://www.clonnectapp.com/health")
HEALTH_MSG=""

if [ "$HTTP_CODE" = "200" ]; then
  HEALTH_MSG="✅ HTTP health: 200 OK"
else
  HEALTH_MSG="⚠️ HTTP health: HTTP $HTTP_CODE — check Railway logs"
fi

# Check 2: RAG health check (run against production DB via railway)
RAG_MSG=""
if command -v railway &>/dev/null; then
  RAG_OUTPUT=$(railway run python3 scripts/rag_health_check.py 2>&1)
  RAG_EXIT=$?
  RAG_LAST=$(echo "$RAG_OUTPUT" | tail -3)
  if [ "$RAG_EXIT" -eq 0 ]; then
    RAG_MSG="✅ RAG health: OK"
  else
    RAG_MSG="⚠️ RAG health: PROBLEMS\n$RAG_LAST"
  fi
else
  RAG_MSG="⏭️ RAG health: skipped (no railway CLI)"
fi

COMBINED="$HEALTH_MSG\n$RAG_MSG"

jq -n --arg msg "$COMBINED" '{
  hookSpecificOutput: {
    additionalContext: $msg
  }
}'
