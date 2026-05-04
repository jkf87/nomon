#!/bin/bash
set -e

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." && pwd )"
LOGS_DIR="$REPO_ROOT/verification/logs"

mkdir -p "$LOGS_DIR"

echo "=== Ouroboros Verification Gate ==="
echo "Target: All 5 dims >= 95%"
echo ""

# Run auto-test
bash "$REPO_ROOT/verification/auto/run_install_test.sh" > "$LOGS_DIR/auto-test.log" 2>&1 || true

echo "✓ Auto-test run"
echo "Next: Dispatch 5 reviewers, collect scores"
