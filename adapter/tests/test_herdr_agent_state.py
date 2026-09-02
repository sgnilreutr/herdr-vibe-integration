"""
Unit tests for herdr-agent-state.py

Tests the core functions that can be tested without Herdr running.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add adapter directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import the module - it's named herdr_agent_state.py for importability
# The actual deployed file is herdr-agent-state.py (symlink or copy)
import herdr_agent_state as hdr


class TestGetStr(unittest.TestCase):
    """Test _get_str helper function."""

    def test_returns_string_value(self):
        data = {"key": "value"}
        result = hdr._get_str(data, "key")
        self.assertEqual(result, "value")

    def test_returns_none_for_missing_key(self):
        data = {"key": "value"}
        result = hdr._get_str(data, "missing")
        self.assertIsNone(result)

    def test_returns_none_for_non_string_value(self):
        data = {"key": 123}
        result = hdr._get_str(data, "key")
        self.assertIsNone(result)

    def test_returns_none_for_none_value(self):
        data = {"key": None}
        result = hdr._get_str(data, "key")
        self.assertIsNone(result)

    def test_returns_none_for_list_value(self):
        data = {"key": ["a", "b"]}
        result = hdr._get_str(data, "key")
        self.assertIsNone(result)

    def test_returns_none_for_dict_value(self):
        data = {"key": {"nested": "value"}}
        result = hdr._get_str(data, "key")
        self.assertIsNone(result)


class TestNextSeq(unittest.TestCase):
    """Test _next_seq function."""

    def test_returns_integer(self):
        result = hdr._next_seq()
        self.assertIsInstance(result, int)

    def test_returns_positive(self):
        result = hdr._next_seq()
        self.assertGreater(result, 0)

    def test_returns_large_number(self):
        """Should return microseconds since epoch, so very large."""
        result = hdr._next_seq()
        # As of 2026, this should be > 1.7e12 (microseconds since 1970)
        self.assertGreater(result, 1_700_000_000_000)


class TestGetHerdrEnv(unittest.TestCase):
    """Test get_herdr_env function."""

    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_returns_dict(self):
        result = hdr.get_herdr_env()
        self.assertIsInstance(result, dict)

    def test_returns_expected_keys(self):
        result = hdr.get_herdr_env()
        self.assertIn("pane_id", result)
        self.assertIn("herdr_bin", result)
        self.assertIn("socket_path", result)

    def test_returns_env_values(self):
        os.environ["HERDR_PANE_ID"] = "w1:p1"
        os.environ["HERDR_BIN_PATH"] = "/usr/bin/herdr"
        os.environ["HERDR_SOCKET_PATH"] = "/tmp/herdr.sock"

        result = hdr.get_herdr_env()

        self.assertEqual(result["pane_id"], "w1:p1")
        self.assertEqual(result["herdr_bin"], "/usr/bin/herdr")
        self.assertEqual(result["socket_path"], "/tmp/herdr.sock")

    def test_returns_none_for_missing(self):
        # Clear any existing Herdr env vars
        os.environ.pop("HERDR_PANE_ID", None)
        os.environ.pop("HERDR_BIN_PATH", None)
        os.environ.pop("HERDR_SOCKET_PATH", None)

        result = hdr.get_herdr_env()

        self.assertIsNone(result["pane_id"])
        self.assertIsNone(result["herdr_bin"])
        self.assertIsNone(result["socket_path"])


class TestReportState(unittest.TestCase):
    """Test report_state function."""

    @patch('herdr_agent_state.send_to_herdr')
    def test_calls_send_to_herdr_with_state(self, mock_send):
        hdr.report_state("working")
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][0], "pane.report_agent")
        self.assertEqual(call_args[0][1]["state"], "working")

    @patch('herdr_agent_state.send_to_herdr')
    def test_includes_message(self, mock_send):
        hdr.report_state("idle", "Ready for input")
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][1]["message"], "Ready for input")

    @patch('herdr_agent_state.send_to_herdr')
    def test_no_message_when_empty(self, mock_send):
        hdr.report_state("idle", "")
        call_args = mock_send.call_args
        self.assertNotIn("message", call_args[0][1])


class TestReportAgentSession(unittest.TestCase):
    """Test report_agent_session function."""

    @patch('herdr_agent_state.send_to_herdr')
    def test_calls_send_to_herdr(self, mock_send):
        hdr.report_agent_session()
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][0], "pane.report_agent_session")

    @patch('herdr_agent_state.send_to_herdr')
    def test_includes_session_id(self, mock_send):
        hdr.report_agent_session("session-123")
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][1]["agent_session_id"], "session-123")

    @patch('herdr_agent_state.send_to_herdr')
    def test_no_session_id_when_none(self, mock_send):
        hdr.report_agent_session(None)
        call_args = mock_send.call_args
        self.assertNotIn("agent_session_id", call_args[0][1])


class TestReleaseAgent(unittest.TestCase):
    """Test release_agent function."""

    @patch('herdr_agent_state.send_to_herdr')
    def test_calls_send_to_herdr(self, mock_send):
        hdr.release_agent()
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][0], "pane.release_agent")
        self.assertEqual(call_args[0][1], {})


class TestSendToHerdr(unittest.TestCase):
    """Test send_to_herdr function."""

    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    @patch('herdr_agent_state.socket')
    @patch('herdr_agent_state.subprocess')
    def test_returns_false_without_pane_id(self, mock_subprocess, mock_socket):
        os.environ.pop("HERDR_PANE_ID", None)
        result = hdr.send_to_herdr("pane.report_agent", {"state": "idle"})
        self.assertFalse(result)

    @patch('herdr_agent_state.socket')
    @patch('herdr_agent_state.subprocess')
    def test_uses_socket_first(self, mock_subprocess, mock_socket):
        os.environ["HERDR_PANE_ID"] = "w1:p1"
        os.environ["HERDR_SOCKET_PATH"] = "/tmp/herdr.sock"

        mock_sock = MagicMock()
        mock_socket.socket.return_value = mock_sock
        mock_socket.AF_UNIX = 1
        mock_socket.SOCK_STREAM = 2

        result = hdr.send_to_herdr("pane.report_agent", {"state": "idle"})

        # Should try socket first
        mock_socket.socket.assert_called_once()
        mock_sock.connect.assert_called_once_with("/tmp/herdr.sock")

    @patch('herdr_agent_state.socket')
    @patch('herdr_agent_state.subprocess')
    def test_falls_back_to_cli(self, mock_subprocess, mock_socket):
        os.environ["HERDR_PANE_ID"] = "w1:p1"
        os.environ["HERDR_BIN_PATH"] = "/usr/bin/herdr"
        os.environ.pop("HERDR_SOCKET_PATH", None)

        # Socket fails
        mock_socket.socket.side_effect = Exception("Socket error")

        mock_popen = MagicMock()
        mock_subprocess.Popen.return_value = mock_popen

        result = hdr.send_to_herdr("pane.report_agent", {"state": "idle"})

        # Should fall back to CLI
        mock_subprocess.Popen.assert_called_once()


class TestConstants(unittest.TestCase):
    """Test module constants."""

    def test_source_constant(self):
        self.assertEqual(hdr.SOURCE, "herdr:vibe")

    def test_agent_constant(self):
        self.assertEqual(hdr.AGENT, "vibe")


class TestHookHandlers(unittest.TestCase):
    """Test hook handler functions."""

    @patch('herdr_agent_state.report_agent_session')
    @patch('herdr_agent_state.report_state')
    def test_handle_post_agent_with_session(self, mock_report_state, mock_report_session):
        hook_data = {"hook_event_name": "post_agent", "session_id": "sess-123"}
        hdr.handle_post_agent(hook_data)

        mock_report_session.assert_called_once_with("sess-123")
        mock_report_state.assert_called_once_with("idle", "Ready for input")

    @patch('herdr_agent_state.report_agent_session')
    @patch('herdr_agent_state.report_state')
    def test_handle_post_agent_without_session(self, mock_report_state, mock_report_session):
        hook_data = {"hook_event_name": "post_agent"}
        hdr.handle_post_agent(hook_data)

        mock_report_session.assert_called_once_with()
        mock_report_state.assert_called_once_with("idle", "Ready for input")

    @patch('herdr_agent_state.report_state')
    def test_handle_pre_tool(self, mock_report_state):
        hook_data = {"hook_event_name": "pre_tool", "tool_name": "read_resource"}
        hdr.handle_pre_tool(hook_data)

        mock_report_state.assert_called_once_with("working", "Running tool: read_resource")

    @patch('herdr_agent_state.report_state')
    def test_handle_pre_tool_without_tool_name(self, mock_report_state):
        hook_data = {"hook_event_name": "pre_tool"}
        hdr.handle_pre_tool(hook_data)

        # Should not report without tool name
        mock_report_state.assert_not_called()

    @patch('herdr_agent_state.report_state')
    def test_handle_post_tool_success(self, mock_report_state):
        hook_data = {"hook_event_name": "post_tool", "tool_name": "read_resource", "tool_status": "success"}
        hdr.handle_post_tool(hook_data)

        mock_report_state.assert_called_once_with("working", "Tool read_resource completed")

    @patch('herdr_agent_state.report_state')
    def test_handle_post_tool_failure(self, mock_report_state):
        hook_data = {"hook_event_name": "post_tool", "tool_name": "read_resource", "tool_status": "failure"}
        hdr.handle_post_tool(hook_data)

        mock_report_state.assert_called_once_with("blocked", "Tool read_resource failed")

    @patch('herdr_agent_state.report_state')
    def test_handle_post_tool_cancelled(self, mock_report_state):
        hook_data = {"hook_event_name": "post_tool", "tool_name": "read_resource", "tool_status": "cancelled"}
        hdr.handle_post_tool(hook_data)

        mock_report_state.assert_called_once_with("idle", "Tool read_resource cancelled")

    @patch('herdr_agent_state.report_state')
    def test_handle_post_tool_unknown_status(self, mock_report_state):
        hook_data = {"hook_event_name": "post_tool", "tool_name": "read_resource", "tool_status": "unknown"}
        hdr.handle_post_tool(hook_data)

        mock_report_state.assert_called_once_with("working", "Tool read_resource status: unknown")


if __name__ == "__main__":
    unittest.main()
