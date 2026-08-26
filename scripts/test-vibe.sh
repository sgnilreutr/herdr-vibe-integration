#!/bin/bash
# Test script to understand Mistral Vibe CLI behavior
# Run this to see how Vibe handles stdin/stdout in different modes

set -e

echo "=== Mistral Vibe CLI Behavior Test ==="
echo ""

# Test 1: Check version
echo "Test 1: Version check"
vibe --version || echo "No --version flag"
echo ""

# Test 2: Help output
echo "Test 2: Help output (first 20 lines)"
vibe --help 2>&1 | head -20 || echo "No --help flag"
echo ""

# Test 3: Programmatic mode with --prompt
echo "Test 3: Programmatic mode with --prompt"
echo "Prompt: 'What is 2+2?'"
timeout 10 vibe --prompt "What is 2+2?" --max-turns 1 2>&1 | head -30 || echo "Programmatic mode test failed or timed out"
echo ""

# Test 4: Stdin input (piped)
echo "Test 4: Piped stdin input"
echo "What is 3+3?" | timeout 10 vibe 2>&1 | head -20 || echo "Piped stdin test failed or timed out"
echo ""

# Test 5: Check if it's a TTY
# This is important for Herdr integration
echo "Test 5: TTY detection"
if [ -t 0 ]; then
    echo "stdin IS a TTY"
else
    echo "stdin is NOT a TTY"
fi
if [ -t 1 ]; then
    echo "stdout IS a TTY"
else
    echo "stdout is NOT a TTY"
fi
echo ""

echo "=== Test Complete ==="
