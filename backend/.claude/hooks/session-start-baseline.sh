#!/bin/bash
# On session start, capture smoke test baseline automatically
BASELINE="/tmp/clonnect_smoke_baseline.json"
CWD=$(cat | jq -r '.cwd // "."')

# Only run if we're in the Clonnect backend directory
if echo "$CWD" | grep -q "Clonnect"; then
  cd "$CWD" 2>/dev/null || cd ~/Clonnect/backend
  if [ -f "tests/smoke_test_endpoints.py" ]; then
    python3 tests/smoke_test_endpoints.py --save-baseline "$BASELINE" >/dev/null 2>&1 &
    jq -n '{
      hookSpecificOutput: {
        additionalContext: "📸 Smoke test baseline captured at /tmp/clonnect_smoke_baseline.json"
      }
    }'
  fi
else
  exit 0
fi
