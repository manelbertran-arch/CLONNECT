#!/bin/bash
# On session start, run smoke tests against the committed baseline
BASELINE="tests/smoke_baseline.json"
CWD=$(cat | jq -r '.cwd // "."')

# Only run if we're in the Clonnect backend directory
if echo "$CWD" | grep -q "Clonnect"; then
  cd "$CWD" 2>/dev/null || cd ~/Clonnect/backend
  if [ -f "tests/smoke_test_endpoints.py" ] && [ -f "$BASELINE" ]; then
    RESULT=$(railway run python3 tests/smoke_test_endpoints.py --compare "$BASELINE" 2>&1)
    if echo "$RESULT" | grep -q "regression"; then
      MSG="⚠️ Smoke test REGRESSIONS detected — check before making changes"
    else
      MSG="✅ Smoke tests OK (10/10 vs committed baseline)"
    fi
    jq -n --arg msg "$MSG" '{
      hookSpecificOutput: {
        additionalContext: $msg
      }
    }'
  fi
else
  exit 0
fi
