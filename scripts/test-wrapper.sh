#!/bin/bash
# Test the vibe-herdr-wrapper in Herdr mode

set -e

echo "=== Testing vibe-herdr-wrapper ==="
echo ""

# Check if herdr is installed
if command -v herdr &>/dev/null; then
  HERDR_BIN=$(which herdr)
  echo "Herdr found at: $HERDR_BIN"
else
  echo "Herdr NOT installed - will simulate with echo"
  HERDR_BIN="echo"
fi

echo ""

# Test 1: Without Herdr environment (should just run vibe)
echo "Test 1: Outside Herdr (no env vars)"
./adapter/vibe-herdr-wrapper --version 2>&1 | head -5

echo ""

# Test 2: With Herdr environment but herdr CLI not available
echo "Test 2: In Herdr mode (with env vars, herdr not installed)"
export HERDR_ENV=1
export HERDR_PANE_ID="test:w1:p1"
export HERDR_BIN_PATH="echo"
export HERDR_SOCKET_PATH="/tmp/herdr.sock"

# Run with programmatic mode to avoid hanging
./adapter/vibe-herdr-wrapper -p "What is 2+2?" --max-turns 1 --output text 2>&1

echo ""
echo "=== Tests Complete ==="
