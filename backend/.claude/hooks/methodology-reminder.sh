#!/bin/bash
# UserPromptSubmit hook — injects 4-phase methodology reminder
# when the prompt contains a code-change keyword.
# Fires before every prompt; only emits output for change requests
# to avoid noise on read-only queries (logs, checks, etc.).

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null | tr '[:upper:]' '[:lower:]')

# Only inject for prompts that imply code changes
if ! echo "$PROMPT" | grep -qE 'fix|add|implement|change|update|refactor|create|delete|remove|modify|revert|migrate|deploy|patch'; then
  exit 0
fi

cat << 'EOF'
BEFORE executing any code change, you MUST follow the 4-phase workflow:
1. PLAN — use the planner agent (.claude/agents/planner.md) to identify affected files, dependencies, and blast radius. Log the decision in DECISIONS.md.
2. IMPLEMENT — use the tdd-guide agent (.claude/agents/tdd-guide.md). Syntax-check every modified .py file: python3 -c "import ast; ast.parse(open('FILE').read())"
3. REVIEW — use the code-reviewer agent (.claude/agents/code-reviewer.md) and python-reviewer agent for Python files. Check for regressions.
4. VERIFY — run smoke tests BEFORE and AFTER: python3 tests/smoke_test_endpoints.py. All tests must pass before commit/push.
If you skip any step, explicitly state which step you skipped and why.
EOF
