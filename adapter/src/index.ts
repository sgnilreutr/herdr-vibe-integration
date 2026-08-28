#!/usr/bin/env node

/**
 * Herdr Integration Adapter for Mistral Vibe
 *
 * Uses Vibe's native hook system to report state changes to Herdr.
 * 
 * Architecture:
 * 1. Wrapper detects Herdr environment
 * 2. Reports initial idle state
 * 3. Runs Vibe with full TTY access so hooks will fire
 * 4. Hooks (via hooks.toml + herdr-agent-state.py) report state changes
 * 5. Handles cleanup on exit
 */

import { spawn } from 'node:child_process';

// Configuration
export const SOURCE = 'herdr:vibe';
export const AGENT = 'vibe';

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
  return (process.env.HERDR_ENV === '1') &&
         Boolean(process.env.HERDR_PANE_ID) &&
         Boolean(process.env.HERDR_BIN_PATH);
}

/**
 * Get Herdr environment variables
 */
export function getHerdrEnv(): HerdrEnv {
  return {
    paneId: process.env.HERDR_PANE_ID || '',
    herdrBin: process.env.HERDR_BIN_PATH || '',
    socketPath: process.env.HERDR_SOCKET_PATH,
  };
}

/**
 * Report agent state to Herdr via CLI
 */
function reportState(state: string, message: string = ''): void {
  const { paneId, herdrBin } = getHerdrEnv();

  const args: string[] = [
    'pane', 'report-agent', paneId,
    '--source', SOURCE,
    '--agent', AGENT,
    '--state', state,
  ];

  if (message) {
    args.push('--message', message);
  }

  try {
    const proc = spawn(herdrBin, args, { stdio: 'ignore', detached: true });
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
    'pane', 'report-agent-session', paneId,
    '--source', SOURCE,
    '--agent', AGENT,
  ];

  if (sessionId) {
    args.push('--agent-session-id', sessionId);
  }

  try {
    const proc = spawn(herdrBin, args, { stdio: 'ignore', detached: true });
    proc.unref();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] Agent session report failed: ${error.message}`);
  }
}

/**
 * Release agent on exit
 */
function releaseAgent(): void {
  const { paneId, herdrBin } = getHerdrEnv();

  try {
    const proc = spawn(herdrBin, [
      'pane', 'release-agent', paneId,
      '--source', SOURCE,
      '--agent', AGENT,
    ], { stdio: 'ignore', detached: true });
    proc.unref();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] Release failed: ${error.message}`);
  }
}

/**
 * Main function
 */
async function main(): Promise<void> {
  // Check if we're in Herdr
  if (!isInHerdr()) {
    // Not in Herdr - just exec vibe with inherit to preserve TUI
    const vibe = spawn('vibe', process.argv.slice(2), {
      stdio: 'inherit',
    });

    vibe.on('error', (err: Error) => {
      console.error('[herdr-vibe] Failed to start vibe:', err.message);
      process.exit(1);
    });

    vibe.on('exit', (code: number | null) => {
      process.exit(code || 0);
    });

    return;
  }

  const { paneId } = getHerdrEnv();
  console.error(`[herdr-vibe] Running in Herdr pane: ${paneId}`);

  // Register agent session BEFORE spawning vibe
  // This prevents Herdr from creating a duplicate auto-detected agent entry
  reportAgentSession();

  // Report initial state
  reportState('idle', 'Vibe ready');

  // Set up cleanup
  process.on('exit', releaseAgent);
  process.on('SIGINT', () => {
    releaseAgent();
    process.exit(130);
  });
  process.on('SIGTERM', () => {
    releaseAgent();
    process.exit(143);
  });

  // Run Vibe with full TTY access so hooks will fire properly
  // State updates will come from hooks (herdr-agent-state.py), not from output parsing
  // IMPORTANT: Vibe is spawned AFTER agent registration to ensure our custom
  // source takes precedence over Herdr's auto-detection
  const vibe = spawn('vibe', process.argv.slice(2), {
    stdio: 'inherit',
  });

  vibe.on('error', (err: Error) => {
    console.error('[herdr-vibe] Failed to start vibe:', err.message);
    reportState('idle', 'Error: ' + err.message);
    process.exit(1);
  });

  vibe.on('exit', (code: number | null) => {
    if (code === 0) {
      reportState('idle', 'Vibe exited');
    } else {
      reportState('idle', `Vibe exited with code ${code}`);
    }
    releaseAgent();
    process.exit(code || 0);
  });
}

// Run main
main().catch((err: Error) => {
  console.error('[herdr-vibe] Fatal error:', err.message);
  releaseAgent();
  process.exit(1);
});
