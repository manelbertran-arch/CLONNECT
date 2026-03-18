#!/bin/bash
# Anti-regression check: save baseline before changes, compare after
set -e

BASELINE="/tmp/clonnect_smoke_baseline.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
  before)
    echo "📸 Capturing baseline..."
    python3 "$SCRIPT_DIR/smoke_test_endpoints.py" --save-baseline "$BASELINE"
    ;;
  after)
    if [ ! -f "$BASELINE" ]; then
      echo "❌ No baseline found at $BASELINE. Run '$0 before' first."
      exit 1
    fi
    echo "🔍 Running smoke tests and comparing against baseline..."
    python3 "$SCRIPT_DIR/smoke_test_endpoints.py" --compare "$BASELINE"
    ;;
  run)
    echo "🏃 Running smoke tests (no comparison)..."
    python3 "$SCRIPT_DIR/smoke_test_endpoints.py"
    ;;
  *)
    echo "Usage: $0 {before|after|run}"
    echo "  before  — capture baseline (run BEFORE changes)"
    echo "  after   — run tests and compare against baseline"
    echo "  run     — just run smoke tests"
    exit 1
    ;;
esac
