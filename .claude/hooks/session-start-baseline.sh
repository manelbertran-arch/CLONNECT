#!/bin/bash
# Session start hook — runs smoke tests as baseline
# Output goes to Claude's context so it knows the current state.

PROJ="${CLAUDE_PROJECT_DIR:-/Users/manelbertranluque/Clonnect/backend}"
SMOKE="$PROJ/tests/smoke_test_endpoints.py"

if [ ! -f "$SMOKE" ]; then
  echo "Smoke test script not found at $SMOKE"
  exit 0
fi

RESULT=$(cd "$PROJ" && python3 "$SMOKE" 2>&1)
PASSED=$(echo "$RESULT" | grep -oE '[0-9]+/[0-9]+ passed' | head -1)

# Save baseline to tmp for later comparison
echo "$RESULT" > /tmp/clonnect_baseline.txt
echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"result\":\"$PASSED\"}" > /tmp/clonnect_baseline.json

if echo "$RESULT" | grep -q "FAIL"; then
  echo "SESSION BASELINE: Smoke tests have failures ($PASSED). Check before pushing."
else
  echo "SESSION BASELINE: Smoke tests $PASSED. Production is healthy."
fi

exit 0
