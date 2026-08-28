#!/usr/bin/env python3
"""
Herdr Agent State Reporter for Mistral Vibe

This script is invoked by Vibe's hook system (via hooks.toml) and reports
agent state to Herdr.

It receives hook invocation JSON on stdin and reports state changes to Herdr
using the Herdr CLI (HERDR_BIN_PATH environment variable).

Installation:
  1. Place this file at ~/.vibe/herdr-agent-state.py
  2. Create ~/.vibe/hooks.toml with the hook configuration
  3. Ensure the script is executable: chmod +x ~/.vibe/herdr-agent-state.py

Herdr Environment:
  HERDR_ENV=1 - Running inside Herdr
  HERDR_PANE_ID - The pane ID (e.g., "w1:p1")
  HERDR_BIN_PATH - Path to the herdr CLI binary

Hook Types:
  POST_AGENT - Called after agent generates a response
  PRE_TOOL - Called before a tool is executed
  POST_TOOL - Called after a tool completes
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from typing import Any

# --- Configuration ---
SOURCE = "herdr:vibe"
AGENT = "vibe"


def get_herdr_env() -> dict[str, str | None]:
    """Get Herdr environment variables."""
    return {
        "pane_id": os.environ.get("HERDR_PANE_ID"),
        "herdr_bin": os.environ.get("HERDR_BIN_PATH"),
        "socket_path": os.environ.get("HERDR_SOCKET_PATH"),
    }


def send_to_herdr(method: str, params: dict[str, Any]) -> bool:
    """Send a JSON-RPC request to Herdr via Unix socket or CLI fallback."""
    env = get_herdr_env()
    socket_path = env["socket_path"]
    pane_id = env["pane_id"]
    herdr_bin = env["herdr_bin"]

    if not pane_id:
        return False

    # Build request
    request_id = f"{SOURCE}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:6]}"
    request = {
        "id": request_id,
        "method": method,
        "params": {**params, "pane_id": pane_id, "source": SOURCE, "agent": AGENT},
    }

    # Try Unix socket first (more reliable, doesn't require HERDR_BIN_PATH)
    if socket_path:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(socket_path)
            sock.sendall((json.dumps(request) + "\n").encode())
            # Try to read response (we don't need it, but this prevents blocking)
            try:
                sock.recv(4096)
            except Exception:
                pass
            sock.close()
            return True
        except Exception:
            pass  # Fall through to CLI method

    # Fallback to CLI if socket not available
    if herdr_bin:
        try:
            # Map method names to CLI commands
            if method == "pane.report_agent":
                args = [
                    herdr_bin,
                    "pane", "report-agent", pane_id,
                    "--source", SOURCE,
                    "--agent", AGENT,
                    "--state", params.get("state", "idle"),
                ]
                if "message" in params:
                    args.extend(["--message", params["message"]])
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            elif method == "pane.report_agent_session":
                args = [
                    herdr_bin,
                    "pane", "report-agent-session", pane_id,
                    "--source", SOURCE,
                    "--agent", AGENT,
                ]
                if "agent_session_id" in params:
                    args.extend(["--agent-session-id", params["agent_session_id"]])
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            elif method == "pane.release_agent":
                subprocess.Popen(
                    [herdr_bin, "pane", "release-agent", pane_id,
                     "--source", SOURCE, "--agent", AGENT],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return True
        except Exception:
            pass

    return False


def report_state(state: str, message: str = "") -> None:
    """Report agent state to Herdr."""
    params: dict[str, Any] = {"state": state}
    if message:
        params["message"] = message
    send_to_herdr("pane.report_agent", params)


def report_agent_session(session_id: str | None = None) -> None:
    """Report agent session to Herdr."""
    params: dict[str, Any] = {}
    if session_id:
        params["agent_session_id"] = session_id
    send_to_herdr("pane.report_agent_session", params)


def release_agent() -> None:
    """Release agent from Herdr."""
    send_to_herdr("pane.release_agent", {})


def handle_post_agent(hook_data: dict[str, Any]) -> None:
    """Handle POST_AGENT hook invocation."""
    session_id = hook_data.get("session_id")

    # Report session if we have one
    if session_id:
        report_agent_session(session_id)

    # POST_AGENT fires after the agent has finished generating a response
    # So we report idle (ready for next input)
    report_state("idle", "Ready for input")


def handle_pre_tool(hook_data: dict[str, Any]) -> None:
    """Handle PRE_TOOL hook invocation."""
    tool_name = hook_data.get("tool_name")
    if tool_name:
        report_state("working", f"Running tool: {tool_name}")


def handle_post_tool(hook_data: dict[str, Any]) -> None:
    """Handle POST_TOOL hook invocation."""
    tool_name = hook_data.get("tool_name")
    tool_status = hook_data.get("tool_status")

    if tool_status == "success":
        report_state("working", f"Tool {tool_name} completed")
    elif tool_status == "failure":
        report_state("blocked", f"Tool {tool_name} failed")
    elif tool_status == "cancelled":
        report_state("idle", f"Tool {tool_name} cancelled")
    else:
        report_state("working", f"Tool {tool_name} status: {tool_status}")


def main() -> None:
    """Main entry point - reads hook invocation from stdin."""
    # Check if we're in Herdr (check pane_id as primary indicator)
    # HERDR_ENV might not be propagated to hook subprocesses, but HERDR_PANE_ID should be
    if not os.environ.get("HERDR_PANE_ID"):
        # Not in Herdr, exit gracefully
        sys.exit(0)

    # Read all stdin (Vibe sends the full hook invocation as JSON)
    try:
        stdin_data = sys.stdin.read()
        hook_data = json.loads(stdin_data) if stdin_data.strip() else {}
    except (json.JSONDecodeError, Exception):
        hook_data = {}

    # Get hook type from the data
    hook_event_name = hook_data.get("hook_event_name")

    # Handle different hook types
    if hook_event_name == "POST_AGENT":
        handle_post_agent(hook_data)
    elif hook_event_name == "PRE_TOOL":
        handle_pre_tool(hook_data)
    elif hook_event_name == "POST_TOOL":
        handle_post_tool(hook_data)
    else:
        # Unknown hook type, report idle
        report_state("idle")

    # Exit successfully
    sys.exit(0)


if __name__ == "__main__":
    main()
