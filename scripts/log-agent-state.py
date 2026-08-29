#!/usr/bin/env python3
"""
Herdr Agent State Logger

This script monitors Herdr agent state changes by polling the agent list.
It saves the logs to /tmp/herdr-agent-state.log for later analysis.

Usage:
    python3 scripts/log-agent-state.py              # Start logging
    python3 scripts/log-agent-state.py --show      # Show existing log
    python3 scripts/log-agent-state.py --clear     # Clear and start fresh
    python3 scripts/log-agent-state.py --track vibe # Only track vibe agents
"""

import argparse
import json
import os
import signal
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_FILE = "/tmp/herdr-agent-state.log"
POLL_INTERVAL = 1.0


def get_socket_path() -> str:
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
    if params is None:
        params = {}
    request = {
        'id': f'logger-{int(time.time() * 1000)}',
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


def log_message(log_file: str, message: str, data: dict = None) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if data:
        log_line = f"[{timestamp}] {message} | {json.dumps(data, default=str)}"
    else:
        log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(log_file, "a") as f:
        f.write(log_line + "\n")
        f.flush()
        os.fsync(f.fileno())


def setup_log_file(log_file: str, track_agents: list = None) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    if not Path(log_file).exists() or Path(log_file).stat().st_size == 0:
        with open(log_file, "w") as f:
            f.write(f"# Herdr Agent State Log\n")
            f.write(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Tracking: {track_agents or 'all agents'}\n\n")


def get_agent_list(socket_path: str, track_agents: list = None) -> list:
    response = send_request(socket_path, 'agent.list')
    agents = response.get('result', {}).get('agents', [])
    if track_agents:
        agents = [a for a in agents if a.get('agent') in track_agents]
    return agents


def monitor_agents(log_file: str, socket_path: str = None, interval: float = POLL_INTERVAL, track_agents: list = None) -> None:
    if socket_path is None:
        socket_path = get_socket_path()
    if not socket_path or not Path(socket_path).exists():
        print(f"Error: Herdr socket not found at {socket_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Monitoring Herdr socket: {socket_path}")
    print(f"Logging to: {log_file}")
    print(f"Press Ctrl+C to stop\n")
    
    setup_log_file(log_file, track_agents)
    log_message(log_file, "CONNECTED")
    
    old_agents = get_agent_list(socket_path, track_agents)
    log_message(log_file, "INITIAL_STATE", {
        'agents': [{'pane': a.get('pane_id'), 'agent': a.get('agent'), 'status': a.get('agent_status')} for a in old_agents]
    })
    
    try:
        while True:
            time.sleep(interval)
            new_agents = get_agent_list(socket_path, track_agents)
            
            # Check for changes
            old_lookup = {a.get('pane_id'): a for a in old_agents}
            new_lookup = {a.get('pane_id'): a for a in new_agents}
            all_panes = set(old_lookup.keys()) | set(new_lookup.keys())
            
            for pane_id in all_panes:
                old = old_lookup.get(pane_id)
                new = new_lookup.get(pane_id)
                
                if old is None:
                    log_message(log_file, f"AGENT_NEW", {'pane_id': pane_id, 'agent': new.get('agent'), 'status': new.get('agent_status')})
                elif new is None:
                    log_message(log_file, f"AGENT_REMOVED", {'pane_id': pane_id, 'agent': old.get('agent')})
                else:
                    status_changed = old.get('agent_status') != new.get('agent_status')
                    title_changed = old.get('terminal_title') != new.get('terminal_title')
                    seq_changed = old.get('state_change_seq') != new.get('state_change_seq')
                    
                    if status_changed or title_changed or seq_changed:
                        log_entry = {
                            'pane_id': pane_id,
                            'agent': new.get('agent'),
                            'status': new.get('agent_status'),
                            'title': new.get('terminal_title', '')[:40]
                        }
                        if status_changed:
                            log_entry['from_status'] = old.get('agent_status')
                            log_entry['to_status'] = new.get('agent_status')
                        if title_changed:
                            log_entry['from_title'] = old.get('terminal_title', '')[:40]
                            log_entry['to_title'] = new.get('terminal_title', '')[:40]
                        if seq_changed:
                            log_entry['from_seq'] = old.get('state_change_seq')
                            log_entry['to_seq'] = new.get('state_change_seq')
                        
                        log_message(log_file, f"STATE_CHANGE", log_entry)
            
            old_agents = new_agents
            
    except KeyboardInterrupt:
        log_message(log_file, "DISCONNECTED")
        print("\nStopped.")


def show_log(log_file: str) -> None:
    if not Path(log_file).exists():
        print(f"Log file not found: {log_file}", file=sys.stderr)
        return
    print(f"\nHerdr Agent State Log: {log_file}\n")
    with open(log_file, "r") as f:
        print(f.read())


def main():
    parser = argparse.ArgumentParser(description="Log Herdr agent state changes")
    parser.add_argument("--output", "-o", default=DEFAULT_LOG_FILE)
    parser.add_argument("--socket", "-s")
    parser.add_argument("--show", "-S", action="store_true")
    parser.add_argument("--clear", "-c", action="store_true")
    parser.add_argument("--track", "-t", nargs='*', default=None)
    parser.add_argument("--interval", "-i", type=float, default=POLL_INTERVAL)
    args = parser.parse_args()
    
    if args.show:
        show_log(args.output)
        return
    if args.clear and Path(args.output).exists():
        Path(args.output).unlink()
        print(f"Cleared: {args.output}")
    monitor_agents(args.output, args.socket, args.interval, args.track)


if __name__ == "__main__":
    main()
