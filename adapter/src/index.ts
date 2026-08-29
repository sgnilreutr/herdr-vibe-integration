#!/usr/bin/env node

/**
 * Herdr Integration Adapter for Mistral Vibe
 *
 * Uses Vibe's native hook system AND output parsing to report state changes to Herdr.
 * 
 * Architecture:
 * 1. Wrapper detects Herdr environment
 * 2. Reports initial idle state
 * 3. Runs Vibe with piped stdout/stderr to parse output for state detection
 * 4. Hooks (via hooks.toml + herdr-agent-state.py) report state changes for tool usage
 * 5. Output parsing detects when Vibe is generating text responses (for plain text prompts)
 * 6. Handles cleanup on exit
 */

import { spawn } from 'node:child_process';
import { createConnection } from 'node:net';
import { randomBytes } from 'node:crypto';

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
 * Send a JSON-RPC request to Herdr via Unix socket
 */
function sendToSocket(method: string, params: Record<string, unknown>): void {
  const { paneId, socketPath } = getHerdrEnv();
  
  if (!socketPath) {
    console.error('[herdr-vibe] No socket path for socket API');
    return;
  }
  
  const requestId = `${SOURCE}:${Date.now()}:${randomBytes(3).toString('hex')}`;
  const request = {
    id: requestId,
    method,
    params: {
      ...params,
      pane_id: paneId,
      source: SOURCE,
      agent: AGENT,
    },
  };
  
  try {
    const client = createConnection(socketPath);
    client.write(JSON.stringify(request) + '\n');
    client.end();
  } catch (err: unknown) {
    const error = err as Error;
    console.error(`[herdr-vibe] Socket error: ${error.message}`);
  }
}

/**
 * Report agent session to Herdr via socket
 */
function reportAgentSessionSocket(sessionId?: string): void {
  const params: Record<string, unknown> = {};
  if (sessionId) {
    params.agent_session_id = sessionId;
  }
  sendToSocket('pane.report_agent_session', params);
}

/**
 * Report agent state to Herdr via socket
 */
function reportStateSocket(state: string, message: string = ''): void {
  const params: Record<string, unknown> = { state };
  if (message) {
    params.message = message;
  }
  sendToSocket('pane.report_agent', params);
}

/**
 * Release agent via socket
 */
function releaseAgentSocket(): void {
  sendToSocket('pane.release_agent', {});
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

  const { paneId, socketPath } = getHerdrEnv();
  console.error(`[herdr-vibe] Running in Herdr pane: ${paneId}`);

  // Register initial state via socket API (consistent with hook script)
  // This ensures agent appears immediately in Herdr tab
  // Hooks will take over for session_id and state updates
  if (socketPath) {
    reportAgentSessionSocket();
    reportStateSocket('idle', 'Vibe ready');
  } else {
    // Fallback to CLI if socket not available
    reportAgentSession();
    reportState('idle', 'Vibe ready');
  }

  // Set up cleanup - use socket API if available
  const cleanup = () => {
    if (socketPath) {
      releaseAgentSocket();
    } else {
      releaseAgent();
    }
  };
  
  process.on('exit', cleanup);
  process.on('SIGINT', () => {
    cleanup();
    process.exit(130);
  });
  process.on('SIGTERM', () => {
    cleanup();
    process.exit(143);
  });

  // Run Vibe with piped stdout/stderr so we can parse output for state detection
  // State updates will come from:
  // 1. Hooks (herdr-agent-state.py) for tool usage
  // 2. Output parsing for plain text responses
  // IMPORTANT: Vibe is spawned AFTER agent registration to ensure our custom
  // source takes precedence over Herdr's auto-detection
  // Note: We use stdio: 'pipe' so we can parse Vibe's output and detect state changes
  // We forward output to the terminal while parsing it
  const vibe = spawn('vibe', process.argv.slice(2), {
    stdio: 'pipe',
  });

  // Track if we're currently in a response (to detect when we go back to idle)
  let inResponse = false;
  let idleTimeout: NodeJS.Timeout | null = null;

  // Function to detect if a line indicates Vibe is waiting for input (showing a prompt)
  function isIdleIndicator(line: string): boolean {
    // These patterns indicate Vibe is waiting for user input
    const idlePatterns = [
      /^\s*>\s*$/,
      /^\s*>>\s*$/,
      /^\s*vibe>\s*$/i,
      /^\s*\$\s*$/,
      /Enter your prompt/,
      /Waiting for input/,
    ];
    return idlePatterns.some(p => p.test(line));
  }

  // Function to detect if a line indicates Vibe is generating output
  function isResponseIndicator(line: string): boolean {
    // A non-empty line that is not a prompt indicates a response
    const trimmed = line.trim();
    return trimmed.length > 0 && !isIdleIndicator(line);
  }

  // Forward output from Vibe to the terminal while parsing
  // We need to buffer lines to handle partial writes
  let stdoutBuffer = '';
  
  if (vibe.stdout) {
    vibe.stdout.on('data', (data: Buffer) => {
      const chunk = data.toString();
      stdoutBuffer += chunk;
      
      // Forward to stdout immediately
      process.stdout.write(chunk);

      // Split into lines and analyze
      const lines = stdoutBuffer.split('\n');
      // Keep the last partial line in buffer
      stdoutBuffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.trim()) {
          // If we see non-prompt output, we're in a response
          if (isResponseIndicator(line)) {
            if (!inResponse) {
              inResponse = true;
              // Clear any pending idle timeout
              if (idleTimeout) {
                clearTimeout(idleTimeout);
                idleTimeout = null;
              }
              // Report working state
              if (socketPath) {
                reportStateSocket('working', 'Generating response');
              } else {
                reportState('working', 'Generating response');
              }
            }
          } else if (isIdleIndicator(line)) {
            // We see a prompt - we're idle
            if (inResponse) {
              inResponse = false;
              if (socketPath) {
                reportStateSocket('idle', 'Ready for input');
              } else {
                reportState('idle', 'Ready for input');
              }
            }
          }
        }
      }
    });
  }

  if (vibe.stderr) {
    vibe.stderr.on('data', (data: Buffer) => {
      const chunk = data.toString();
      // Forward to stderr
      process.stderr.write(chunk);
    });
  }

  // Set up timeout to detect when Vibe goes idle
  // If we don't see any output for a while, assume we're idle
  function scheduleIdleCheck() {
    if (idleTimeout) clearTimeout(idleTimeout);
    idleTimeout = setTimeout(() => {
      if (inResponse) {
        inResponse = false;
        if (socketPath) {
          reportStateSocket('idle', 'Ready for input');
        } else {
          reportState('idle', 'Ready for input');
        }
      }
    }, 2000); // 2 seconds of no output = idle
  }

  // Schedule idle check on each data chunk
  if (vibe.stdout) {
    vibe.stdout.on('data', () => {
      scheduleIdleCheck();
    });
  }
  if (vibe.stderr) {
    vibe.stderr.on('data', () => {
      scheduleIdleCheck();
    });
  }
  
  // Check for idle state on exit
  if (vibe.stdout) {
    vibe.stdout.on('end', () => {
      scheduleIdleCheck();
    });
  }
  
  if (vibe.stderr) {
    vibe.stderr.on('end', () => {
      scheduleIdleCheck();
    });
  }

  vibe.on('error', (err: Error) => {
    console.error('[herdr-vibe] Failed to start vibe:', err.message);
    if (socketPath) {
      reportStateSocket('idle', 'Error: ' + err.message);
    } else {
      reportState('idle', 'Error: ' + err.message);
    }
    releaseAgent();
    process.exit(1);
  });

  vibe.on('exit', (code: number | null) => {
    if (code === 0) {
      if (socketPath) {
        reportStateSocket('idle', 'Vibe exited');
      } else {
        reportState('idle', 'Vibe exited');
      }
    } else {
      if (socketPath) {
        reportStateSocket('idle', `Vibe exited with code ${code}`);
      } else {
        reportState('idle', `Vibe exited with code ${code}`);
      }
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
