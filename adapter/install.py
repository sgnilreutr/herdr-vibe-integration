#!/usr/bin/env python3
"""
Installation script for Herdr + Mistral Vibe integration.

This script:
1. Copies hooks.toml to ~/.vibe/hooks.toml
2. Copies herdr-agent-state.py to ~/.vibe/herdr-agent-state.py
3. Creates a symlink for vibe-herdr wrapper at ~/.local/bin/vibe-herdr
4. Verifies the installation

Architecture:
- The vibe-herdr wrapper (TypeScript) is a thin wrapper that:
  * Detects Herdr environment
  * Reports initial idle state
  * Runs Vibe with TUI intact
  * Reports release on exit

- The hooks.toml + herdr-agent-state.py provide rich state reporting:
  * POST_AGENT: Reports when Vibe generates a response
  * PRE_TOOL: Reports when a tool starts
  * POST_TOOL: Reports when a tool completes
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
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

        print(f"  Installed: {dest}")
        return True
    except Exception as e:
        print(f"  Failed to install {dest}: {e}", file=sys.stderr)
        return False


def install_symlink() -> bool:
    """Create symlink for vibe-herdr wrapper."""
    script_dir = get_script_dir()
    dist_path = script_dir / "dist" / "index.js"

    if not dist_path.exists():
        print("  Building TypeScript first...", file=sys.stderr)
        try:
            subprocess.run(
                ["npm", "run", "build"],
                cwd=script_dir,
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  Failed to build TypeScript: {e}", file=sys.stderr)
            return False

    symlink_path = Path.home() / ".local" / "bin" / "vibe-herdr"
    symlink_path.parent.mkdir(parents=True, exist_ok=True)

    if symlink_path.exists():
        symlink_path.unlink()

    try:
        symlink_path.symlink_to(dist_path)
        print(f"  Symlinked: {symlink_path} -> {dist_path}")
        return True
    except Exception as e:
        print(f"  Failed to create symlink: {e}", file=sys.stderr)
        return False


def verify_installation() -> bool:
    """Verify that all files are installed correctly."""
    all_ok = True

    print("\nVerifying installation...")

    for _, dest_str in INSTALL_FILES:
        dest = expand_path(dest_str)
        if not dest.exists():
            print(f"  Missing: {dest}")
            all_ok = False
        elif not dest.is_file():
            print(f"  Not a file: {dest}")
            all_ok = False
        elif not os.access(dest, os.X_OK) and dest.suffix in (".py", ".sh", ""):
            print(f"  Not executable: {dest}")
            all_ok = False
        else:
            print(f"  Verified: {dest}")

    # Check symlink
    symlink_path = Path.home() / ".local" / "bin" / "vibe-herdr"
    if not symlink_path.exists():
        print(f"  Missing symlink: {symlink_path}")
        all_ok = False
    elif not symlink_path.is_symlink():
        print(f"  Not a symlink: {symlink_path}")
        all_ok = False
    else:
        print(f"  Verified symlink: {symlink_path}")

    return all_ok


def main() -> None:
    """Main installation function."""
    script_dir = get_script_dir()

    print("Installing Herdr + Mistral Vibe integration...\n")

    success_count = 0
    for source_file, dest_str in INSTALL_FILES:
        source = script_dir / source_file
        if not source.exists():
            print(f"  Source file not found: {source}", file=sys.stderr)
            continue
        if install_file(source, dest_str):
            success_count += 1

    # Install symlink
    if install_symlink():
        success_count += 1

    if success_count != len(INSTALL_FILES) + 1:
        print(f"\n  Installation incomplete ({success_count}/{len(INSTALL_FILES) + 1} items)")
        sys.exit(1)

    print("\n" + "=" * 60)

    if verify_installation():
        print("\n  Installation successful!")
        print("\nTo use:")
        print("  1. Start Herdr: herdr")
        print("  2. In a Herdr pane, run: vibe-herdr")
        print("  3. Herdr will show Vibe's state in the sidebar")
        print("\nHow it works:")
        print("  - The vibe-herdr wrapper reports initial idle state")
        print("  - Vibe's hook system calls herdr-agent-state.py on events")
        print("  - This provides rich state reporting (working/blocked/done)")
        print("\nTo uninstall:")
        print("  python3 install.py --uninstall")
        sys.exit(0)
    else:
        print("\n  Installation verification failed")
        sys.exit(1)


def uninstall() -> None:
    """Uninstall the integration."""
    print("Uninstalling Herdr + Mistral Vibe integration...\n")

    for _, dest_str in INSTALL_FILES:
        dest = expand_path(dest_str)
        if dest.exists():
            try:
                dest.unlink()
                print(f"  Removed: {dest}")
            except Exception as e:
                print(f"  Failed to remove {dest}: {e}", file=sys.stderr)
        else:
            print(f"  Not found: {dest}")

    # Remove symlink
    symlink_path = Path.home() / ".local" / "bin" / "vibe-herdr"
    if symlink_path.exists():
        try:
            symlink_path.unlink()
            print(f"  Removed symlink: {symlink_path}")
        except Exception as e:
            print(f"  Failed to remove symlink: {e}", file=sys.stderr)
    else:
        print(f"  Symlink not found: {symlink_path}")

    print("\n  Uninstallation complete")


if __name__ == "__main__":
    if "--uninstall" in sys.argv or "-u" in sys.argv:
        uninstall()
    else:
        main()
