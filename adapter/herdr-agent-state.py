#!/usr/bin/env python3
"""
Herdr Agent State Reporter for Mistral Vibe

This script is invoked by Vibe's hook system (via hooks.toml) and reports
agent state to Herdr via the Unix domain socket API.

It receives hook invocation JSON on stdin and reports state changes to Herdr.

Installation:
  1. Place this file at ~/.vibe/herdr-agent-state.py
  2. Create ~/.vibe/hooks.toml with the hook configuration
  3. Ensure the script is executable: chmod +x ~/.vibe/herdr-agent-state.py

Herdr Environment:
  HERDR_ENV=1 - Running inside Herdr
  HERDR_PANE_ID - The pane ID
  HERDR_SOCKET_PATH - Unix socket path for Herdr API
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any


# --- Configuration ---
SOURCE = "herdr:vibe"
AGENT = "vibe"

# State patterns - reused from our TypeScript adapter
STATE_PATTERNS = {
    "idle": [
        r"^[>\$] ",
        r"^vibe[> ]",
        re.compile(r"^vibe[> ]", re.IGNORECASE),
        r"^Enter (prompt|command|query):",
        re.compile(r"^Enter (prompt|command|query):", re.IGNORECASE),
        r"^What would you like",
        re.compile(r"^What would you like", re.IGNORECASE),
        r"^How can I help",
        re.compile(r"^How can I help", re.IGNORECASE),
        r"^\n*$",
        re.compile(r"^\n*$"),
    ],
    "working": [
        r"^Thinking",
        re.compile(r"^Thinking", re.IGNORECASE),
        r"^Generating",
        re.compile(r"^Generating", re.IGNORECASE),
        r"^Processing",
        re.compile(r"^Processing", re.IGNORECASE),
        r"^Analyzing",
        re.compile(r"^Analyzing", re.IGNORECASE),
        r"^Working",
        re.compile(r"^Working", re.IGNORECASE),
        r"^[|/\\-]",
        re.compile(r"^[|/\\-]"),
        r"^[▰▱▱▱|▱▰▱▱|▱▱▰▱|▱▱▱▰]",
        re.compile(r"^[▰▱▱▱|▱▰▱▱|▱▱▰▱|▱▱▱▰]"),
        r"^[▉▊]",
        re.compile(r"^[▉▊]"),
        r"^\.\.\.",
        re.compile(r"^\.\.\."),
    ],
    "blocked": [
        r"Allow[?\s]",
        re.compile(r"Allow[?\s]", re.IGNORECASE),
        r"Please confirm",
        re.compile(r"Please confirm", re.IGNORECASE),
        r"Do you want to",
        re.compile(r"Do you want to", re.IGNORECASE),
        r"Continue[?\s]",
        re.compile(r"Continue[?\s]", re.IGNORECASE),
        r"Proceed[?\s]",
        re.compile(r"Proceed[?\s]", re.IGNORECASE),
        r"\[y/\\n\]",
        re.compile(r"\[y/\\n\]", re.IGNORECASE),
        r"\[yes/no\]",
        re.compile(r"\[yes/no\]", re.IGNORECASE),
        r"Approve[?\s]",
        re.compile(r"Approve[?\s]", re.IGNORECASE),
        r"Call tool",
        re.compile(r"Call tool", re.IGNORECASE),
        r"Run command",
        re.compile(r"Run command", re.IGNORECASE),
        r"Execute[?\s]",
        re.compile(r"Execute[?\s]", re.IGNORECASE),
    ],
    "done": [
        r"^Task complete",
        re.compile(r"^Task complete", re.IGNORECASE),
        r"^Done",
        re.compile(r"^Done", re.IGNORECASE),
        r"^✓",
        re.compile(r"^✓"),
        r"^✅",
        re.compile(r"^✅"),
        r"^Success",
        re.compile(r"^Success", re.IGNORECASE),
        r"^Finished",
        re.compile(r"^Finished", re.IGNORECASE),
        r"^Complete",
        re.compile(r"^Complete", re.IGNORECASE),
    ],
}


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    # CSI sequences
    text = re.sub(r'\x1b\[[\x20-\x3F]*[\x40-\x7E]', '', text)
    # OSC sequences
    text = re.sub(r'\x1b\][^\x07]*\x07', '', text)
    # ESC + control char
    text = re.sub(r'\x1b[\x00-\x1F\x7F]', '', text)
    return text


def detect_state_from_text(text: str) -> str | None:
    """Detect agent state from a line of text."""
    lines = text.split('\n')
    
    # Check each line for patterns
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check each state type
        for state_name, patterns in STATE_PATTERNS.items():
            for pattern in patterns:
                if isinstance(pattern, str):
                    if re.match(pattern, line):
                        return state_name
                else:  # compiled regex
                    if pattern.match(line):
                        return state_name
    
    return None


def get_herdr_env() -> dict[str, str | None]:
    """Get Herdr environment variables."""
    return {
        "pane_id": os.environ.get("HERDR_PANE_ID"),
        "socket_path": os.environ.get("HERDR_SOCKET_PATH"),
        "herdr_bin": os.environ.get("HERDR_BIN_PATH"),
    }


def send_to_herdr(method: str, params: dict[str, Any]) -> bool:
    """Send a JSON-RPC request to Herdr via Unix socket."""
    env = get_herdr_env()
    socket_path = env["socket_path"]
    pane_id = env["pane_id"]
    
    if not socket_path or not pane_id:
        return False
    
    request_id = f"{SOURCE}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:6]}"
    request = {
        "id": request_id,
        "method": method,
        "params": {**params, "pane_id": pane_id, "source": SOURCE, "agent": AGENT},
    }
    
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
    # Extract useful information
    session_id = hook_data.get("session_id")
    transcript_path = hook_data.get("transcript_path")
    
    # Report session if we have one
    if session_id:
        report_agent_session(session_id)
    
    # For now, report working state when post_agent fires
    # (Vibe is generating a response)
    report_state("working", "Generating response")


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
    else:
        report_state("working", f"Tool {tool_name} status: {tool_status}")


def main() -> None:
    """Main entry point - reads hook invocation from stdin."""
    # Check if we're in Herdr
    if os.environ.get("HERDR_ENV") != "1":
        # Not in Herdr, exit gracefully
        sys.exit(0)
    
    # Read all stdin (Vibe sends the full hook invocation as JSON)
    try:
        stdin_data = sys.stdin.read()
        hook_data = json.loads(stdin_data) if stdin_data.strip() else {}
    except (json.JSONDecodeError, Exception):
        hook_data = {}
    
    # Debug: print hook data to stderr
    print(f"[DEBUG] hook_data: {json.dumps(hook_data, indent=2)}", file=sys.stderr)
    
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
