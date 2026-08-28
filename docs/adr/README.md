# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for the Herdr-Vibe integration project.

## Purpose
ADRs document the "why" behind significant architectural choices. They provide context for future maintainers and prevent re-litigation of settled decisions.

## Structure

```
docs/adr/
├── README.md              # This file
├── DECISION-LOG.md        # Chronological record of all decisions
├── ADR-001-*.md          # First decision
├── ADR-002-*.md          # Second decision
└── ...
```

## Current ADRs

| Number | Title | Status | Date |
|--------|-------|--------|------|
| [ADR-001](ADR-001-hooks-only-architecture.md) | Hooks-Only Architecture for Herdr-Vibe Integration | ✅ Accepted | 2026-08-28 |
| [ADR-002](ADR-002-socket-api-over-cli.md) | Unix Socket API over CLI for Hook State Reporting | ✅ Accepted | 2026-08-28 |

## How to Add a New ADR

1. **Create the ADR file**: Copy the template below, fill in details
2. **Name it**: `ADR-XXX-title-in-kebab-case.md` (increment XXX sequentially)
3. **Update this table**: Add your ADR to the table above
4. **Update decision log**: Add entries to `DECISION-LOG.md`
5. **Link related ADRs**: Reference other ADRs if relevant

## ADR Template

```markdown
# ADR-XXX: [Short Title]

## Status
**Accepted** or **Proposed** or **Rejected** or **Deprecated**

## Context
[What is the problem we're trying to solve? What are the forces at play?]

## Decision
[What did we choose?]

## Consequences
### Positive
- [Good things that will happen]

### Negative
- [Trade-offs, bad things that might happen]

## Alternatives Considered
### Alternative 1
- **Rejected because:** [reason]

### Alternative 2
- **Rejected because:** [reason]

## Related Decisions
- [ADR-001](./ADR-001-*.md)
- [ADR-002](./ADR-002-*.md)
```

## Decision Timeline

For a complete chronological history, see [DECISION-LOG.md](DECISION-LOG.md).

### Major Phases

**Phase 1: Output Parsing (2026-08-26)**
- Attempted to parse Vibe's stdout/stderr
- Failed due to TTY detection issues
- **Outcome**: Rejected

**Phase 2: Hooks Architecture (2026-08-26 to 2026-08-28)**
- Switched to stdio: 'inherit' for TTY access
- Removed output parsing, relied on hooks
- Added agent session registration
- **Outcome**: Partially working, but environment variable issues

**Phase 3: Socket API (2026-08-28)**
- Discovered hook subprocesses missing HERDR_ENV, HERDR_BIN_PATH
- Switched to Unix socket API with CLI fallback
- **Outcome**: Fully working

## Status Definitions

| Status | Meaning |
|--------|---------|
| **Proposed** | Decision proposed, under discussion |
| **Accepted** | Decision agreed upon, implemented |
| **Rejected** | Decision considered but rejected |
| **Deprecated** | Previously accepted, now superseded |
| **Amended** | Accepted with modifications |

## Right Angles

The "right angles" approach means:
- **Clear structure**: Each ADR has defined sections (Context, Decision, Consequences, Alternatives)
- **Explicit trade-offs**: Document both positive and negative consequences
- **Historical context**: Record why alternatives were rejected
- **Traceability**: Link ADRs together to show decision evolution

This ensures decisions can be understood and revisited with proper context.
