#!/bin/bash
# Stop hook (command): Auto-run smoke tests when Claude finishes and .py files were modified.
# Blocks Claude from stopping if smoke tests fail.

INPUT=$(cat)

# Prevent infinite loops — if Stop hook already triggered a continuation, allow
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
cd "$CWD" 2>/dev/null || exit 0

# Check if any .py files have uncommitted changes (staged or unstaged)
PY_CHANGED=false
if git diff --name-only 2>/dev/null | grep -qE '\.py$'; then
  PY_CHANGED=true
fi
if git diff --cached --name-only 2>/dev/null | grep -qE '\.py$'; then
  PY_CHANGED=true
fi

if [ "$PY_CHANGED" = "false" ]; then
  exit 0  # No .py changes — skip tests
fi

# Run smoke tests
if [ ! -f "tests/smoke_test_endpoints.py" ]; then
  exit 0  # No smoke test file — skip
fi

RESULT=$(python3 tests/smoke_test_endpoints.py 2>&1)
LAST_LINES=$(echo "$RESULT" | tail -5)

# Check if tests passed
if echo "$RESULT" | grep -q "passed"; then
  echo "[AUTO-SMOKE] $LAST_LINES"
  exit 0
fi

# Tests failed — block
jq -n --arg reason "[AUTO-SMOKE] Smoke tests FAILED. Fix before finishing.\n$LAST_LINES" '{
  decision: "block",
  reason: $reason
}'
