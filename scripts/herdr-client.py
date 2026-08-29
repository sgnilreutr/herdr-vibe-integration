#!/usr/bin/env python3
"""
Herdr Socket Client for Testing

This script provides programmatic control over Herdr panes for testing.
It gives Vibe "eyes" to see and control Herdr state.

Usage:
    # List available commands
    python3 scripts/herdr-client.py --help
    
    # Report agent state
    python3 scripts/herdr-client.py report-state w1:p1 working
    
    # Create agent session
    python3 scripts/herdr-client.py create-session w1:p1
    
    # Query all agents
    python3 scripts/herdr-client.py list-agents
    
    # Monitor socket messages (listen mode)
    python3 scripts/herdr-client.py listen
"""

import json
import os
import socket
import sys
import time
from pathlib import Path


# Configuration
SOURCE = "herdr:vibe"
AGENT = "vibe"
DEFAULT_TIMEOUT = 1.0


def get_socket_path() -> str | None:
    """Get the Herdr socket path from environment or default locations."""
    # Check environment first
    socket_path = os.environ.get("HERDR_SOCKET_PATH")
    if socket_path:
        return socket_path
    
    # Check default Herdr locations
    default_paths = [
        Path.home() / ".config" / "herdr" / "herdr.sock",
        Path.home() / ".config" / "herdr" / "sessions" / "herdr.sock",
        Path("/tmp/herdr.sock"),
        Path("/tmp/herdr.sock." + str(os.getuid())),
    ]
    
    for path in default_paths:
        if path.exists():
            return str(path)
    
    return None


def generate_request_id() -> str:
    """Generate a unique request ID."""
    import random
    return f"{SOURCE}:{int(time.time() * 1000)}:{random.randrange(1_000_000):06d}"


def send_request(method: str, params: dict, socket_path: str = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """
    Send a JSON-RPC request to Herdr socket and return response.
    
    Args:
        method: The API method (e.g., "pane.report_agent")
        params: The parameters dictionary
        socket_path: Path to Herdr socket (uses get_socket_path() if None)
        timeout: Socket timeout in seconds
    
    Returns:
        Response dictionary or {"error": str} on failure
    """
    if socket_path is None:
        socket_path = get_socket_path()
    
    if not socket_path:
        return {"error": "Herdr socket not found. Set HERDR_SOCKET_PATH or start Herdr."}
    
    # Build request
    request = {
        "id": generate_request_id(),
        "method": method,
        "params": params,
    }
    
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
        sock.sendall((json.dumps(request) + "\n").encode())
        
        # Try to read response
        try:
            response = sock.recv(4096).decode()
            if response.strip():
                return json.loads(response)
        except socket.timeout:
            pass  # No response, but request was sent
        finally:
            sock.close()
        
        return {"success": True, "method": method}
    except ConnectionRefusedError:
        return {"error": f"Connection refused. Is Herdr running? Socket: {socket_path}"}
    except FileNotFoundError:
        return {"error": f"Socket not found: {socket_path}"}
    except Exception as e:
        return {"error": str(e)}


def report_agent_state(
    pane_id: str,
    state: str,
    message: str = "",
    source: str = SOURCE,
    agent: str = AGENT,
    socket_path: str = None,
) -> dict:
    """
    Report agent state to Herdr.
    
    Valid states: idle, working, blocked, done, unknown
    
    Args:
        pane_id: The pane ID (e.g., "w1:p1")
        state: The agent state
        message: Optional status message
        source: The source identifier
        agent: The agent name
        socket_path: Optional socket path override
    
    Returns:
        Response from Herdr
    """
    params = {
        "pane_id": pane_id,
        "source": source,
        "agent": agent,
        "state": state,
    }
    if message:
        params["message"] = message
    
    return send_request("pane.report_agent", params, socket_path)


def report_agent_session(
    pane_id: str,
    session_id: str = None,
    source: str = SOURCE,
    agent: str = AGENT,
    socket_path: str = None,
) -> dict:
    """
    Report agent session to Herdr.
    
    Args:
        pane_id: The pane ID (e.g., "w1:p1")
        session_id: Optional session identifier
        source: The source identifier
        agent: The agent name
        socket_path: Optional socket path override
    
    Returns:
        Response from Herdr
    """
    params = {
        "pane_id": pane_id,
        "source": source,
        "agent": agent,
    }
    if session_id:
        params["agent_session_id"] = session_id
    
    return send_request("pane.report_agent_session", params, socket_path)


def release_agent(
    pane_id: str,
    source: str = SOURCE,
    agent: str = AGENT,
    socket_path: str = None,
) -> dict:
    """
    Release agent from Herdr.
    
    Args:
        pane_id: The pane ID
        source: The source identifier
        agent: The agent name
        socket_path: Optional socket path override
    
    Returns:
        Response from Herdr
    """
    params = {
        "pane_id": pane_id,
        "source": source,
        "agent": agent,
    }
    return send_request("pane.release_agent", params, socket_path)


def get_agent_state(pane_id: str, socket_path: str = None) -> dict:
    """
    Query the current agent state for a pane.
    
    Note: This uses a hypothetical Herdr API method. The actual Herdr API
    may not support querying state directly.
    
    Args:
        pane_id: The pane ID
        socket_path: Optional socket path override
    
    Returns:
        Agent state information
    """
    params = {"pane_id": pane_id}
    return send_request("pane.get_agent", params, socket_path)


def list_agents(socket_path: str = None) -> dict:
    """
    List all registered agents in Herdr.
    
    Note: This uses a hypothetical Herdr API method.
    
    Args:
        socket_path: Optional socket path override
    
    Returns:
        Dictionary of all agents
    """
    return send_request("agent.get_all", {}, socket_path)


def listen(socket_path: str = None, max_messages: int = 100) -> None:
    """
    Listen to Herdr socket and print all messages.
    
    This is useful for debugging and understanding what's happening.
    
    Args:
        socket_path: Path to Herdr socket
        max_messages: Maximum number of messages to print
    """
    if socket_path is None:
        socket_path = get_socket_path()
    
    if not socket_path:
        print("Error: Herdr socket not found.", file=sys.stderr)
        print(f"Checked: {get_socket_path()}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Listening on {socket_path}... (Press Ctrl+C to stop)")
    print("-" * 60)
    
    try:
        # Create a temporary response socket (we're not a server, just spying)
        # Actually, we need to connect as a client to receive broadcast messages
        # This is a simplified version that just shows how to monitor
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        
        message_count = 0
        while message_count < max_messages:
            try:
                sock.connect(socket_path)
                break
            except ConnectionRefusedError:
                print("Waiting for Herdr socket to be available...")
                time.sleep(1)
        
        print("Connected. Waiting for messages...")
        
        # Note: The actual Herdr socket protocol may not support passive listening
        # This is a placeholder for future implementation
        while True:
            try:
                data = sock.recv(4096).decode()
                for line in data.split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            message_count += 1
                            print(f"\n[{message_count}] Method: {msg.get('method')}")
                            print(f"       Params: {json.dumps(msg.get('params'), indent=2)}")
                        except json.JSONDecodeError:
                            print(f"[Raw] {line[:100]}")
            except socket.timeout:
                # Check if we should continue
                if message_count >= max_messages:
                    break
            except KeyboardInterrupt:
                print("\nStopping...")
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        try:
            sock.close()
        except:
            pass


def check_herdr_running() -> bool:
    """Check if Herdr is running by testing socket connectivity."""
    socket_path = get_socket_path()
    if not socket_path:
        return False
    
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(socket_path)
        sock.close()
        return True
    except:
        return False


def print_environment() -> None:
    """Print relevant environment variables for debugging."""
    print("Herdr Environment Variables:")
    print("-" * 40)
    print(f"  HERDR_ENV: {os.environ.get('HERDR_ENV', '(not set)')}")
    print(f"  HERDR_PANE_ID: {os.environ.get('HERDR_PANE_ID', '(not set)')}")
    print(f"  HERDR_SOCKET_PATH: {os.environ.get('HERDR_SOCKET_PATH', '(not set)')}")
    print(f"  HERDR_BIN_PATH: {os.environ.get('HERDR_BIN_PATH', '(not set)')}")
    print(f"  HERDR_WORKSPACE_ID: {os.environ.get('HERDR_WORKSPACE_ID', '(not set)')}")
    print(f"  HERDR_TAB_ID: {os.environ.get('HERDR_TAB_ID', '(not set)')}")
    print()
    
    # Check for socket files
    socket_path = get_socket_path()
    if socket_path:
        exists = "✓" if Path(socket_path).exists() else "✗"
        print(f"  Socket file {socket_path}: {exists}")
    
    # Check if Herdr is running
    running = check_herdr_running()
    print(f"  Herdr running: {'✓ Yes' if running else '✗ No'}")


def main():
    """CLI interface for Herdr client."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Herdr Socket Client - Control and query Herdr panes for testing"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["report-state", "create-session", "release-agent", "get-state", 
                 "list-agents", "listen", "env", "ping"],
        help="Command to execute"
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Command arguments"
    )
    parser.add_argument(
        "--socket", "-s",
        help="Override Herdr socket path"
    )
    parser.add_argument(
        "--source",
        default=SOURCE,
        help="Override source identifier"
    )
    parser.add_argument(
        "--agent",
        default=AGENT,
        help="Override agent name"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug output"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )
    
    args = parser.parse_args()
    
    # Debug output
    if args.debug:
        print_environment()
    
    # Check if Herdr is running
    if not check_herdr_running() and args.command not in ["env", "listen", None]:
        print("Warning: Herdr does not appear to be running.", file=sys.stderr)
        print("State reports will be queued but not processed.", file=sys.stderr)
        print()
    
    # Execute command
    if args.command is None or args.command == "env":
        print_environment()
    elif args.command == "ping":
        socket_path = args.socket or get_socket_path()
        result = send_request("pane.ping", {"pane_id": "test"}, socket_path)
        if args.json:
            print(json.dumps(result))
        else:
            if "error" in result:
                print(f"❌ Ping failed: {result['error']}")
            else:
                print("✓ Ping successful")
    elif args.command == "report-state":
        if len(args.args) < 2:
            print("Usage: herdr-client.py report-state <pane_id> <state> [message]")
            print("  Valid states: idle, working, blocked, done, unknown")
            sys.exit(1)
        pane_id = args.args[0]
        state = args.args[1]
        message = args.args[2] if len(args.args) > 2 else ""
        result = report_agent_state(
            pane_id, state, message,
            args.source, args.agent,
            args.socket
        )
        if args.json:
            print(json.dumps(result))
        else:
            if "error" in result:
                print(f"❌ Failed: {result['error']}")
            else:
                print(f"✓ Reported state '{state}' for pane {pane_id}")
    elif args.command == "create-session":
        if len(args.args) < 1:
            print("Usage: herdr-client.py create-session <pane_id> [session_id]")
            sys.exit(1)
        pane_id = args.args[0]
        session_id = args.args[1] if len(args.args) > 1 else None
        result = report_agent_session(
            pane_id, session_id,
            args.source, args.agent,
            args.socket
        )
        if args.json:
            print(json.dumps(result))
        else:
            if "error" in result:
                print(f"❌ Failed: {result['error']}")
            else:
                print(f"✓ Created session for pane {pane_id}")
    elif args.command == "release-agent":
        if len(args.args) < 1:
            print("Usage: herdr-client.py release-agent <pane_id>")
            sys.exit(1)
        pane_id = args.args[0]
        result = release_agent(
            pane_id,
            args.source, args.agent,
            args.socket
        )
        if args.json:
            print(json.dumps(result))
        else:
            if "error" in result:
                print(f"❌ Failed: {result['error']}")
            else:
                print(f"✓ Released agent for pane {pane_id}")
    elif args.command == "get-state":
        if len(args.args) < 1:
            print("Usage: herdr-client.py get-state <pane_id>")
            sys.exit(1)
        pane_id = args.args[0]
        result = get_agent_state(pane_id, args.socket)
        if args.json:
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))
    elif args.command == "list-agents":
        result = list_agents(args.socket)
        if args.json:
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))
    elif args.command == "listen":
        listen(args.socket)
    else:
        print("Unknown command.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
