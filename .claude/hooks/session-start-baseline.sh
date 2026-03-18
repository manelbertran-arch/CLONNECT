#!/bin/bash
# Session start hook — runs smoke tests as baseline
# Output goes to Claude's context so it knows the current state.

BASE="${CLAUDE_PROJECT_DIR:-/Users/manelbertranluque/Clonnect}"
# Smoke tests live in backend/tests/ — handle both repo root and backend dir
if [ -f "$BASE/tests/smoke_test_endpoints.py" ]; then
  PROJ="$BASE"
  SMOKE="$BASE/tests/smoke_test_endpoints.py"
elif [ -f "$BASE/backend/tests/smoke_test_endpoints.py" ]; then
  PROJ="$BASE/backend"
  SMOKE="$BASE/backend/tests/smoke_test_endpoints.py"
else
  echo "Smoke test script not found"
  exit 0
fi

RESULT=$(cd "$PROJ" && python3 "$SMOKE" 2>&1)
PASSED=$(echo "$RESULT" | grep -oE '[0-9]+/[0-9]+ passed' | head -1)

# Save baseline to tmp for later comparison
echo "$RESULT" > /tmp/clonnect_baseline.txt
echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"result\":\"$PASSED\"}" > /tmp/clonnect_baseline.json

if [ -z "$PASSED" ]; then
  echo "SESSION BASELINE: Could not parse smoke test results. Run manually."
elif echo "$RESULT" | grep -q "FAIL"; then
  echo "SESSION BASELINE: Smoke tests have failures ($PASSED). Check before pushing."
else
  echo "SESSION BASELINE: Smoke tests $PASSED. Production is healthy."
fi

exit 0
