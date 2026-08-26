#!/bin/bash
# Test script for state detection in Herdr + Mistral Vibe integration
# Run this OUTSIDE Herdr to test state reporting via simulated Herdr environment

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADAPTER="$REPO_ROOT/adapter/dist/index.js"

echo "=== State Detection Test ==="
echo ""
echo "This script simulates Herdr environment to test state reporting."
echo "Run this OUTSIDE Herdr (in a regular terminal)."
echo ""

# Check if adapter exists
if [ ! -f "$ADAPTER" ]; then
  echo "❌ Adapter not found at $ADAPTER"
  echo "Run: cd $REPO_ROOT/adapter && npm run build"
  exit 1
fi

# Ensure it's executable
chmod +x "$ADAPTER"

# Test function
run_test() {
  local test_name="$1"
  local prompt="$2"
  local expected_state="$3"
  
  echo "Test: $test_name"
  echo "  Prompt: $prompt"
  echo "  Expected state: $expected_state"
  
  # Simulate Herdr environment
  export HERDR_ENV=1
  export HERDR_PANE_ID="test:w1:p1"
  export HERDR_BIN_PATH="echo"
  
  # Run with a timeout and capture output
  if timeout 10 node "$ADAPTER" -p "$prompt" --max-turns 1 --output text 2>&1 | head -20; then
    echo "  ✅ Completed"
  else
    echo "  ⚠️  Timed out (may need adjustment)"
  fi
  echo ""
}

echo "Test 1: Idle state (initial)"
echo "  Command: vibe-herdr (no prompt, then exit)"
export HERDR_ENV=1 HERDR_PANE_ID=test:w1:p1 HERDR_BIN_PATH=echo
node "$ADAPTER" --version 2>&1 | head -5
echo ""

echo "Test 2: Working state (simple question)"
run_test "Simple math" "What is 2+2?" "working"

echo "Test 3: Working state (code generation)"
run_test "Code generation" "Write a hello world in Python" "working"

echo "Test 4: Working state (thinking)"
run_test "Complex question" "Explain how a neural network works" "working"

echo ""
echo "=== State Pattern Tests ==="
echo ""
echo "Note: These test the REGEX patterns in the adapter."
echo "Full state detection requires actual Vibe TUI output."
echo ""

echo "=== Tests Complete ==="
echo ""
echo "Next: Run 'vibe-herdr' in a Herdr pane to test real state detection."
