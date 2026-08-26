# Herdr + Mistral Vibe Integration Plan

## Goal
Integrate **Mistral Vibe** as a custom agent in **Herdr** using Herdr's Socket API.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Herdr                               │
│  ┌─────────────┐  ┌─────────────────────────────────────┐ │
│  │   Pane      │  │  Socket API (local Unix domain)       │ │
│  │             │←─┤  - pane.report_agent                 │ │
│  │             │  │  - pane.report_agent_session         │ │
│  │             │  │  - pane.release_agent                │ │
│  └─────────────┘  └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ stdin/stdout
                          ▼
┌─────────────────────────────────────────────────────────┐
│                 Adapter Script (Node.js/Python)           │
│  1. Spawns: `vibe` CLI process                            │
│  2. Connects: to HERDR_SOCKET_PATH                        │
│  3. Reports: agent state (idle/working/done)              │
│  4. Forwards: I/O between Herdr pane and vibe process    │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ spawns
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Mistral Vibe CLI                        │
│  - Reads user input from stdin                             │
│  - Writes responses to stdout                              │
│  - Already terminal-compatible                            │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

### Herdr Requirements
- Herdr must be running (provides `HERDR_SOCKET_PATH` env var)
- Socket API docs: https://herdr.dev/docs/socket-api/
- Agent state reporting: `pane.report_agent`, `pane.report_agent_session`, `pane.release_agent`

### Mistral Vibe Requirements
- `vibe` CLI installed and in PATH
- Works as interactive terminal agent (reads stdin, writes stdout)

## Implementation Phases

### Phase 1: Research (1-2 hours)
- [ ] Review Herdr Socket API spec
- [ ] Test Herdr custom agent with simple echo script
- [ ] Verify Mistral Vibe CLI behavior (stdin/stdout)
- [ ] Identify state transition triggers in Vibe

### Phase 2: Minimal Adapter (2-4 hours)
- [ ] Create adapter script (Node.js for async socket I/O)
- [ ] Connect to Herdr socket
- [ ] Spawn `vibe` process
- [ ] Forward stdin/stdout between Herdr and Vibe
- [ ] Report basic state: idle → working → done

### Phase 3: State Detection (2-4 hours)
- [ ] Detect when Vibe is waiting for input (idle)
- [ ] Detect when Vibe is processing (working)
- [ ] Detect when Vibe completes task (done)
- [ ] Handle blocked state (if Vibe needs user input)

### Phase 4: Polish & Test (2-4 hours)
- [ ] Error handling
- [ ] Clean shutdown
- [ ] Herdr session management
- [ ] Documentation

## File Structure

```
herdr-vibe-integration/
├── README.md
├── PLAN.md
├── adapter/
│   ├── index.js          # Main adapter (Node.js)
│   ├── package.json
│   └── config.js         # Configuration
├── scripts/
│   ├── test-herdr.js     # Test Herdr socket connection
│   └── test-vibe.js      # Test Vibe CLI behavior
└── docs/
    └── DEVELOPMENT.md
```

## Socket API Quick Reference

From https://herdr.dev/docs/socket-api/:

```json
// Report agent state
{
  "method": "pane.report_agent",
  "params": {
    "state": "working|idle|done|blocked",
    "name": "vibe",
    "version": "1.0.0"
  }
}

// Report session
{
  "method": "pane.report_agent_session",
  "params": {
    "session_id": "unique-id",
    "agent_name": "vibe"
  }
}

// Release agent
{
  "method": "pane.release_agent",
  "params": {
    "session_id": "unique-id"
  }
}
```

## Vibe CLI Behavior

Need to verify:
- Does Vibe read from stdin? (Yes, interactive mode)
- Does Vibe write to stdout? (Yes)
- Can we detect state from output? (Need to test)
- Does Vibe support `--stdio` or similar? (Need to check)

## Success Criteria

1. Herdr recognizes `vibe` as a connected agent
2. Agent state updates correctly in Herdr UI
3. Input from Herdr pane reaches Vibe
4. Vibe output appears in Herdr pane
5. Multiple concurrent Vibe sessions work

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Herdr Socket API changes | Use documented stable methods |
| Vibe CLI behavior changes | Test with latest Vibe version |
| State detection is fragile | Use multiple signals (output patterns + timing) |
| Performance overhead | Use efficient streaming, avoid buffering |

## Next Steps

1. Read Herdr Socket API docs thoroughly
2. Write test script to connect to Herdr socket
3. Write test script to verify Vibe CLI I/O behavior
4. Build minimal adapter that just forwards I/O
5. Add state reporting
