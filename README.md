# herdr-vibe-integration

> Native Herdr integration for Mistral Vibe as a custom agent

## Status

Production Testing - Hooks-based architecture with automatic state reporting

---

## About

This integration allows Mistral Vibe to run as a first-class agent within [Herdr](https://herdr.dev/), with real-time state reporting in the Herdr sidebar.

**Architecture:** Uses Vibe's built-in hook system to report state changes (idle, working, blocked, done) to Herdr via Unix socket or CLI. See [docs/adr/](docs/adr/) for design details.

---

## Quick Start

```bash
# 1. Install dependencies and build
make deps build

# 2. Install the integration
make install

# 3. Start Herdr
herdr

# 4. In a Herdr pane, run:
vibe-herdr
```

Herdr will now display Vibe's agent state in the sidebar, updating automatically as Vibe processes requests, executes tools, and completes tasks.

---

## Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| [Herdr](https://herdr.dev/) | Latest | Terminal multiplexer with socket API |
| [Mistral Vibe CLI](https://mistral.ai/products/vibe/) | Latest | AI agent in your terminal |
| Node.js | >= 26.7.0 | Runs the TypeScript adapter |
| pnpm | >= 11.24.0 | Package management |
| Python | >= 3.x | Hook script execution |

---

## How It Works

Vibe's hook system triggers state updates:

| Hook Event | State Reported | Description |
|------------|----------------|-------------|
| `post_agent` | `idle` | Vibe finished generating a response |
| `pre_tool` | `working` | Tool execution starting |
| `post_tool` | `working` or `blocked` | Tool completed (success/failure/cancelled) |

The adapter supplements this with lifecycle reporting (initial idle, error states, cleanup).

Herdr Socket API methods used: `pane.report_agent`, `pane.report_agent_session`, `pane.release_agent`.

---

## Installation

### Automatic Installation

```bash
make install
```

This installs:
- `hooks.toml` -> `~/.vibe/hooks.toml`
- `herdr-agent-state.py` -> `~/.vibe/herdr-agent-state.py`
- Symlink `vibe-herdr` -> `adapter/dist/index.js`

### Manual Installation

```bash
make deps build
mkdir -p ~/.vibe
cp adapter/hooks.toml ~/.vibe/
cp adapter/herdr-agent-state.py ~/.vibe/
chmod +x ~/.vibe/herdr-agent-state.py
mkdir -p ~/.local/bin
ln -sf $(pwd)/adapter/dist/index.js ~/.local/bin/vibe-herdr
```

### Uninstall

```bash
make uninstall
```

---

## Usage

```bash
# In Herdr pane:
vibe-herdr

# Standalone (for testing the wrapper):
vibe-herdr
```

> **Note:** The wrapper auto-detects Herdr. Outside Herdr, it simply runs `vibe` normally — useful for verifying the wrapper itself.

---

## Development

### Build & Test

```bash
make help              # List all available commands
make deps              # Install Node.js dependencies
make build             # Compile TypeScript
make lint              # TypeScript lint + typecheck
make test              # Run integration tests
make test-all          # Unit + integration tests
make check             # Build + test everything
make doctor            # Check system and project health
```

### Clean

```bash
make clean             # Remove dist/
make clean-all         # Remove dist/ and node_modules/
make reset             # Full clean
```

### Quick Setup

```bash
make quickstart        # deps + build + install
```

### Testing with Herdr

```bash
make test-with-herdr   # Run tests with real Herdr instance
make herdr-env         # Show Herdr environment variables
make socket-path       # Show current Herdr socket path
make logs              # Show Herdr logs
```

---
## Configuration

### Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `HERDR_ENV` | Herdr | Set to `1` when running in Herdr |
| `HERDR_PANE_ID` | Herdr | Pane identifier (e.g., `w1:p1`) |
| `HERDR_BIN_PATH` | Herdr | Path to herdr CLI binary |
| `HERDR_SOCKET_PATH` | Herdr | Unix socket path |

### Hook Configuration

Edit `~/.vibe/hooks.toml` to customize hook behavior. Default reports on `post_agent`, `pre_tool`, and `post_tool` events.

---
## Troubleshooting

### State not updating in Herdr

```bash
# Verify environment
make herdr-env

# Verify installation
make verify

# Test socket connectivity
make test-socket-server
```

### Build fails

```bash
make clean-all
make deps
```

### Vibe TUI not working

Ensure you're using the `vibe-herdr` wrapper, not running `vibe` directly. The wrapper preserves TTY access.

---
## Architecture Decisions

See [docs/adr/](docs/adr/) for Architecture Decision Records.

---
## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/xxx`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

Pre-commit hooks via [lefthook](https://github.com/evilmartians/lefthook):

```bash
pnpm exec lefthook install
```

---
## License

MIT
