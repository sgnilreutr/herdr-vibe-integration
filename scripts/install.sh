#!/bin/bash
# Install script for Herdr + Mistral Vibe integration
# Usage: ./scripts/install.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADAPTER_DIR="$REPO_ROOT/adapter"
TARGET_BIN="$HOME/.local/bin/vibe-herdr"

echo "=== Herdr + Mistral Vibe Integration Installer ==="
echo ""

# Step 1: Build TypeScript adapter
echo "Step 1/3: Building TypeScript adapter..."
cd "$ADAPTER_DIR"
if [ ! -d node_modules ]; then
  echo "  Installing dependencies..."
  npm install
fi
npm run build
echo "  ✅ Built successfully"
echo ""

# Step 2: Add shebang if missing
echo "Step 2/3: Checking shebang..."
if ! head -1 dist/index.js | grep -q '#!/usr/bin/env node'; then
  echo "  Adding shebang to dist/index.js..."
  echo '#!/usr/bin/env node' | cat - dist/index.js > dist/index.js.tmp
  mv dist/index.js.tmp dist/index.js
  chmod +x dist/index.js
  echo "  ✅ Shebang added"
else
  echo "  ✅ Shebang already present"
fi
echo ""

# Step 3: Create symlink
echo "Step 3/3: Creating symlink..."
mkdir -p "$HOME/.local/bin"
ln -sf "$ADAPTER_DIR/dist/index.js" "$TARGET_BIN"
chmod +x "$TARGET_BIN"
echo "  ✅ Symlink created at $TARGET_BIN"
echo ""

# Verify
echo "Verification:"
if command -v vibe-herdr &>/dev/null; then
  echo "  ✅ vibe-herdr is in PATH"
  echo ""
  echo "Test it:"
  echo "  vibe-herdr --version"
  echo ""
  echo "In Herdr, run:"
  echo "  vibe-herdr"
else
  echo "  ❌ vibe-herdr not found in PATH"
  echo "  Make sure ~/.local/bin is in your PATH"
fi

echo ""
echo "=== Installation Complete ==="
