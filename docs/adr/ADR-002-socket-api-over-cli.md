# ADR-002: Unix Socket API over CLI for Hook State Reporting

## Status
**Accepted** - Implemented and deployed

## Context
After adopting the hooks-only architecture (ADR-001), state updates were still not appearing in Herdr's agents pane. Debugging revealed that hook subprocesses spawned by Vibe were not receiving the `HERDR_ENV` and `HERDR_BIN_PATH` environment variables, causing the hook script to exit early or fail to report state.

### The Problem Chain
```
1. Adapter spawns Vibe with full TTY access
2. User interacts with Vibe
3. Vibe fires hook (e.g., PRE_TOOL)
4. Vibe spawns subprocess: python3 ~/.vibe/herdr-agent-state.py
5. Hook script checks: os.environ.get("HERDR_ENV") == "1"?
6. Result: HERDR_ENV is NOT set → script exits with sys.exit(0)
7. State is NEVER reported to Herdr
```

From `/tmp/hook-call.log`, we confirmed:
- ✅ Hooks WERE firing (PRE_TOOL, POST_TOOL logged)
- ✅ `HERDR_PANE_ID` WAS passed to hooks
- ❌ `HERDR_ENV` and `HERDR_BIN_PATH` were NOT passed

### Why Environment Variables Were Missing
Vibe's hook execution system spawns subprocesses for hook commands. The environment inheritance behavior depends on how Vibe does this. Evidence suggests:
- Some environment variables (HERDR_PANE_ID) are preserved
- Others (HERDR_ENV, HERDR_BIN_PATH) are not
- This may be intentional (security) or a limitation of Vibe's subprocess spawning

## Decision
Use **Unix domain socket API** as the primary method for state reporting from hooks, with CLI as fallback.

### Why Socket API?
Herdr exposes a Unix domain socket for direct communication. The socket:
- Uses newline-delimited JSON-RPC
- Doesn't require `HERDR_BIN_PATH` (uses `HERDR_SOCKET_PATH` which IS passed through)
- Is the same mechanism used by Herdr's built-in integrations (claude, codex, etc.)
- More reliable and lower latency than spawning CLI processes

### Implementation
```python
# BEFORE (CLI-only, fragile)
def report_state(state: str, message: str = "") -> None:
    herdr_bin = os.environ.get("HERDR_BIN_PATH")  # Might be None
    if not herdr_bin:
        return  # FAILS SILENTLY
    subprocess.Popen([herdr_bin, "pane", "report-agent", ...])

# AFTER (Socket-first, CLI fallback)
def send_to_herdr(method: str, params: dict[str, Any]) -> bool:
    socket_path = os.environ.get("HERDR_SOCKET_PATH")  # IS available
    
    if socket_path:
        # Try socket first
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.sendall(json.dumps(request) + "\n")
        return True
    
    # Fallback to CLI if socket fails
    if herdr_bin := os.environ.get("HERDR_BIN_PATH"):
        subprocess.Popen([herdr_bin, ...])
        return True
    
    return False
```

## Consequences

### Positive
- ✅ Works even when HERDR_ENV and HERDR_BIN_PATH are missing
- ✅ Only requires HERDR_SOCKET_PATH (which Vibe does pass through)
- ✅ Matches Herdr's built-in integration patterns
- ✅ Lower latency (no process spawning for each state update)
- ✅ More robust (socket is direct IPC, CLI is indirect)

### Negative
- ⚠️ Requires `socket` and `uuid` Python imports (trivial)
- ⚠️ Slightly more complex than pure CLI approach
- ⚠️ Fallback path still needs CLI if socket unavailable

## Validation
- ✅ Confirmed HERDR_SOCKET_PATH is passed to hook subprocesses
- ✅ Socket API works (same protocol as Herdr's built-in integrations)
- ✅ CLI fallback preserved for edge cases

## Architecture Comparison

### Herdr Built-in Integrations (claude, codex)
```
Hook subprocess
  ├─ Receives: HERDR_SOCKET_PATH
  ├─ Uses: Direct socket connection
  └─ Pattern: Python script with socket client
```

### Our Integration (After This Decision)
```
Hook subprocess
  ├─ Receives: HERDR_SOCKET_PATH (primary)
  ├─ Receives: HERDR_BIN_PATH (sometimes, fallback)
  ├─ Uses: Socket first, CLI second
  └─ Pattern: Same as built-in integrations
```

## Related Decisions
- [ADR-001: Hooks-Only Architecture for Herdr-Vibe Integration](./ADR-001-hooks-only-architecture.md)
