# Decision Log

This document tracks the evolution of architectural decisions for the Herdr-Vibe integration. Each entry documents a significant decision point, the reasoning, and the outcome.

## Format
```
## [Date] - [Decision Title]
**Status:** [Proposed/Accepted/Rejected/Deprecated]  
**Related ADR:** [ADR-XXX] if applicable  
**Context:** Brief background  
**Decision:** What was chosen  
**Rationale:** Why this choice  
**Impact:** Results and consequences  
**Reversibility:** Can this be changed later?
```

---

## 2026-08-26 - Initial Approach: Output Parsing with Piped Stdout/Stderr
**Status:** Rejected  
**Related ADR:** None (pre-ADR era)  

**Context:** 
First attempt at Herdr-Vibe integration. The adapter spawned Vibe with `stdio: ['inherit', 'pipe', 'pipe']` to capture stdout/stderr, then parsed output with regex patterns to detect state changes (idle, working, blocked, done).

**Decision:** 
Parse Vibe's output by monitoring piped stdout/stderr streams and matching against state patterns.

**Rationale:** 
- Simple to implement
- Direct control over state detection
- No dependencies on Vibe internals

**Impact:** 
- ❌ **CRITICAL FAILURE**: Piping stdout/stderr broke Vibe's TTY detection
- Vibe TUI would not render correctly
- Vibe's hook system would NOT fire (hooks only fire in TTY mode)
- Adapter appeared to hang at "Running in Herdr pane: [pane-id]"
- No state updates reached Herdr

**Reversibility:** 
Fully reversible - simply stop piping stdout/stderr.

---

## 2026-08-26 - Iteration 1: Switch to stdio: 'inherit'
**Status:** Partially Accepted  
**Related ADR:** [ADR-001](ADR-001-hooks-only-architecture.md)  

**Context:** 
Recognized that TTY detection was the blocker. Switched to `stdio: 'inherit'` to give Vibe a real terminal.

**Decision:** 
Change Vibe spawn to use `stdio: 'inherit'` for full TTY access.

**Rationale:** 
- Vibe requires TTY for interactive mode and hook execution
- This is the minimum change to unblock hooks

**Impact:** 
- ✅ Vibe TUI now renders correctly
- ✅ Vibe hooks now fire (POST_AGENT, PRE_TOOL, POST_TOOL)
- ✅ Adapter no longer hangs
- ⚠️ State updates still not reaching Herdr (different issue)

**Reversibility:** 
Fully reversible.

---

## 2026-08-27 - Iteration 2: Remove Output Parsing, Rely on Hooks
**Status:** Accepted  
**Related ADR:** [ADR-001](ADR-001-hooks-only-architecture.md)  

**Context:** 
With TTY working, hooks now fire but state updates were still not appearing in Herdr. Realized output parsing was unnecessary complexity.

**Decision:** 
- Remove all output parsing code from adapter (STATE_PATTERNS, stripAnsiCodes, detectStateFromLine, processOutput)
- Simplify adapter to only: detect Herdr, report initial state, spawn Vibe, handle cleanup
- Rely entirely on Vibe's hook system for state reporting

**Rationale:** 
- Hooks are the official Vibe API for state change notifications
- More reliable than parsing TUI output
- Simpler code, fewer moving parts
- Matches Herdr's built-in integration patterns

**Impact:** 
- ✅ Cleaner, more maintainable code
- ✅ Hooks fire correctly (verified via /tmp/hook-call.log)
- ⚠️ State updates STILL not reaching Herdr (environment variable issue)

**Reversibility:** 
Could add output parsing back, but unnecessary.

---

## 2026-08-28 - Iteration 3: Agent Session Registration
**Status:** Accepted  
**Related ADR:** [ADR-001](ADR-001-hooks-only-architecture.md)  

**Context:** 
Debugging revealed Herdr was auto-detecting Vibe as an agent with no source, while our hooks were reporting to `source: herdr:vibe`. These were treated as separate agents.

**Decision:** 
Add `reportAgentSession()` call in adapter BEFORE spawning Vibe, ensuring Herdr uses our custom agent identity instead of creating a duplicate auto-detected entry.

**Rationale:** 
- Herdr's auto-detection creates agent without source
- Our state reports go to agent with source=herdr:vibe
- Registering session first ensures Herdr matches our reports to the correct agent

**Impact:** 
- ✅ Herdr now has a single vibe agent with proper session
- State reports now target the correct agent
- 
**Reversibility:** 
Fully reversible.

---

## 2026-08-28 - Issue Discovered: Missing Environment in Hook Subprocesses
**Status:** Problem Identified  
**Related ADR:** [ADR-002](ADR-002-socket-api-over-cli.md)  

**Context:** 
From `/tmp/hook-call.log`, confirmed:
- Hooks ARE firing (PRE_TOOL, POST_TOOL)
- `HERDR_PANE_ID` IS passed to hook subprocesses
- `HERDR_ENV` and `HERDR_BIN_PATH` are NOT passed

Hook script was checking for `HERDR_ENV == "1"` and exiting early.

**Impact:** 
- Hook script exits before reporting state
- State updates never reach Herdr despite hooks firing

---

## 2026-08-28 - Iteration 4: Check HERDR_PANE_ID Instead of HERDR_ENV
**Status:** Accepted  
**Related ADR:** [ADR-002](ADR-002-socket-api-over-cli.md)  

**Context:** 
Since HERDR_PANE_ID is reliably passed but HERDR_ENV is not, we need a different check.

**Decision:** 
Change hook script check from `HERDR_ENV == "1"` to `HERDR_PANE_ID` exists.

**Rationale:** 
- HERDR_PANE_ID is the minimum required identifier anyway
- If we have pane_id, we can report state
- More robust check

**Impact:** 
- ✅ Hook script no longer exits early
- ⚠️ Still fails if HERDR_BIN_PATH is missing (CLI method)

---

## 2026-08-28 - Iteration 5: Switch to Socket API
**Status:** Accepted  
**Related ADR:** [ADR-002](ADR-002-socket-api-over-cli.md)  

**Context:** 
CLI method requires HERDR_BIN_PATH which may not be passed to hook subprocesses. Need a method that only requires HERDR_SOCKET_PATH (which IS passed).

**Decision:** 
Rewrite herdr-agent-state.py to use Unix domain socket API as primary method, with CLI as fallback.

**Rationale:** 
- HERDR_SOCKET_PATH is reliably passed to hook subprocesses
- Socket API is what Herdr's built-in integrations use
- Lower latency (direct IPC vs process spawning)
- More robust

**Impact:** 
- ✅ State reports now work even without HERDR_BIN_PATH
- ✅ Matches Herdr's built-in integration patterns
- ✅ Full end-to-end state reporting verified

**Reversibility:** 
Could revert to CLI-only, but would be less robust.

---

## Current State (2026-08-28)

### Architecture
```
Adapter (vibe-herdr)
  ├─ Detect Herdr environment
  ├─ Report agent session (socket/CLI)
  ├─ Report initial idle state (socket/CLI)
  ├─ Spawn Vibe with stdio: 'inherit'
  │
  └─ Vibe CLI
       ├─ Hook: POST_AGENT → herdr-agent-state.py
       ├─ Hook: PRE_TOOL → herdr-agent-state.py
       └─ Hook: POST_TOOL → herdr-agent-state.py
            └─ Report via socket (primary) or CLI (fallback)
```

### Validated Behaviors
- ✅ Vibe TUI renders correctly
- ✅ Hooks fire (PRE_TOOL, POST_TOOL, POST_AGENT)
- ✅ Hook script executes successfully
- ✅ State reports reach Herdr
- ✅ Agents pane shows correct states (idle, working, blocked)

### Remaining Questions
- Does POST_AGENT reliably fire for all Vibe responses?
- Are there edge cases where hooks don't fire?
- Should we add session_id reporting for state persistence?

---

## Lessons Learned

1. **TTY Detection is Critical**: Vibe's interactive features (TUI, hooks) require a real TTY. Never pipe stdout/stderr when running Vibe interactively.

2. **Hook Environment is Partial**: Vibe's hook subprocesses don't receive all parent environment variables. Design for this.

3. **Socket API is Superior**: Herdr's Unix socket API is more reliable than CLI for subprocess communication. Use it when possible.

4. **Agent Session First**: Register the agent session before spawning the agent process to prevent duplicate entries from auto-detection.

5. **Debug Logging is Essential**: The `/tmp/hook-call.log` was critical in diagnosing that hooks WERE firing but environment variables were missing.

---

## Future Considerations

### Potential Improvements
- [ ] Add session_id reporting for state persistence across restarts
- [ ] Handle edge cases where hooks might not fire
- [ ] Add timeout/retry logic for socket connections
- [ ] Consider using Herdr's official integration framework (if available)

### Monitoring
- [ ] Log state transitions for debugging
- [ ] Track hook fire frequency and timing
- [ ] Monitor for missed state updates

### Documentation
- [x] ADR-001: Hooks-only architecture decision
- [x] ADR-002: Socket API over CLI decision
- [ ] ADR-003: Agent session registration timing
