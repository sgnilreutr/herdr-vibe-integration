#!/usr/bin/env python3
"""
Installation script for Herdr + Mistral Vibe integration.

This script:
1. Copies hooks.toml to ~/.vibe/hooks.toml
2. Copies herdr-agent-state.py to ~/.vibe/herdr-agent-state.py
3. Makes the script executable
4. Verifies the installation
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

# Files to install
INSTALL_FILES = [
    ("hooks.toml", "~/.vibe/hooks.toml"),
    ("herdr-agent-state.py", "~/.vibe/herdr-agent-state.py"),
]


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.resolve()


def expand_path(path: str) -> Path:
    """Expand ~ in path to user's home directory."""
    if path.startswith("~"):
        return Path.home() / path[2:]
    return Path(path)


def install_file(source: Path, dest: Path) -> bool:
    """Copy a file from source to dest, with proper permissions."""
    dest = expand_path(str(dest))
    
    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        shutil.copy2(source, dest)
        
        # Make executable if it's a script
        if dest.suffix in (".py", ".sh", ""):
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
        
        print(f"  ✓ Installed: {dest}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to install {dest}: {e}", file=sys.stderr)
        return False


def verify_installation() -> bool:
    """Verify that all files are installed correctly."""
    all_ok = True
    
    print("\nVerifying installation...")
    
    for _, dest_str in INSTALL_FILES:
        dest = expand_path(dest_str)
        if not dest.exists():
            print(f"  ✗ Missing: {dest}")
            all_ok = False
        elif not dest.is_file():
            print(f"  ✗ Not a file: {dest}")
            all_ok = False
        elif not os.access(dest, os.X_OK) and dest.suffix in (".py", ".sh", ""):
            print(f"  ✗ Not executable: {dest}")
            all_ok = False
        else:
            print(f"  ✓ Verified: {dest}")
    
    return all_ok


def main() -> None:
    """Main installation function."""
    script_dir = get_script_dir()
    
    print("Installing Herdr + Mistral Vibe integration...\n")
    
    success_count = 0
    for source_file, dest_str in INSTALL_FILES:
        source = script_dir / source_file
        if not source.exists():
            print(f"  ✗ Source file not found: {source}", file=sys.stderr)
            continue
        if install_file(source, dest_str):
            success_count += 1
    
    if success_count != len(INSTALL_FILES):
        print(f"\n✗ Installation incomplete ({success_count}/{len(INSTALL_FILES)} files)")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    
    if verify_installation():
        print("\n✓ Installation successful!")
        print("\nTo use:")
        print("  1. Start Herdr: herdr")
        print("  2. In a pane, run: vibe")
        print("  3. Herdr will automatically detect Vibe and show its state")
        print("\nTo uninstall:")
        print("  python3 install.py --uninstall")
        sys.exit(0)
    else:
        print("\n✗ Installation verification failed")
        sys.exit(1)


def uninstall() -> None:
    """Uninstall the integration."""
    print("Uninstalling Herdr + Mistral Vibe integration...\n")
    
    for _, dest_str in INSTALL_FILES:
        dest = expand_path(dest_str)
        if dest.exists():
            try:
                dest.unlink()
                print(f"  ✓ Removed: {dest}")
            except Exception as e:
                print(f"  ✗ Failed to remove {dest}: {e}", file=sys.stderr)
        else:
            print(f"  - Not found: {dest}")
    
    print("\n✓ Uninstallation complete")


if __name__ == "__main__":
    if "--uninstall" in sys.argv or "-u" in sys.argv:
        uninstall()
    else:
        main()
