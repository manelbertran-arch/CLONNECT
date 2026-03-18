#!/bin/bash
# Block git commit if any staged .py file has syntax errors

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only intercept git commit commands
if ! echo "$COMMAND" | grep -qE '^\s*git\s+commit'; then
  exit 0
fi

# Get staged .py files
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
STAGED=$(cd "$CWD" && git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$')

if [ -z "$STAGED" ]; then
  exit 0
fi

ERRORS=""
while IFS= read -r FILE; do
  FULL="$CWD/$FILE"
  if [ -f "$FULL" ]; then
    ERR=$(python3 -c "import ast; ast.parse(open('$FULL').read())" 2>&1)
    if [ $? -ne 0 ]; then
      ERRORS="$ERRORS\n❌ $FILE: $ERR"
    fi
  fi
done <<< "$STAGED"

if [ -n "$ERRORS" ]; then
  jq -n --arg reason "Syntax errors in staged .py files:$(echo -e "$ERRORS")" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
else
  exit 0
fi
