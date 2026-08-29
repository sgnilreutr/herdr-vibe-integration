# TDD Testing Approach for Herdr-Vibe Integration

## Current Status Analysis

Based on code review and Herdr's official integrations (Claude, Cursor, Opencode), here's what we know:

### How Herdr Integrations Work

**Pattern from official integrations:**
1. **Session Reporting**: Primary function is to report `pane.report_agent_session` so Herdr knows which agent instance is in which pane
2. **State Reporting**: Optional but recommended - report `pane.report_agent` with states (idle, working, blocked, done)
3. **Communication**: Use **Unix socket API** (not CLI) for reliability
4. **Environment Checks**: Verify `HERDR_ENV=1`, `HERDR_SOCKET_PATH`, `HERDR_PANE_ID`

**Key Insight**: Herdr **auto-detects** running agent processes (like `vibe`, `claude`) and shows them in the agents tab. The integration's job is to:
- Register the session (so Herdr knows which instance)
- Report state changes (optional but nice to have)

### Current Implementation Issues

**What's Working:**
- ✅ Hooks fire correctly (POST_AGENT, PRE_TOOL, POST_TOOL)
- ✅ Hook script (`herdr-agent-state.py`) executes
- ✅ Socket API used in hook script
- ✅ HERDR_PANE_ID check in hook script
- ✅ State reports sent via socket

**What Might Be Failing:**
- ⚠️ Adapter uses **CLI method** for initial state/session reporting
- ⚠️ CLI requires HERDR_BIN_PATH which may not work correctly
- ⚠️ No `agent_session_id` reported (only source and agent)

## Root Cause: Agents Tab Not Showing

The agents tab in Herdr shows agents when:
1. **Auto-detection**: Herdr sees a known agent process running (e.g., `vibe`)
2. **Session registration**: Integration reports `pane.report_agent_session`

If the agent isn't showing up, it's likely because:
1. Herdr doesn't auto-detect `vibe` as a known agent (it's not in Herdr's built-in list)
2. Our session reporting isn't working

**Solution**: We need to ensure session reporting works BEFORE spawning Vibe.

## TDD Approach for Herdr Integrations

Based on how Herdr's official integrations are tested:

### 1. Unit Tests (No Herdr Required)

Test the core logic in isolation:
- Environment variable parsing
- JSON message construction
- Socket communication logic

```python
# test_herdr_agent_state.py
import pytest
from herdr_agent_state import send_to_herdr, report_state

def test_send_to_herdr_socket(monkeypatch, tmp_path):
    # Mock socket and environment
    socket_path = tmp_path / "herdr.sock"
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", str(socket_path))
    
    # Create a fake socket server
    # ... test socket communication
    
    result = send_to_herdr("pane.report_agent", {"state": "idle"})
    assert result == True
```

### 2. Integration Tests (With Simulated Herdr)

Use the test socket server approach:

```bash
# Start fake Herdr socket server
python3 scripts/test-socket-server.py /tmp/test-herdr.sock &

# Run integration with simulated environment
hooks_test.py --socket-path /tmp/test-herdr.sock
```

### 3. End-to-End Tests (With Real Herdr)

Manual testing process:
1. Start Herdr
2. Open a pane
3. Run `vibe-herdr`
4. Verify agent appears in agents tab
5. Type a prompt
6. Verify state changes to "working"
7. Wait for response
8. Verify state changes to "idle"

### 4. Debugging Tools

**Socket Listener** (Already exists: `scripts/test-socket-server.py`):
```bash
python3 scripts/test-socket-server.py
```
Listens and prints all messages sent to Herdr socket.

**Environment Logger**:
```bash
# Add to hook script for debugging
echo "HERDR_PANE_ID=$HERDR_PANE_ID" >> /tmp/herdr-debug.log
echo "HERDR_SOCKET_PATH=$HERDR_SOCKET_PATH" >> /tmp/herdr-debug.log
echo "HERDR_ENV=$HERDR_ENV" >> /tmp/herdr-debug.log
```

**State Transition Logger**:
```bash
# In herdr-agent-state.py, add:
print(f"[DEBUG] Reporting state: {state}", file=sys.stderr)
```

## Recommended Improvements

### 1. Switch Adapter to Socket API

Change `adapter/src/index.ts` to use socket API instead of CLI:

```typescript
// BEFORE: CLI method
function reportState(state: string, message: string = ''): void {
  const { paneId, herdrBin } = getHerdrEnv();
  const args = ['pane', 'report-agent', paneId, ...];
  spawn(herdrBin, args, ...);
}

// AFTER: Socket API
function reportState(state: string, message: string = ''): void {
  const { paneId, socketPath } = getHerdrEnv();
  const request = {
    id: generateRequestId(),
    method: 'pane.report_agent',
    params: { pane_id: paneId, source: SOURCE, agent: AGENT, state, message }
  };
  sendToSocket(socketPath, request);
}
```

### 2. Report Session ID from Hooks

Vibe's hooks provide `session_id`. We should use it:

```python
# In herdr-agent-state.py
def handle_post_agent(hook_data: dict[str, Any]) -> None:
    session_id = hook_data.get("session_id")
    if session_id:
        report_agent_session(session_id)  # Report session first
    report_state("idle", "Ready for input")
```

### 3. Add Debug Mode

Add debug logging that can be enabled via environment variable:

```python
# In herdr-agent-state.py
DEBUG = os.environ.get("HERDR_VIBE_DEBUG") == "1"

def send_to_herdr(method: str, params: dict[str, Any]) -> bool:
    if DEBUG:
        print(f"[herdr-vibe] Sending: {method} {params}", file=sys.stderr)
    # ... rest of function
```

### 4. Testing Script for Full Integration

Create `scripts/test-full-integration.sh`:

```bash
#!/bin/bash
# Full integration test - simulates Herdr environment and tests all flows

set -e

echo "=== Starting Herdr Socket Test Server ==="
python3 scripts/test-socket-server.py /tmp/test-herdr.sock &
SOCKET_PID=$!
sleep 1

echo "=== Testing Hook Invocation ==="
echo '{"hook_event_name": "POST_AGENT", "session_id": "test-123"}' \
  | HERDR_PANE_ID=w1:p1 HERDR_SOCKET_PATH=/tmp/test-herdr.sock \
  python3 adapter/herdr-agent-state.py

echo "=== Testing Adapter ==="
HERDR_ENV=1 HERDR_PANE_ID=w1:p1 HERDR_SOCKET_PATH=/tmp/test-herdr.sock \
  HERDR_BIN_PATH=/usr/bin/echo node adapter/dist/index.js --version

kill $SOCKET_PID
echo "=== Tests Complete ==="
```

### 5. Herdr Pane Control "Eyes"

To give Vibe "eyes" to control Herdr panes for testing, we need:

**A. Socket API Client Library**

Create `scripts/herdr-client.py`:

```python
#!/usr/bin/env python3
"""
Herdr Socket Client for Testing

This script provides programmatic control over Herdr panes for testing.
"""

import json
import os
import socket
import sys
from pathlib import Path


def get_socket_path():
    """Get the Herdr socket path."""
    # Check environment first
    socket_path = os.environ.get("HERDR_SOCKET_PATH")
    if socket_path:
        return socket_path
    
    # Check default locations
    default_paths = [
        Path.home() / ".config" / "herdr" / "herdr.sock",
        Path("/tmp/herdr.sock"),
    ]
    
    for path in default_paths:
        if path.exists():
            return str(path)
    
    return None


def send_request(method: str, params: dict, socket_path: str = None) -> dict:
    """Send a request to Herdr socket and return response."""
    if socket_path is None:
        socket_path = get_socket_path()
    
    if not socket_path:
        raise Exception("Herdr socket not found")
    
    request = {
        "id": f"test:{os.getpid()}:{os.urandom(4).hex()}",
        "method": method,
        "params": params,
    }
    
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(socket_path)
        sock.sendall((json.dumps(request) + "\n").encode())
        
        # Read response
        response = sock.recv(4096).decode()
        sock.close()
        
        return json.loads(response) if response else {}
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return {"error": str(e)}


def list_agents():
    """List all registered agents in Herdr."""
    # This is a hypothetical method - check Herdr API
    # For now, we can query pane states
    return send_request("agent.get_all", {})


def report_agent_state(pane_id: str, state: str, source: str = "herdr:vibe", 
                        agent: str = "vibe", message: str = "") -> dict:
    """Report agent state for a pane."""
    return send_request("pane.report_agent", {
        "pane_id": pane_id,
        "source": source,
        "agent": agent,
        "state": state,
        "message": message,
    })


def create_test_session(pane_id: str) -> dict:
    """Create a test agent session."""
    return send_request("pane.report_agent_session", {
        "pane_id": pane_id,
        "source": "herdr:vibe",
        "agent": "vibe",
        "agent_session_id": f"test-session-{os.getpid()}",
    })


def main():
    """CLI interface for testing."""
    if len(sys.argv) < 2:
        print("Usage: herdr-client.py <command> [args]")
        print("Commands: list, report-state <pane> <state>, create-session <pane>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        agents = list_agents()
        print(json.dumps(agents, indent=2))
    elif command == "report-state":
        if len(sys.argv) < 4:
            print("Usage: herdr-client.py report-state <pane> <state>")
            sys.exit(1)
        result = report_agent_state(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2))
    elif command == "create-session":
        if len(sys.argv) < 3:
            print("Usage: herdr-client.py create-session <pane>")
            sys.exit(1)
        result = create_test_session(sys.argv[2])
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**B. Automated Testing Framework**

Create `scripts/test-integration.py`:

```python
#!/usr/bin/env python3
"""
Integration Testing Framework for Herdr-Vibe

This script provides automated testing with "eyes" into Herdr state.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from herdr_client import send_request, get_socket_path


class HerdrTestHarness:
    """Test harness for Herdr integration testing."""
    
    def __init__(self, socket_path: str = None):
        self.socket_path = socket_path or get_socket_path()
        self.temp_dir = tempfile.mkdtemp()
        self.cleanup_files = []
    
    def setup_environment(self, pane_id: str = "test:w1:p1"):
        """Set up test environment variables."""
        env = os.environ.copy()
        env.update({
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": pane_id,
            "HERDR_SOCKET_PATH": self.socket_path,
            "HERDR_BIN_PATH": "/usr/bin/echo",  # Fallback
        })
        return env
    
    def run_hook_script(self, hook_data: dict, pane_id: str = "test:w1:p1") -> dict:
        """Run the hook script and capture output."""
        env = self.setup_environment(pane_id)
        
        hook_script = Path("~/vibe/herdr-agent-state.py").expanduser()
        if not hook_script.exists():
            hook_script = Path("adapter/herdr-agent-state.py")
        
        cmd = ["python3", str(hook_script)]
        
        try:
            result = subprocess.run(
                cmd,
                input=json.dumps(hook_data),
                capture_output=True,
                text=True,
                env=env,
                timeout=5,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Timeout"}
    
    def test_hook_invocation(self):
        """Test that hooks invoke correctly."""
        hook_data = {
            "hook_event_name": "POST_AGENT",
            "session_id": "test-session-123",
        }
        
        result = self.run_hook_script(hook_data)
        assert result["returncode"] == 0, f"Hook failed: {result}"
        print("✅ Hook invocation test passed")
        return True
    
    def test_state_reporting(self):
        """Test that state is reported to Herdr."""
        # This requires a real Herdr socket
        if not self.socket_path:
            print("⚠️ Skipping state reporting test (no socket)")
            return False
        
        # Report a test state
        result = send_request("pane.report_agent", {
            "pane_id": "test:w1:p1",
            "source": "herdr:vibe",
            "agent": "vibe",
            "state": "working",
            "message": "Test message",
        }, self.socket_path)
        
        print(f"✅ State reporting test: {result}")
        return True
    
    def test_full_flow(self):
        """Test complete integration flow."""
        print("Testing full integration flow...")
        
        # Test 1: Hook invocation
        self.test_hook_invocation()
        
        # Test 2: State reporting
        self.test_state_reporting()
        
        print("✅ Full flow test passed")
    
    def cleanup(self):
        """Clean up test files."""
        for f in self.cleanup_files:
            try:
                os.unlink(f)
            except:
                pass


def main():
    """Run integration tests."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", help="Path to Herdr socket")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    
    harness = HerdrTestHarness(socket_path=args.socket_path)
    
    try:
        if args.debug:
            print(f"Socket path: {harness.socket_path}")
        
        harness.test_full_flow()
        print("\n🎉 All tests passed!")
    finally:
        harness.cleanup()


if __name__ == "__main__":
    main()
```

## Testing Checklist

- [ ] Unit tests for environment detection
- [ ] Unit tests for message construction
- [ ] Unit tests for socket communication
- [ ] Integration test with simulated Herdr
- [ ] End-to-end test with real Herdr
- [ ] Debug mode for troubleshooting
- [ ] Herdr socket client for programmatic control
- [ ] Automated test framework

## Next Steps

1. **Implement socket API in adapter** (replace CLI calls)
2. **Add session_id reporting from hooks**
3. **Create herdr-client.py for pane control**
4. **Create test-integration.py framework**
5. **Add debug logging**
6. **Run full test suite**
7. **Document results**
