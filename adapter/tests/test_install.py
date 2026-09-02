"""
Unit tests for install.py

Tests the installation script functions.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Add adapter directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import functions from install.py
from install import (
    get_script_dir,
    expand_path,
    INSTALL_FILES,
)


class TestInstallFunctions(unittest.TestCase):
    """Test install script functions."""

    def test_get_script_dir(self):
        """Test get_script_dir returns a Path."""
        result = get_script_dir()
        self.assertIsInstance(result, Path)
        self.assertTrue(result.exists())

    def test_expand_path_with_tilde(self):
        """Test expand_path handles ~ expansion."""
        result = expand_path("~/.vibe/hooks.toml")
        self.assertIsInstance(result, Path)
        self.assertIn(".vibe", str(result))
        # Should not contain ~
        self.assertNotIn("~", str(result))

    def test_expand_path_without_tilde(self):
        """Test expand_path handles paths without ~."""
        result = expand_path("/tmp/test")
        self.assertIsInstance(result, Path)
        self.assertEqual(str(result), "/tmp/test")

    def test_install_files_constant(self):
        """Test INSTALL_FILES contains expected files."""
        self.assertIsInstance(INSTALL_FILES, list)
        self.assertGreater(len(INSTALL_FILES), 0)
        # Check that hooks.toml is in the list
        file_names = [f[0] for f in INSTALL_FILES]
        self.assertIn("hooks.toml", file_names)
        self.assertIn("herdr-agent-state.py", file_names)


class TestInstallPaths(unittest.TestCase):
    """Test path handling in install.py."""

    def test_vibe_files_exist(self):
        """Test that expected files exist in the project."""
        # Check that herdr-agent-state.py exists
        agent_state_path = Path(__file__).parent.parent / "herdr-agent-state.py"
        self.assertTrue(agent_state_path.exists())

    def test_hooks_toml_exist(self):
        """Test that hooks.toml exists."""
        hooks_path = Path(__file__).parent.parent / "hooks.toml"
        self.assertTrue(hooks_path.exists())


if __name__ == "__main__":
    unittest.main()
