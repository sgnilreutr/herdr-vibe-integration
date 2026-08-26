# Herdr + Mistral Vibe Integration - Option C: Proper Integration Plan

## Goal

Build a **native Herdr integration** for Mistral Vibe that follows Herdr's plugin pattern, using Vibe's built-in hooks system to report state to Herdr via Unix domain socket.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Herdr                               │
│  ┌─────────────┐  ┌─────────────────────────────────────┐ │
│  │   Pane      │  │  Socket API (Unix domain socket)       │ │
│  │             │←─┤  - pane.report_agent                  │ │
│  │             │  │  - pane.report_agent_session          │ │
│  └─────────────┘  └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ Unix socket (HERDR_SOCKET_PATH)
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Vibe Hook Script (Python)                    │
│  File: ~/.vibe/herdr-agent-state.py                        │
│  - Listens to Vibe hook events via stdin (JSON)          │
│  - Reports state to Herdr via socket                     │
│  - Detects: idle, working, blocked, done                 │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ spawns (via hooks.toml)
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Mistral Vibe CLI                        │
│  - Loads hooks from ~/.vibe/hooks.toml                   │
│  - Executes hook scripts on events                       │
│  - Passes JSON invocation data to stdin                 │
└─────────────────────────────────────────────────────────┘
```

## Background: How Vibe Hooks Work

From Vibe's source code (`vibe/core/hooks/`):

1. **Hook Configuration**: `hooks.toml` files in:
   - `~/.vibe/hooks.toml` (user-level)
   - `<project>/.vibe/hooks.toml` (project-level)

2. **Hook Types**:
   - `POST_AGENT` - After agent generates a response
   - `PRE_TOOL` - Before a tool is executed
   - `POST_TOOL` - After a tool completes

3. **Hook Execution**:
   - Vibe spawns the hook command as a subprocess
   - Passes JSON invocation data to stdin
   - Expects JSON response on stdout (optional)
   - Timeout: configurable (default 60s)

## File Structure

```
herdr-vibe-integration/
├── README.md
├── PLAN-OPTION-C.md          # This file
├── adapter/
│   ├── index.ts              # Wrapper adapter (kept for fallback)
│   ├── herdr-agent-state.py  # ✨ NEW: Herdr state reporter (Python)
│   ├── hooks.toml            # ✨ NEW: Vibe hook configuration
│   ├── install.py            # ✨ NEW: Installation script
│   ├── package.json
│   └── dist/
│       └── index.js
├── scripts/
│   └── ...
└── docs/
    └── ...
```

## Implementation

### 1. Hook Script (`herdr-agent-state.py`)

**Location**: `~/.vibe/herdr-agent-state.py`

**Responsibilities**:
- Read hook invocation JSON from stdin
- Parse hook type (`POST_AGENT`, `PRE_TOOL`, `POST_TOOL`)
- Report state to Herdr via Unix socket
- Use Herdr's socket API methods:
  - `pane.report_agent` - Report current state
  - `pane.report_agent_session` - Report session info
  - `pane.release_agent` - Release agent on exit

**Key Functions**:
```python
def send_to_herdr(method: str, params: dict) -> bool
def report_state(state: str, message: str = "") -> None
def report_agent_session(session_id: str) -> None
def handle_post_agent(hook_data: dict) -> None
def handle_pre_tool(hook_data: dict) -> None
def handle_post_tool(hook_data: dict) -> None
```

### 2. Hook Configuration (`hooks.toml`)

**Location**: `~/.vibe/hooks.toml`

**Content**:
```toml
[[hooks]]
name = "herdr-post-agent"
type = "post_agent"
command = "python3 ~/.vibe/herdr-agent-state.py"
timeout = 5.0

[[hooks]]
name = "herdr-pre-tool"
type = "pre_tool"
command = "python3 ~/.vibe/herdr-agent-state.py"
timeout = 5.0

[[hooks]]
name = "herdr-post-tool"
type = "post_tool"
command = "python3 ~/.vibe/herdr-agent-state.py"
timeout = 5.0
```

### 3. State Detection

**Reused from TypeScript adapter**:
- Pattern matching for: idle, working, blocked, done
- Patterns match Vibe's TUI output (spinners, prompts, etc.)
- fall back to hook type-based detection

## Socket API Communication

**Request Format** (JSON sent to Herdr socket):
```json
{
  "id": "herdr:vibe:123456:abc123",
  "method": "pane.report_agent",
  "params": {
    "pane_id": "w1:p1",
    "source": "herdr:vibe",
    "agent": "vibe",
    "state": "working",
    "message": "Generating response",
    "seq": 123456
  }
}
```

**Socket Path**: From `HERDR_SOCKET_PATH` environment variable

## Installation

### Manual Installation

```bash
# 1. Copy files to ~/.vibe/
cp adapter/herdr-agent-state.py ~/.vibe/herdr-agent-state.py
cp adapter/hooks.toml ~/.vibe/hooks.toml

# 2. Make executable
chmod +x ~/.vibe/herdr-agent-state.py

# 3. Verify
ls -la ~/.vibe/herdr-agent-state.py ~/.vibe/hooks.toml
```

### Script Installation

```bash
# Run the installation script
python3 adapter/install.py

# Or to uninstall
python3 adapter/install.py --uninstall
```

## State Mapping

| Vibe State | Herdr State | Trigger |
|------------|-------------|---------|
| Starting | idle | Initial hook invocation |
| Processing prompt | working | POST_AGENT (start) |
| Generating response | working | POST_AGENT (during) |
| Running tool | working | PRE_TOOL |
| Tool completed | working | POST_TOOL (success) |
| Tool failed | blocked | POST_TOOL (failure) |
| Ready for input | idle | POST_AGENT (complete) |
| Permission needed | blocked | PRE_TOOL (needs approval) |
| Task complete | done | Detected in output |

## Testing

### Test 1: Hook Invocation
```bash
# Simulate a hook invocation
echo '{"hook_event_name": "POST_AGENT", "session_id": "test-123"}' \
  | HERDR_ENV=1 HERDR_PANE_ID=w1:p1 HERDR_SOCKET_PATH=/tmp/herdr.sock \
  python3 ~/.vibe/herdr-agent-state.py
```

### Test 2: Full Integration
```bash
# 1. Start Herdr in one terminal
herdr

# 2. In a Herdr pane, run Vibe
vibe

# 3. Verify Herdr sidebar shows Vibe's state
```

### Test 3: State Transitions
```bash
# In Vibe:
# - Type a prompt
# - Check Herdr sidebar: should show "working"
# - After response: should show "idle"
# - Use a tool: should show "working" then "idle"
```

## Comparison with Other Options

| Aspect | Option A (Wrapper) | Option B (Enhanced Wrapper) | Option C (Native Integration) |
|--------|-------------------|---------------------------|------------------------------|
| Complexity | Low | Medium | Medium |
| Herdr Integration | ❌ No | ⚠️ Partial | ✅ Full |
| Socket API | ❌ CLI calls | ⚠️ Added | ✅ Native |
| Vibe Hooks | ❌ No | ❌ No | ✅ Yes |
| Auto-detection | ❌ Manual | ❌ Manual | ✅ Automatic |
| Sidebar State | ❌ No | ✅ Yes | ✅ Yes |
| Maintenance | Easy | Medium | Medium |
| Upstream Potential | Low | Low | ✅ High |

## Fallback Strategy

If Vibe's hooks system doesn't work as expected (e.g., Vibe doesn't load hooks.toml from expected location), we can fall back to:

1. **Wrapper mode**: Use the TypeScript adapter as a wrapper
2. **Environment variable**: Set `VIBE_HOOKS_PATH` to point to our hooks.toml
3. **Patch Vibe**: Submit a PR to Vibe to support custom hooks directories

## Next Steps

1. ✅ Create `herdr-agent-state.py`
2. ✅ Create `hooks.toml`
3. ✅ Create `install.py`
4. ⏳ **Test hook invocation locally**
5. ⏳ **Test in Herdr**
6. ⏳ **Fix any issues**
7. ⏳ **Document installation**
8. ⏳ **Package for distribution**

## Files to Create

- [x] `adapter/herdr-agent-state.py` - Herdr state reporter
- [x] `adapter/hooks.toml` - Vibe hook configuration
- [x] `adapter/install.py` - Installation script
- [ ] `README.md` (update) - Installation instructions
- [ ] `scripts/test-hook.sh` - Test script for hooks
- [ ] `scripts/test-socket.py` - Test Herdr socket communication

## Success Criteria

1. ✅ Vibe starts in Herdr without hanging
2. ✅ Herdr sidebar shows Vibe's state (idle/working/blocked/done)
3. ✅ State transitions are reported correctly
4. ✅ Hooks are invoked on Vibe events
5. ✅ Installation is simple and reliable
6. ✅ Uninstallation is clean

## References

- Herdr Socket API: https://herdr.dev/docs/socket-api/
- Vibe Hooks: `vibe/core/hooks/`
- Claude Integration: `~/.claude/hooks/herdr-agent-state.sh`
- Opencode Integration: `~/.config/opencode/plugins/herdr-agent-state.js`
