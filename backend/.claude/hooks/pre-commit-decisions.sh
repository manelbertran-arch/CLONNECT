#!/bin/bash
# PreToolUse hook: Block git commit/push if .py files are staged but DECISIONS.md is not.
# Enforces the rule: every code change must have a documented decision.

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Only intercept git commit or git push commands
if ! echo "$CMD" | grep -qE '^\s*git\s+(commit|push)'; then
  exit 0
fi

cd "$CWD" 2>/dev/null || exit 0

# Check if any .py files are staged
if ! git diff --cached --name-only 2>/dev/null | grep -qE '\.py$'; then
  exit 0  # No .py files staged — allow
fi

# Check if DECISIONS.md is also staged
if git diff --cached --name-only 2>/dev/null | grep -q 'DECISIONS.md'; then
  exit 0  # DECISIONS.md is staged — allow
fi

# .py files staged without DECISIONS.md → block
jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "BLOCKED: .py files are staged but DECISIONS.md was not updated. Add a decision entry explaining what changed and why, then stage it."
  }
}'
