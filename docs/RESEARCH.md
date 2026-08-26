# Research Findings

## Herdr Socket API & Integration

### Key Documentation
- [Herdr Socket API](https://herdr.dev/docs/socket-api/)
- [Herdr Integrations](https://herdr.dev/docs/integrations/)

### Environment Variables (Inherited by Pane Processes)
When Herdr launches a pane, it injects these environment variables:
```
HERDR_ENV=1
HERDR_SOCKET_PATH=/path/to/herdr.sock
HERDR_BIN_PATH=/path/to/herdr
HERDR_WORKSPACE_ID=w1
HERDR_TAB_ID=w1:t1
HERDR_PANE_ID=w1:p1
```

### State Reporting (CLI Method - Recommended)
Herdr provides CLI wrappers for state reporting. From a pane process:

```bash
# Report agent state
$HERDR_BIN_PATH pane report-agent $HERDR_PANE_ID \
  --source custom:vibe \
  --agent vibe \
  --state working \
  --message "Processing request"

# Report session (optional)
$HERDR_BIN_PATH pane report-agent-session $HERDR_PANE_ID \
  --source custom:vibe \
  --agent vibe \
  --agent-session-id "session-123"

# Release agent on exit
$HERDR_BIN_PATH pane release-agent $HERDR_PANE_ID \
  --source custom:vibe \
  --agent vibe
```

**Valid states:** `idle`, `working`, `blocked`, `done`, `unknown`

**Important:** 
- Only report when `HERDR_ENV=1` and required vars are present
- Keep `--source` stable and unique (e.g., `custom:vibe`)
- Use `--seq` for ordering if reports can arrive out of order
- Report `idle` when ready for input, `blocked` when needs user decision

### Integration Types
Herdr distinguishes between:

1. **Lifecycle authority** (report state): Pi, OMP, Kimi Code CLI, OpenCode, Kilo Code CLI, MastraCode
2. **Session identity** (report session for restore): Claude Code, Codex, GitHub Copilot CLI, etc.
3. **Custom integrations** - Can report both state and session

For Mistral Vibe, we want **Lifecycle authority** + **Session identity**.

### Socket API (Raw - For Advanced Use)
The socket uses newline-delimited JSON:
```json
{"id":"req_1","method":"pane.report_agent","params":{"pane_id":"w1:p1","source":"custom:vibe","agent":"vibe","state":"working"}}
```

Socket paths:
- Default: `~/.config/herdr/herdr.sock`
- Named sessions: `~/.config/herdr/sessions/<name>/herdr.sock`

Resolution order:
1. `--session <name>` CLI flag
2. `HERDR_SOCKET_PATH` env var
3. `HERDR_SESSION=<name>` env var
4. Default session socket

---

## Mistral Vibe CLI

### Documentation
- [Mistral Vibe CLI Docs](https://docs.mistral.ai/vibe/code/cli/work-with-cli)
- [DeepWiki: CLI Interface](https://deepwiki.com/mistralai/mistral-vibe/3.1-cli-interface-(vibe))

### Modes

#### Interactive Mode (Default)
- Launched with: `vibe` (no arguments)
- Uses Textual TUI
- Rich terminal interface
- User can chat, use slash commands, switch agents with Shift+Tab
- **Stdin handling:** If stdin is not a TTY, reads piped content as prompt, then resets stdin to `/dev/tty`

#### Programmatic Mode
- Launched with: `vibe --prompt "..."` or `echo "..." | vibe`
- No TUI, headless execution
- Outputs to stdout
- Exits after processing
- **Not suitable** for Herdr integration (we want interactive TUI)

### Key Behaviors
- Stdin: If not TTY, reads piped input as initial prompt
- Stdout: In programmatic mode, writes output; in interactive mode, renders in TUI
- Shell sessions: Managed sessions return session_id, inline output, cursor, log path

### MCP Support
- Mistral Vibe supports MCP (Model Context Protocol)
- Can configure MCP servers in `config.toml`
- Tools from MCP servers become available to Vibe
- See: [MCP Integration](https://docs.mistral.ai/vibe/code/cli/mcp-servers)

---

## Integration Strategy

### Approach: Wrapper Script with Heuristics

**Architecture:**
```
Herdr Pane
  ├─ Env: HERDR_ENV=1, HERDR_PANE_ID=w1:p1, HERDR_BIN_PATH=...
  └─ Launches: /path/to/adapter.js
       ├─ Detects Herdr environment
       ├─ Reports: pane.report_agent (idle)
       ├─ Spawns: vibe (as subprocess with PTY)
       ├─ Monitors: Vibe's output for state patterns
       └─ Reports: state changes to Herdr
```

**State Detection Heuristics:**
Since Vibe runs as a TUI, we need to detect state from its output:

| State | Detection Pattern | Example |
|-------|-------------------|---------|
| **idle** | Vibe displays input prompt | `> `, `$ `, `vibe> `, `Enter prompt:` |
| **working** | Vibe is generating output | Streaming tokens, thinking indicators |
| **blocked** | Vibe asks for user decision | `Allow? (y/n)`, `Please confirm` |
| **done** | Vibe indicates completion | `Task complete`, `Done.` |

**Implementation Options:**

#### Option 1: Simple Shell Wrapper (Limited)
```bash
#!/bin/bash
if [ "$HERDR_ENV" = "1" ]; then
  # Report initial state
  "$HERDR_BIN_PATH" pane report-agent "$HERDR_PANE_ID" \
    --source custom:vibe --agent vibe --state idle
  
  # Run Vibe
  vibe
  
  # Release on exit
  "$HERDR_BIN_PATH" pane release-agent "$HERDR_PANE_ID" \
    --source custom:vibe --agent vibe
else
  exec vibe
fi
```
**Limitation:** No state detection during Vibe execution.

#### Option 2: Node.js Wrapper with PTY Monitoring (Recommended)
- Use Node.js `node-pty` or `pty.js` to spawn Vibe with a pseudo-terminal
- Read Vibe's output in real-time
- Apply regex patterns to detect state changes
- Report to Herdr via CLI calls or raw socket

**Advantages:**
- Full control over I/O
- Real-time state detection
- Can inject input if needed
- Cross-platform (with proper PTY library)

#### Option 3: Raw Socket API Client
- Connect directly to Herdr's socket
- Send JSON-RPC messages for state reporting
- More complex but more efficient

---

## Recommended Implementation

**Use Option 2: Node.js wrapper with PTY monitoring**

### Why Node.js?
- Async I/O handling
- Good PTY libraries available (`node-pty`, `@herdr/node-pty`)
- Easy JSON handling for socket API if needed
- Cross-platform support

### File Structure
```
adapter/
├── index.js              # Main wrapper entry point
├── pty-monitor.js        # PTY monitoring logic
├── state-detector.js     # State pattern matching
├── herdr-client.js       # Herdr CLI/socket client
└── package.json
```

### Dependencies
```json
{
  "dependencies": {
    "node-pty": "^1.0.0",
    "@herdr/node-pty": "^1.0.0"  // If available, Herdr's own PTY
  }
}
```

### State Detection Patterns (Tentative)

```javascript
const STATE_PATTERNS = {
  idle: [
    /^> /,                    // Simple prompt
    /^\$/,
    /^vibe> /,
    /Enter prompt: /i,
    /^\n$/                     // Empty line (might indicate ready)
  ],
  working: [
    /^Thinking/i,
    /^Generating/i,
    /^\.\.\./,                // Spinner
    /^[▰▱▱▱]/,                // Progress bar
    /^▉/                      // Block characters
  ],
  blocked: [
    /Allow\? \[y\/n\]/i,
    /Please confirm/i,
    /Do you want to proceed/i
  ],
  done: [
    /^Task complete/i,
    /^Done\./i,
    /^✓/,
    /^Success/i
  ]
};
```

### Next Steps
1. Test basic Herdr socket connection
2. Test Mistral Vibe in a PTY to understand its output patterns
3. Build minimal Node.js wrapper
4. Implement state detection
5. Test end-to-end
