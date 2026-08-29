# Herdr-Vibe Integration Testing Guide

## Overview

This guide explains how to test the Herdr-Vibe integration and provides the tools needed to give Vibe "eyes" into Herdr panes for real-time testing and debugging.

## Problem Analysis: Why Agents Tab Isn't Showing

Based on research into Herdr's official integrations (Claude, Cursor, Opencode), here's what we discovered:

### How Herdr Integrations Work

1. **Auto-detection**: Herdr automatically detects known agent processes (Claude, Codex, etc.) running in panes
2. **Session Registration**: Integrations report `pane.report_agent_session` so Herdr knows which agent instance is in which pane
3. **State Reporting**: Optional - report `pane.report_agent` with states (idle, working, blocked, done)
4. **Communication**: Official integrations use **Unix socket API** (not CLI)

### Key Differences in Our Implementation

**Official Integrations (Claude, Cursor):**
- Only report `pane.report_agent_session` (no state reporting!)
- Use socket API directly
- Check for `HERDR_ENV=1`, `HERDR_SOCKET_PATH`, `HERDR_PANE_ID`
- Triggered by agent's hook/plugin system

**Our Implementation:**
- Reports both session AND state (good!)
- Hook script uses socket API ✅
- Adapter uses CLI API ⚠️ (potential issue)
- Herdr doesn't auto-detect `vibe` as a known agent ⚠️

### The Root Cause

Herdr **only shows agents in the agents tab if**:
1. It auto-detects a known agent process, OR
2. An integration reports a session via `pane.report_agent_session`

**Issue**: `vibe` is not in Herdr's built-in list of known agents (unlike Claude, Codex, etc.). So we must ensure our session reporting works perfectly.

**Current Status**: Our implementation should work, but the CLI method in the adapter might fail if `HERDR_BIN_PATH` isn't set correctly in the wrapper process.

## Testing Infrastructure

We've created two powerful tools for testing:

### 1. Herdr Client (`scripts/herdr-client.py`)

A command-line tool to control Herdr panes programmatically.

**Usage:**
```bash
# Show help
python3 scripts/herdr-client.py --help

# Check environment
python3 scripts/herdr-client.py env

# Report agent state
python3 scripts/herdr-client.py report-state w1:p1 working "Processing..."

# Create agent session
python3 scripts/herdr-client.py create-session w1:p1 "session-123"

# Release agent
python3 scripts/herdr-client.py release-agent w1:p1

# Listen to socket messages (debugging)
python3 scripts/herdr-client.py listen
```

**Features:**
- Auto-detects Herdr socket path
- Can override socket path with `--socket`
- JSON output with `--json` flag
- Debug mode with `--debug` flag

### 2. Integration Test Harness (`scripts/test-integration.py`)

Automated testing framework with "eyes" into Herdr state.

**Usage:**
```bash
# Run all tests
python3 scripts/test-integration.py

# Run with debug output
python3 scripts/test-integration.py --debug

# Run specific test
python3 scripts/test-integration.py --test test_hook_invocation

# Test with real Herdr (not test server)
python3 scripts/test-integration.py --real-herdr

# List all available tests
python3 scripts/test-integration.py --list-tests
```

**Available Tests:**
- `test_environment_detection` - Verify Herdr environment variables
- `test_hook_with_missing_env` - Verify graceful handling of missing env
- `test_hook_invocation` - Test POST_AGENT hook
- `test_hook_pre_tool` - Test PRE_TOOL hook
- `test_hook_post_tool` - Test POST_TOOL hook
- `test_session_reporting` - Test session reporting
- `test_state_reporting` - Test state reporting
- `test_adapter_detection` - Test adapter Herdr detection

## Step-by-Step Testing

### Quick Test (No Herdr Required)

```bash
# Start a test socket server
python3 scripts/test-socket-server.py /tmp/test-herdr.sock &

# Run integration tests in another terminal
python3 scripts/test-integration.py
```

### Test with Real Herdr

**Step 1: Start Herdr**
```bash
herdr
```

**Step 2: Get Socket Path**
```bash
# In a Herdr pane or separate terminal
python3 scripts/herdr-client.py env
# Look for HERDR_SOCKET_PATH
```

**Step 3: Manually Test Socket Communication**
```bash
# Report a test state
python3 scripts/herdr-client.py report-state w1:p1 working "Test"

# Check if it appears in Herdr agents tab
```

**Step 4: Test Hook Script**
```bash
# Simulate a hook invocation
echo '{"hook_event_name": "POST_AGENT", "session_id": "test-123"}' | \
  HERDR_PANE_ID=w1:p1 HERDR_SOCKET_PATH=/path/to/herdr.sock \
  python3 ~/.vibe/herdr-agent-state.py
```

**Step 5: Test Full Integration**
```bash
# In a Herdr pane, run:
vibe-herdr

# Then interact with Vibe and watch the agents tab
```

### Debug Mode Testing

Enable debug logging in the hook script:

```bash
# Edit herdr-agent-state.py and add:
DEBUG = os.environ.get("HERDR_VIBE_DEBUG") == "1"

def send_to_herdr(method: str, params: dict[str, Any]) -> bool:
    if DEBUG:
        print(f"[herdr-vibe DEBUG] {method}: {params}", file=sys.stderr)
    # ... rest of function
```

Then test with debug enabled:
```bash
HERDR_VIBE_DEBUG=1 vibe-herdr
```

## Common Issues and Fixes

### Issue 1: Agent Not Showing in Agents Tab

**Symptoms:**
- Vibe runs fine in Herdr pane
- No agent entry appears in agents tab
- Hooks are firing (verified via logs)

**Debug Steps:**
1. Check if session is being reported:
   ```bash
   # In the Herdr pane where vibe-herdr is running, check stderr
   # Look for: "pane.report_agent_session" messages
   ```

2. Manually test session reporting:
   ```bash
   python3 scripts/herdr-client.py create-session w1:p1 "test-session"
   ```

3. Check Herdr socket connectivity:
   ```bash
   python3 scripts/herdr-client.py env
   ```

**Fix:**
- Ensure `reportAgentSession()` is called in adapter BEFORE spawning Vibe
- Use socket API instead of CLI in adapter
- Verify `HERDR_SOCKET_PATH` is set in adapter environment

### Issue 2: State Not Updating

**Symptoms:**
- Agent shows in agents tab
- State stays as "idle" or doesn't change
- User interacts with Vibe but state doesn't update

**Debug Steps:**
1. Check hook script execution:
   ```bash
   # Add to herdr-agent-state.py:
   import sys
   print(f"[DEBUG] Hook called: {hook_event_name}", file=sys.stderr)
   ```

2. Check environment in hooks:
   ```bash
   # Add to herdr-agent-state.py:
   print(f"[DEBUG] HERDR_PANE_ID={os.environ.get('HERDR_PANE_ID')}", file=sys.stderr)
   print(f"[DEBUG] HERDR_SOCKET_PATH={os.environ.get('HERDR_SOCKET_PATH')}", file=sys.stderr)
   ```

3. Test socket connectivity from hook:
   ```bash
   # Manually trigger a hook
   echo '{"hook_event_name": "PRE_TOOL", "tool_name": "test"}' | \
     HERDR_PANE_ID=w1:p1 HERDR_SOCKET_PATH=/path/to/herdr.sock \
     python3 ~/.vibe/herdr-agent-state.py
   ```

**Fix:**
- Verify hook script checks for `HERDR_PANE_ID` (not `HERDR_ENV`)
- Ensure socket API is used in hook script
- Check that Vibe is actually calling the hooks

### Issue 3: Adapter Hanging

**Symptoms:**
- Running `vibe-herdr` in Herdr pane
- Adapater prints "Running in Herdr pane: [pane-id]" then hangs
- Vibe TUI doesn't appear

**Root Cause:**
- This was the original issue when using `stdio: ['inherit', 'pipe', 'pipe']`
- Piping stdout/stderr broke Vibe's TTY detection

**Fix:**
- Use `stdio: 'inherit'` in adapter
- This is already fixed in current implementation

## Recommended Improvements

### 1. Switch Adapter to Socket API (Critical)

The adapter currently uses CLI API which requires `HERDR_BIN_PATH`. Switch to socket API for consistency with hooks.

**File:** `adapter/src/index.ts`

```typescript
// Add socket support
import { createConnection } from 'net';

function sendToSocket(method: string, params: any): void {
  const { paneId, socketPath } = getHerdrEnv();
  
  if (!socketPath) {
    console.error('[herdr-vibe] No socket path, falling back to CLI');
    reportState(state, message); // CLI fallback
    return;
  }
  
  const request = {
    id: `${SOURCE}:${Date.now()}:${Math.floor(Math.random() * 1_000_000).toString().padStart(6, '0')}`,
    method,
    params: { ...params, pane_id: paneId, source: SOURCE, agent: AGENT }
  };
  
  try {
    const client = createConnection(socketPath);
    client.write(JSON.stringify(request) + '\n');
    client.end();
  } catch (err) {
    console.error('[herdr-vibe] Socket error:', err.message);
  }
}

// Update reportState to use socket
function reportState(state: string, message: string = ''): void {
  const params: any = { state };
  if (message) params.message = message;
  sendToSocket('pane.report_agent', params);
}

// Update reportAgentSession to use socket
function reportAgentSession(sessionId?: string): void {
  const params: any = {};
  if (sessionId) params.agent_session_id = sessionId;
  sendToSocket('pane.report_agent_session', params);
}
```

### 2. Report Session ID from Hooks

Ensure session_id from Vibe hooks is used for session reporting.

**File:** `adapter/herdr-agent-state.py`

```python
def handle_post_agent(hook_data: dict[str, Any]) -> None:
    session_id = hook_data.get("session_id")
    
    # Always report session if we have one
    if session_id:
        report_agent_session(session_id)
    
    # Report idle state after agent completes
    report_state("idle", "Ready for input")
```

### 3. Add Installation Verification

Update the install script to verify everything works.

**File:** `adapter/install.py`

```python
def verify_herdr_integration():
    """Verify that Herdr integration is working."""
    print("\nVerifying Herdr integration...")
    
    # Check if Herdr is running
    herdr_running = check_herdr_running()
    if herdr_running:
        print("  ✓ Herdr is running")
        
        # Test session reporting
        result = report_agent_session("test:pane", "test-session")
        if "error" not in result:
            print("  ✓ Session reporting works")
        else:
            print(f"  ✗ Session reporting failed: {result['error']}")
    else:
        print("  ⚠ Herdr is not running (skipping live tests)")
    
    return herdr_running
```

### 4. Add Hook Logging

Add logging to hook script for debugging.

**File:** `adapter/herdr-agent-state.py`

```python
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[herdr-vibe] %(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Then use logger.info(), logger.debug(), etc.
```

## Testing Checklist

Before releasing or committing:

- [ ] Run unit tests: `python3 scripts/test-integration.py`
- [ ] Test with simulated Herdr: `python3 scripts/test-integration.py --debug`
- [ ] Test hook invocation manually
- [ ] Test with real Herdr instance
- [ ] Verify agent appears in agents tab
- [ ] Verify state changes (idle → working → idle)
- [ ] Test tool execution state changes
- [ ] Test cleanup on exit
- [ ] Test installation/uninstallation

## TDD Workflow

### 1. Write Tests First

Before implementing a new feature:
```bash
# Create a test for the new feature
python3 scripts/test-integration.py --test test_new_feature
# Should FAIL initially
```

### 2. Implement Feature

Implement the feature in the code.

### 3. Verify Tests Pass

```bash
# Run the test again
python3 scripts/test-integration.py --test test_new_feature
# Should PASS now
```

### 4. Run All Tests

```bash
python3 scripts/test-integration.py
```

### 5. Manual Testing

```bash
# Test in real Herdr
vibe-herdr
# Verify behavior
```

## Files Created/Modified

### New Files
- `scripts/herdr-client.py` - Herdr socket client for programmatic control
- `scripts/test-integration.py` - Automated testing framework
- `docs/TDD-TESTING-APPROACH.md` - Detailed TDD approach documentation
- `docs/TESTING-GUIDE.md` - This guide

### Modified Files
- `adapter/herdr-agent-state.py` - Added socket API with CLI fallback
- `adapter/src/index.ts` - Reports agent session before spawning Vibe

## Next Steps

1. **Fix the adapter to use socket API** - This is the most critical improvement
2. **Add debug logging** - For easier troubleshooting
3. **Test with real Herdr** - Verify everything works end-to-end
4. **Add more unit tests** - Cover edge cases
5. **Create CI workflow** - Automated testing on changes

## References

- [Herdr Socket API Docs](https://herdr.dev/docs/socket-api/)
- [Herdr Integrations](https://herdr.dev/docs/integrations/)
- [Claude Integration Hook](https://github.com/herdrdev/herdr/blob/master/src/integration/assets/claude/herdr-agent-state.sh)
- [Opencode Integration Plugin](https://github.com/herdrdev/herdr/blob/master/src/integration/assets/opencode/herdr-agent-state.js)
