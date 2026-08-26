#!/bin/bash
# Test the Node.js adapter

set -e

echo "=== Testing Node.js Adapter ==="
echo ""

# Check if node-pty installed correctly
cd /Users/rtuerlings/Coding/herdr-vibe-integration/adapter

echo "Test 1: Check Node.js adapter can be imported"
node -e "require('./index.js')" 2>&1 && echo "✅ Module loads successfully" || echo "❌ Module failed to load"
echo ""

echo "Test 2: Run adapter outside Herdr (should just exec vibe)"
node ./index.js --version 2>&1

echo ""
echo "Test 3: Run adapter in Herdr mode (simulated)"
export HERDR_ENV=1
export HERDR_PANE_ID="test:w1:p1"
export HERDR_BIN_PATH="echo"
export HERDR_SOCKET_PATH="/tmp/herdr.sock"

node ./index.js -p "What is 2+2?" --max-turns 1 --output text 2>&1

echo ""
echo "=== Tests Complete ==="
