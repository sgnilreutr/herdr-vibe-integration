# herdr-vibe-integration

> Custom integration to run Mistral Vibe as an agent in Herdr

## Status

🟡 **Planning Phase** - See [PLAN.md](PLAN.md) for detailed roadmap.

## Quick Start (Future)

```bash
# Install the adapter
npm install

# Run with Herdr
herdr --agent ./adapter/index.js
```

## Project Structure

- `adapter/` - Main integration adapter (Node.js)
- `scripts/` - Test and development scripts
- `docs/` - Additional documentation

## Requirements

- [Herdr](https://herdr.dev/) (provides socket API)
- [Mistral Vibe CLI](https://mistral.ai/products/vibe/) (`vibe` in PATH)
- Node.js 18+ (for adapter)

## Development

See [PLAN.md](PLAN.md) for implementation details.

## License

MIT
