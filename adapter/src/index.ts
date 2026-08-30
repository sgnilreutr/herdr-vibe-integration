#!/usr/bin/env node

/**
 * Herdr Integration Adapter for Mistral Vibe
 *
 * Hooks-only architecture (see docs/adr/ADR-001-hooks-only-architecture.md).
 *
 * Architecture:
 * 1. Wrapper detects Herdr environment
 * 2. Reports initial idle state
 * 3. Runs Vibe with stdio: 'inherit' so its TTY-dependent TUI and hook
 *    system both work (piping stdout/stderr breaks both - see ADR-001)
 * 4. Hooks (via hooks.toml + herdr-agent-state.py) report all state changes
 * 5. Handles cleanup on exit, waiting for the release report to actually
 *    reach Herdr before the process exits
 */

import { spawn } from "node:child_process";
import { createConnection } from "node:net";
import { randomBytes } from "node:crypto";

// Configuration
export const SOURCE = "herdr:vibe";
export const AGENT = "vibe";

// Herdr environment variables
interface HerdrEnv {
  paneId: string;
  herdrBin: string;
  socketPath?: string;
}

/**
 * Check if we're running inside Herdr
 */
export function isInHerdr(): boolean {
  return (
    process.env.HERDR_ENV === "1" &&
    Boolean(process.env.HERDR_PANE_ID) &&
    Boolean(process.env.HERDR_BIN_PATH)
  );
}

/**
 * Get Herdr environment variables
 */
export function getHerdrEnv(): HerdrEnv {
  return {
    paneId: process.env.HERDR_PANE_ID || "",
    herdrBin: process.env.HERDR_BIN_PATH || "",
    socketPath: process.env.HERDR_SOCKET_PATH,
  };
}

// Monotonic sequence counter so Herdr can order our reports and doesn't
// silently drop out-of-order ones (see herdrdev/herdr#667).
let seqCounter = 0;
function nextSeq(): number {
  seqCounter += 1;
  return seqCounter;
}

/**
 * Report agent state to Herdr via CLI
 */
function reportState(state: string, message: string = ""): void {
  const { paneId, herdrBin } = getHerdrEnv();

  const args: string[] = [
    "pane",
    "report-agent",
    paneId,
    "--source",
    SOURCE,
    "--agent",
    AGENT,
    "--state",
    state,
  ];

  if (message) {
    args.push("--message", message);
  }

  try {
    const proc = spawn(herdrBin, args, { stdio: "ignore", detached: true });
    proc.unref();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] State report failed: ${error.message}`);
  }
}

/**
 * Report agent session to Herdr
 */
function reportAgentSession(sessionId?: string): void {
  const { paneId, herdrBin } = getHerdrEnv();

  const args: string[] = [
    "pane",
    "report-agent-session",
    paneId,
    "--source",
    SOURCE,
    "--agent",
    AGENT,
  ];

  if (sessionId) {
    args.push("--agent-session-id", sessionId);
  }

  try {
    const proc = spawn(herdrBin, args, { stdio: "ignore", detached: true });
    proc.unref();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] Agent session report failed: ${error.message}`);
  }
}

/**
 * Release agent on exit (synchronous CLI call - safe to use in exit paths
 * since spawnSync blocks until the process completes)
 */
function releaseAgent(): void {
  const { paneId, herdrBin } = getHerdrEnv();

  try {
    const proc = spawn(
      herdrBin,
      ["pane", "release-agent", paneId, "--source", SOURCE, "--agent", AGENT],
      { stdio: "ignore", detached: true },
    );
    proc.unref();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] Release failed: ${error.message}`);
  }
}

/**
 * Send a JSON-RPC request to Herdr via Unix socket. Returns a promise that
 * resolves once the write has been flushed (or the connection failed), so
 * callers that need the report to land before the process exits can await it.
 */
function sendToSocket(method: string, params: Record<string, unknown>): Promise<void> {
  const { paneId, socketPath } = getHerdrEnv();

  if (!socketPath) {
    console.error("[herdr-vibe] No socket path for socket API");
    return Promise.resolve();
  }

  const requestId = `${SOURCE}:${Date.now()}:${randomBytes(3).toString("hex")}`;
  const request = {
    id: requestId,
    method,
    params: {
      ...params,
      pane_id: paneId,
      source: SOURCE,
      agent: AGENT,
      seq: nextSeq(),
    },
  };

  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };

    try {
      const client = createConnection(socketPath);
      client.on("error", (err: Error) => {
        console.error(`[herdr-vibe] Socket error: ${err.message}`);
        done();
      });
      client.on("connect", () => {
        client.write(JSON.stringify(request) + "\n", () => {
          client.end();
        });
      });
      client.on("close", done);
      // Don't let a hung socket block process exit indefinitely
      setTimeout(done, 500);
    } catch (err: unknown) {
      const error = err as Error;
      console.error(`[herdr-vibe] Socket error: ${error.message}`);
      done();
    }
  });
}

/**
 * Report agent session to Herdr via socket
 */
function reportAgentSessionSocket(sessionId?: string): Promise<void> {
  const params: Record<string, unknown> = {};
  if (sessionId) {
    params.agent_session_id = sessionId;
  }
  return sendToSocket("pane.report_agent_session", params);
}

/**
 * Report agent state to Herdr via socket
 */
function reportStateSocket(state: string, message: string = ""): Promise<void> {
  const params: Record<string, unknown> = { state };
  if (message) {
    params.message = message;
  }
  return sendToSocket("pane.report_agent", params);
}

/**
 * Release agent via socket
 */
function releaseAgentSocket(): Promise<void> {
  return sendToSocket("pane.release_agent", {});
}

/**
 * Main function
 */
async function main(): Promise<void> {
  // Check if we're in Herdr
  if (!isInHerdr()) {
    // Not in Herdr - just exec vibe with inherit to preserve TUI
    const vibe = spawn("vibe", process.argv.slice(2), {
      stdio: "inherit",
    });

    vibe.on("error", (err: Error) => {
      console.error("[herdr-vibe] Failed to start vibe:", err.message);
      process.exit(1);
    });

    vibe.on("exit", (code: number | null) => {
      process.exit(code || 0);
    });

    return;
  }

  const { paneId, socketPath } = getHerdrEnv();
  console.error(`[herdr-vibe] Running in Herdr pane: ${paneId}`);

  // Register initial state via socket API (consistent with hook script)
  // This ensures agent appears immediately in Herdr tab
  // Hooks will take over for session_id and state updates
  if (socketPath) {
    await reportAgentSessionSocket();
    await reportStateSocket("idle", "Vibe ready");
  } else {
    // Fallback to CLI if socket not available
    reportAgentSession();
    reportState("idle", "Vibe ready");
  }

  // Set up cleanup - use socket API if available, and actually wait for it
  // to land before the process exits (process.on('exit', ...) can't do
  // async work, so this must run before process.exit() is called).
  let cleanedUp = false;
  const cleanup = async () => {
    if (cleanedUp) return;
    cleanedUp = true;
    if (socketPath) {
      await releaseAgentSocket();
    } else {
      releaseAgent();
    }
  };

  process.on("SIGINT", () => {
    cleanup().finally(() => process.exit(130));
  });
  process.on("SIGTERM", () => {
    cleanup().finally(() => process.exit(143));
  });

  // Run Vibe with full TTY access. Vibe requires a real TTY for its
  // interactive TUI and hook system to work at all - piping stdout/stderr
  // here breaks both (see docs/adr/ADR-001-hooks-only-architecture.md).
  // All state reporting comes from hooks.toml + herdr-agent-state.py.
  // IMPORTANT: Vibe is spawned AFTER agent registration to ensure our
  // custom source takes precedence over Herdr's auto-detection.
  const vibe = spawn("vibe", process.argv.slice(2), {
    stdio: "inherit",
  });

  vibe.on("error", async (err: Error) => {
    console.error("[herdr-vibe] Failed to start vibe:", err.message);
    if (socketPath) {
      await reportStateSocket("idle", "Error: " + err.message);
    } else {
      reportState("idle", "Error: " + err.message);
    }
    await cleanup();
    process.exit(1);
  });

  vibe.on("exit", async (code: number | null) => {
    const message = code === 0 ? "Vibe exited" : `Vibe exited with code ${code}`;
    if (socketPath) {
      await reportStateSocket("idle", message);
    } else {
      reportState("idle", message);
    }
    await cleanup();
    process.exit(code || 0);
  });
}

// Run main
main().catch(async (err: Error) => {
  console.error("[herdr-vibe] Fatal error:", err.message);
  releaseAgent();
  process.exit(1);
});
