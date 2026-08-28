# ADR-001: Hooks-Only Architecture for Herdr-Vibe Integration

## Status
**Accepted** - Implemented and deployed

## Context
The initial implementation of the Herdr-Vibe integration used output parsing to detect Vibe's state by monitoring stdout/stderr streams. This approach had a critical flaw: piping stdout/stderr broke Vibe's TTY detection, which prevented:

1. Vibe's interactive prompt from rendering correctly
2. Vibe's hook system from firing (POST_AGENT, PRE_TOOL, POST_TOOL)
3. State updates from reaching Herdr
4. The adapter appeared to hang at "Running in Herdr pane: [pane-id]"

### The Root Cause
```typescript
// BEFORE (broken)
const vibe = spawn('vibe', process.argv.slice(2), {
  stdio: ['inherit', 'pipe', 'pipe']  // stdout/stderr piped
});
```

Vibe requires a real TTY for interactive mode. When stdout/stderr are piped, Vibe detects it is NOT running in a TTY and disables:
- Interactive TUI rendering
- Hook system execution

Without hooks firing, there was no way to detect state changes.

## Decision
Adopt a **hooks-only architecture** that:

1. **Gives Vibe full TTY access** - Use `stdio: 'inherit'` so Vibe detects a real terminal
2. **Relies on Vibe's native hook system** - POST_AGENT, PRE_TOOL, POST_TOOL hooks report state
3. **Removes all output parsing** - Delete state pattern matching, ANSI stripping, and line processing
4. **Simplifies the adapter** - Only handles Herdr environment detection, initial state, and cleanup

### Architecture Diagram
```
Herdr Pane (TTY)
  │
  ├─ Env: HERDR_ENV=1, HERDR_PANE_ID=w1:p1, HERDR_SOCKET_PATH=...
  │
  └─ adapter (vibe-herdr)
       ├─ 1. Detect Herdr environment
       ├─ 2. Report agent session (pane.report_agent_session)
       ├─ 3. Report initial idle state (pane.report_agent)
       ├─ 4. Spawn: vibe (stdio: 'inherit' → real TTY)
       │    │
       │    └─ Vibe CLI (Python TUI)
       │         │
       │         ├─ Hook fires: POST_AGENT → herdr-agent-state.py
       │         ├─ Hook fires: PRE_TOOL → herdr-agent-state.py
       │         └─ Hook fires: POST_TOOL → herdr-agent-state.py
       │              │
       │              └─ Report state to Herdr via socket/CLI
       │
       └─ 5. On exit: release agent (pane.release_agent)
```

## Consequences

### Positive
- ✅ Vibe's TUI works correctly (TTY detection passes)
- ✅ Vibe's hooks fire reliably
- ✅ State updates flow to Herdr in real-time
- ✅ No adapter hanging
- ✅ Simpler code (removed ~100 lines of output parsing)
- ✅ More maintainable (relies on Vibe's official hook API)

### Negative
- ⚠️ Requires Vibe hooks.toml to be installed in ~/.vibe/
- ⚠️ Hook script must be installed and executable in ~/.vibe/
- ⚠️ Less control over state detection (dependent on Vibe's hook events)

## Alternatives Considered

### Alternative 1: PTY Monitoring with Output Parsing
Use node-pty to give Vibe a pseudo-terminal while still reading output.

**Rejected because:**
- Complex to implement correctly across platforms
- Requires native dependencies (node-pty)
- Still fragile - TUI output is hard to parse reliably
- Hooks are more reliable when available

### Alternative 2: Vibe Programmatic Mode
Run Vibe in `--prompt` mode and parse JSON output.

**Rejected because:**
- No TUI - users lose Vibe's interactive features
- Doesn't work for multi-turn conversations
- Not the intended use case

## Implementation Details

### Files Changed
| File | Change |
|------|--------|
| `adapter/src/index.ts` | Removed output parsing, added agent session reporting, use `stdio: 'inherit'` |
| `adapter/src/index.test.ts` | Updated tests for new architecture |
| `adapter/herdr-agent-state.py` | Switched to socket API with CLI fallback, check HERDR_PANE_ID instead of HERDR_ENV |
| `adapter/hooks.toml` | Unchanged (hook configuration) |
| `adapter/package.json` | Added vitest for testing |

### State Reporting Flow
```
1. Adapter starts in Herdr pane
2. Adapter: report_agent_session() → Herdr knows about agent
3. Adapter: report_state('idle') → Initial state
4. Adapter: spawn vibe with stdio: 'inherit'
5. User interacts with Vibe
6. Vibe fires POST_AGENT/PRE_TOOL/POST_TOOL hooks
7. Hook script: report_state('working'/'idle'/'blocked') to Herdr
8. Herdr updates agents pane
```

## Validation
- ✅ Tested: Vibe TUI renders correctly
- ✅ Tested: Hooks fire (verified via /tmp/hook-call.log)
- ✅ Tested: State updates appear in Herdr agents pane
- ✅ Tested: Working → Idle transitions
- ✅ Tested: Tool execution state changes

## Related Decisions
- [ADR-002: Socket API over CLI for Hook Reporting](./ADR-002-socket-api-over-cli.md)
