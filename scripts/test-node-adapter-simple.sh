#!/bin/bash
# Simple test of Node.js adapter

echo "=== Node.js Adapter Test ==="
echo ""

cd /Users/rtuerlings/Coding/herdr-vibe-integration/adapter

# Test 1: Outside Herdr
echo "Test 1: Outside Herdr (should just run vibe)"
unset HERDR_ENV
node index.js --version 2>&1

echo ""

# Test 2: In Herdr mode with echo as herdr binary
echo "Test 2: In Herdr mode (HERDR_BIN_PATH=echo)"
HERDR_ENV=1 HERDR_PANE_ID=test:p1 HERDR_BIN_PATH=echo node index.js -p "What is 2+2?" --max-turns 1 --output text 2>&1

echo ""
echo "=== Tests Complete ==="
echo ""
echo "Summary:"
echo "- Test 1: Should show 'vibe 2.24.3'"
echo "- Test 2: Should show '[herdr-vibe] Running...' then '4' (no state changes for simple output)"
