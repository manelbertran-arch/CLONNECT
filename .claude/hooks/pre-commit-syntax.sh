#!/bin/bash
# Pre-commit syntax check hook for Claude Code
# Runs ast.parse on all staged .py files before allowing git commit.
# Exit 0 = allow, Exit 2 = block with message.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only process git commit commands
if [[ ! "$COMMAND" =~ git[[:space:]]+commit ]]; then
  exit 0
fi

# Get staged .py files
STAGED=$(cd "$CLAUDE_PROJECT_DIR" 2>/dev/null && git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$')

if [ -z "$STAGED" ]; then
  exit 0
fi

ERRORS=""
COUNT=0
FAIL=0

for FILE in $STAGED; do
  FULL="$CLAUDE_PROJECT_DIR/$FILE"
  COUNT=$((COUNT + 1))
  if [ -f "$FULL" ]; then
    ERR=$(python3 -c "import ast; ast.parse(open('$FULL').read())" 2>&1)
    if [ $? -ne 0 ]; then
      FAIL=$((FAIL + 1))
      ERRORS="$ERRORS\n  FAIL: $FILE — $ERR"
    fi
  fi
done

if [ $FAIL -gt 0 ]; then
  echo "Syntax check FAILED: $FAIL/$COUNT files have errors.$ERRORS" >&2
  echo "Fix syntax errors before committing." >&2
  exit 2
fi

echo "Syntax check passed: $COUNT .py files OK." >&2
exit 0
