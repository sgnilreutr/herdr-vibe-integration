#!/usr/bin/env python3
"""
Simple Unix socket server for testing Herdr integration.

This creates a fake Herdr socket that listens for messages and prints them.
Use it to test the hook script without running actual Herdr.
"""

import json
import os
import socket
import sys
from pathlib import Path


def main() -> None:
    """Run a simple Unix socket server."""
    # Use a test socket path
    if len(sys.argv) > 1:
        socket_path = Path(sys.argv[1])
    else:
        socket_path = Path("/tmp/herdr-test.sock")
    
    # Remove socket if it already exists
    if socket_path.exists():
        socket_path.unlink()
    
    # Create and bind socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(socket_path))
    sock.listen(5)
    
    print(f"Listening on {socket_path}... (Press Ctrl+C to stop)")
    
    try:
        while True:
            conn, _ = sock.accept()
            data = conn.recv(4096).decode()
            
            # Parse and display each JSON message (they're newline-delimited)
            for line in data.split('\n'):
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        print(f"\n✓ Received message:", flush=True)
                        print(f"  Method: {msg.get('method')}", flush=True)
                        print(f"  Params: {json.dumps(msg.get('params'), indent=2)}", flush=True)
                        sys.stdout.flush()
                        
                        # Send a dummy response
                        response = {"id": msg.get("id"), "result": "ok"}
                        conn.sendall((json.dumps(response) + "\n").encode())
                    except json.JSONDecodeError:
                        print(f"  Raw: {line[:100]}...", flush=True)
                        sys.stdout.flush()
            conn.close()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sock.close()
        if socket_path.exists():
            socket_path.unlink()


if __name__ == "__main__":
    main()
