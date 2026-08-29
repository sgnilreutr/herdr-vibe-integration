#!/usr/bin/env python3
"""
Herdr-Vibe Integration Validation Logger

This is the BACKBONE for validating Herdr-Vibe integration.
It captures:
1. ALL hook invocations (from hook script debug log)
2. Herdr state changes (from socket polling)
3. send_to_herdr success/failure (from hook script debug log)

Usage:
    python3 scripts/validate-herdr-vibe.py              # Start validation logging
    python3 scripts/validate-herdr-vibe.py --show      # Show validation log
    python3 scripts/validate-herdr-vibe.py --clear     # Clear and start fresh
"""

import argparse
import json
import os
import signal
import socket
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_FILE = "/tmp/herdr-vibe-validation.log"
HOOK_DEBUG_LOG = "/tmp/herdr-debug/hook-debug.log"
POLL_INTERVAL = 0.5

# Track state for change detection
agent_state_cache = {}


def get_socket_path() -> str:
    """Get Herdr socket path."""
    socket_path = os.environ.get("HERDR_SOCKET_PATH")
    if socket_path:
        return socket_path
    default_paths = [
        Path.home() / ".config" / "herdr" / "herdr.sock",
        Path("/tmp/herdr.sock"),
    ]
    for path in default_paths:
        if path.exists():
            return str(path)
    return "~/.config/herdr/herdr.sock"


def send_request(socket_path: str, method: str, params: dict = None) -> dict:
    """Send JSON-RPC request to Herdr socket."""
    if params is None:
        params = {}
    request = {
        'id': f'validator-{int(time.time() * 1000)}',
        'method': method,
        'params': params
    }
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(socket_path)
        sock.sendall((json.dumps(request) + '\n').encode())
        response = sock.recv(8192).decode()
        sock.close()
        return json.loads(response)
    except Exception as e:
        return {'error': str(e)}


def log_validation(log_file: str, event_type: str, message: str, data: dict = None) -> None:
    """Log validation event."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if data:
        log_line = f"[{timestamp}] {event_type} | {message} | {json.dumps(data, default=str)}"
    else:
        log_line = f"[{timestamp}] {event_type} | {message}"
    print(log_line)
    with open(log_file, "a") as f:
        f.write(log_line + "\n")


def setup_log_file(log_file: str) -> None:
    """Setup validation log file."""
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    if not Path(log_file).exists() or Path(log_file).stat().st_size == 0:
        with open(log_file, "w") as f:
            f.write(f"# Herdr-Vibe Integration Validation Log\n")
            f.write(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# This is the BACKBONE for validation\n\n")


def get_agent_list(socket_path: str) -> list:
    """Get list of agents from Herdr."""
    response = send_request(socket_path, 'agent.list')
    return response.get('result', {}).get('agents', [])


def monitor_hook_log(log_file: str, hook_log_path: str) -> None:
    """Monitor hook debug log for new entries."""
    last_position = 0
    while True:
        try:
            if not Path(hook_log_path).exists():
                time.sleep(0.1)
                continue
            
            with open(hook_log_path, 'r') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse hook invocation
                    if "Hook script invoked" in line:
                        parts = line.split("HERDR_PANE_ID=")
                        if len(parts) > 1:
                            pane_id = parts[1].split("\n")[0].strip()
                            log_validation(log_file, "HOOK_INVOKED", f"Pane {pane_id}", {"pane_id": pane_id})
                    
                    # Parse hook data
                    if "hook_event_name" in line and "stdin_data=" in line:
                        try:
                            # Extract JSON from stdin_data
                            start = line.index("stdin_data=") + 11
                            json_str = line[start:]
                            hook_data = json.loads(json_str.split("\n")[0].rstrip(","))
                            pane_id = hook_data.get("pane_id") or "unknown"
                            event_name = hook_data.get("hook_event_name", "unknown")
                            session_id = hook_data.get("session_id", "unknown")[:8]
                            
                            log_validation(log_file, "HOOK_EVENT", f"{event_name} from {pane_id}", {
                                "pane_id": pane_id,
                                "session_id": session_id,
                                "event": event_name,
                                "tool": hook_data.get("tool_name"),
                                "state": hook_data.get("agent_status")
                            })
                        except (json.JSONDecodeError, Exception):
                            pass
                    
                    # Parse send_to_herdr results
                    if "send_to_herdr SUCCESS" in line:
                        parts = line.split("pane=")
                        if len(parts) > 1:
                            pane_id = parts[1].strip()
                            method = line.split("method=")[1].split(" pane=")[0].strip()
                            log_validation(log_file, "HERDR_SEND_SUCCESS", f"{method} to {pane_id}", {"pane_id": pane_id, "method": method})
                    
                    if "send_to_herdr FAIL" in line:
                        parts = line.split("pane=")
                        if len(parts) > 1:
                            pane_id = parts[1].strip()
                            log_validation(log_file, "HERDR_SEND_FAILED", f"Failed for {pane_id}", {"pane_id": pane_id, "line": line[:200]})
                    
                    last_position = f.tell()
        except Exception as e:
            time.sleep(0.1)
        time.sleep(0.1)


def monitor_herdr_state(log_file: str, socket_path: str) -> None:
    """Monitor Herdr state changes."""
    old_agents = get_agent_list(socket_path)
    old_lookup = {a.get('pane_id'): a for a in old_agents}
    
    log_validation(log_file, "INITIAL_STATE", "Herdr agent list", {
        'agents': [{'pane': a.get('pane_id'), 'agent': a.get('agent'), 'status': a.get('agent_status')} for a in old_agents]
    })
    
    while True:
        time.sleep(POLL_INTERVAL)
        new_agents = get_agent_list(socket_path)
        new_lookup = {a.get('pane_id'): a for a in new_agents}
        all_panes = set(old_lookup.keys()) | set(new_lookup.keys())
        
        for pane_id in all_panes:
            old = old_lookup.get(pane_id)
            new = new_lookup.get(pane_id)
            
            if old is None:
                log_validation(log_file, "AGENT_APPEARED", f"New agent in {pane_id}", {
                    'pane_id': pane_id,
                    'agent': new.get('agent'),
                    'status': new.get('agent_status')
                })
            elif new is None:
                log_validation(log_file, "AGENT_REMOVED", f"Agent removed from {pane_id}", {
                    'pane_id': pane_id,
                    'agent': old.get('agent')
                })
            elif old.get('agent_status') != new.get('agent_status'):
                log_validation(log_file, "STATE_CHANGE", f"{pane_id}: {old.get('agent_status')} -> {new.get('agent_status')}", {
                    'pane_id': pane_id,
                    'agent': new.get('agent'),
                    'from': old.get('agent_status'),
                    'to': new.get('agent_status'),
                    'title': new.get('terminal_title', '')[:50]
                })
        
        old_lookup = new_lookup


def monitor_agents(log_file: str, socket_path: str = None) -> None:
    """Main monitoring function."""
    if socket_path is None:
        socket_path = get_socket_path()
    if not socket_path or not Path(socket_path).exists():
        print(f"Error: Herdr socket not found at {socket_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Validation Logger started")
    print(f"Logging to: {log_file}")
    print(f"Monitoring hooks from: {HOOK_DEBUG_LOG}")
    print(f"Monitoring Herdr socket: {socket_path}")
    print(f"Press Ctrl+C to stop\n")
    
    setup_log_file(log_file)
    log_validation(log_file, "VALIDATION_STARTED", "Herdr-Vibe integration validation logger active")
    
    # Start hook log monitor in background thread
    hook_thread = threading.Thread(target=monitor_hook_log, args=(log_file, HOOK_DEBUG_LOG), daemon=True)
    hook_thread.start()
    
    # Monitor Herdr state in main thread
    monitor_herdr_state(log_file, socket_path)


def show_log(log_file: str) -> None:
    """Show validation log."""
    if not Path(log_file).exists():
        print(f"Log file not found: {log_file}", file=sys.stderr)
        return
    print(f"\nHerdr-Vibe Validation Log: {log_file}\n")
    with open(log_file, "r") as f:
        print(f.read())


def main():
    parser = argparse.ArgumentParser(description="Herdr-Vibe Integration Validation Logger")
    parser.add_argument("--output", "-o", default=DEFAULT_LOG_FILE)
    parser.add_argument("--socket", "-s")
    parser.add_argument("--show", "-S", action="store_true")
    parser.add_argument("--clear", "-c", action="store_true")
    args = parser.parse_args()
    
    if args.show:
        show_log(args.output)
        return
    if args.clear and Path(args.output).exists():
        Path(args.output).unlink()
        print(f"Cleared: {args.output}")
    monitor_agents(args.output, args.socket)


if __name__ == "__main__":
    main()
