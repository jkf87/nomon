#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
LOG_FILE="$REPO_ROOT/verification/logs/auto-test.log"

mkdir -p "$(dirname "$LOG_FILE")"

{
    echo "=== Nomon OpenClaw Auto-Test ==="
    echo "Date: $(date)"
    echo ""

    TEMP_HOME=$(mktemp -d)
    trap "rm -rf $TEMP_HOME" EXIT

    export HOME="$TEMP_HOME"
    export OPENCLAW_SKILLS_DIR="$TEMP_HOME/.openclaw/skills"
    export OPENCLAW_MCP_CONFIG="$TEMP_HOME/.openclaw/mcp/claude-mcp-config.json"
    export NOMON_CONFIG="$TEMP_HOME/.nomon/config.yaml"

    mkdir -p "$(dirname "$OPENCLAW_MCP_CONFIG")"
    echo '{"mcpServers": {}}' > "$OPENCLAW_MCP_CONFIG"

    echo "STEP 1: Install"
    cd "$REPO_ROOT"
    if python3 -m openclaw_nomon install > /dev/null 2>&1; then
        echo "✓ Install succeeded"
    else
        echo "✗ Install failed"
        exit 1
    fi

    echo "STEP 2: Verify installed files"
    if [ ! -f "$OPENCLAW_SKILLS_DIR/nomon/SKILL.md" ]; then
        echo "✗ SKILL.md not found"
        exit 1
    fi
    echo "✓ SKILL.md present"

    if [ ! -f "$NOMON_CONFIG" ]; then
        echo "✗ nomon config not found"
        exit 1
    fi
    echo "✓ nomon config present"

    if grep -q "nomon" "$OPENCLAW_MCP_CONFIG"; then
        echo "✓ MCP entry present"
    else
        echo "✗ MCP entry not found"
        exit 1
    fi

    echo "STEP 3: Run doctor"
    if python3 -m openclaw_nomon doctor > /dev/null 2>&1; then
        echo "✓ Doctor checks passed"
    else
        echo "✗ Doctor failed"
        exit 1
    fi

    echo "STEP 4: Uninstall"
    if python3 -m openclaw_nomon uninstall > /dev/null 2>&1; then
        echo "✓ Uninstall succeeded"
    else
        echo "✗ Uninstall failed"
        exit 1
    fi

    if grep -q '"nomon"' "$OPENCLAW_MCP_CONFIG"; then
        echo "✗ MCP entry still present after uninstall"
        exit 1
    fi
    echo "✓ MCP entry removed"
    
    echo ""
    echo "=== All auto-tests passed ==="
    exit 0
    
} | tee "$LOG_FILE"

exit ${PIPESTATUS[0]}
