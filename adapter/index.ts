#!/usr/bin/env node

/**
 * Herdr Integration Adapter for Mistral Vibe
 *
 * This adapter runs Mistral Vibe inside Herdr and reports agent state.
 * When not running in Herdr, it simply execs the vibe CLI.
 */

import { spawn, ChildProcess, SpawnOptions } from 'child_process';

// Configuration
const SOURCE = 'custom:vibe';
const AGENT = 'vibe';

// Valid agent states
type AgentState = 'idle' | 'working' | 'blocked' | 'done' | 'unknown';

// Herdr environment variables
interface HerdrEnv {
  paneId: string;
  herdrBin: string;
  socketPath?: string;
}

// State patterns for detecting Vibe's state from output
const STATE_PATTERNS: Record<AgentState, RegExp[]> = {
  idle: [
    // Vibe's input prompt patterns
    /^[>\$] /,
    /^vibe[> ]/i,
    /^Enter (prompt|command|query):/i,
    /^What would you like/i,
    /^How can I help/i,
    // Empty line might indicate ready state
    /^\n*$/,
  ],
  working: [
    // Thinking/generating indicators
    /^Thinking/i,
    /^Generating/i,
    /^Processing/i,
    /^Analyzing/i,
    /^Working/i,
    // Spinners and progress indicators
    /^[|/\\-]/,
    /^[▰▱▱▱|▱▰▱▱|▱▱▰▱|▱▱▱▰]/,
    /^[▉▊]/,
    /^\.\.\./,
  ],
  blocked: [
    // Permission/confirmation prompts
    /Allow[?\s]/i,
    /Please confirm/i,
    /Do you want to/i,
    /Continue[?\s]/i,
    /Proceed[?\s]/i,
    /\[y\/n\]/i,
    /\[yes\/no\]/i,
    /Approve[?\s]/i,
    // Tool use approval
    /Call tool/i,
    /Run command/i,
    /Execute[?\s]/i,
  ],
  done: [
    // Completion indicators
    /^Task complete/i,
    /^Done/i,
    /^✓/,
    /^✅/,
    /^Success/i,
    /^Finished/i,
    /^Complete/i,
  ],
  unknown: [],
};

// Current state tracking
let currentState: AgentState = 'idle';
let sequenceNumber = 0;

/**
 * Check if we're running inside Herdr
 */
function isInHerdr(): boolean {
  return (process.env.HERDR_ENV === '1') &&
         Boolean(process.env.HERDR_PANE_ID) &&
         Boolean(process.env.HERDR_BIN_PATH);
}

/**
 * Get Herdr environment variables
 */
function getHerdrEnv(): HerdrEnv {
  return {
    paneId: process.env.HERDR_PANE_ID || '',
    herdrBin: process.env.HERDR_BIN_PATH || '',
    socketPath: process.env.HERDR_SOCKET_PATH,
  };
}

/**
 * Report agent state to Herdr via CLI
 */
function reportState(state: AgentState, message: string = ''): void {
  const { paneId, herdrBin } = getHerdrEnv();

  // Only report if state actually changed
  if (state === currentState) {
    return;
  }

  currentState = state;
  sequenceNumber++;

  const args: string[] = [
    'pane', 'report-agent', paneId,
    '--source', SOURCE,
    '--agent', AGENT,
    '--state', state,
    '--seq', sequenceNumber.toString(),
  ];

  if (message) {
    args.push('--message', message);
  }

  try {
    const proc = spawn(herdrBin, args, { stdio: 'ignore', detached: true });
    proc.unref();
  } catch (err: unknown) {
    // Silently ignore errors - Herdr might not be available
    const error = err as Error;
    console.error(`[herdr-vibe] State report failed: ${error.message}`);
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
    // Silently ignore
    const error = err as Error;
    console.error(`[herdr-vibe] Release failed: ${error.message}`);
  }
}

/**
 * Detect state from a line of output
 */
function detectState(line: string): AgentState | null {
  // Check blocked patterns first (highest priority)
  for (const pattern of STATE_PATTERNS.blocked) {
    if (pattern.test(line)) {
      return 'blocked';
    }
  }

  // Check done patterns
  for (const pattern of STATE_PATTERNS.done) {
    if (pattern.test(line)) {
      return 'done';
    }
  }

  // Check working patterns
  for (const pattern of STATE_PATTERNS.working) {
    if (pattern.test(line)) {
      return 'working';
    }
  }

  // Check idle patterns
  for (const pattern of STATE_PATTERNS.idle) {
    if (pattern.test(line)) {
      return 'idle';
    }
  }

  // No pattern matched - maintain current state
  return null;
}

/**
 * Strip ANSI escape codes from text
 */
function stripAnsiCodes(text: string): string {
  // Match common ANSI escape sequences
  // ESC [ ... letter (CSI sequences like \x1b[31m, \x1b[?1049h, \x1b[>25u)
  // ESC ] ... BEL (OSC sequences like \x1b]22;default\x07)
  // ESC other sequences
  // First pass: CSI sequences (ESC [ ... final_byte) - final_byte is in range 64-126
  let result = text.replace(/\x1b\[[\x20-\x3F]*[\x40-\x7E]/g, '');
  // Second pass: OSC sequences (ESC ] ... BEL)
  result = result.replace(/\x1b\][^\x07]*\x07/g, '');
  // Third pass: Any ESC followed by a control character
  result = result.replace(/\x1b[\x00-\x1F\x7F]/g, '');
  return result;
}



/**
 * Spawn Vibe process with proper configuration
 * 
 * Key insight: Vibe CLI has two modes:
 * - Interactive mode (no -p flag): starts Textual TUI which reads from terminal, not stdin
 * - Programmatic mode (-p flag): runs without TUI, reads prompt from args or stdin
 * 
 * IMPORTANT: When using programmatic mode (-p), Vibe still tries to read from stdin
 * via get_prompt_from_stdin() if stdin is a pipe. We use stdio: ['ignore', 'pipe', 'pipe']
 * to prevent Vibe from reading from stdin, forcing it to use only the -p argument.
 * 
 * To avoid TUI issues in Herdr, we force programmatic mode by always passing -p with the prompt.
 */
function spawnVibe(prompt: string): ChildProcess {
  const spawnOptions: SpawnOptions = {
    // Use 'ignore' for stdin to prevent Vibe from reading from it
    // Vibe's get_prompt_from_stdin() will see stdin as not readable and skip it
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      TERM: 'dumb',
      NO_COLOR: '1',
    },
  };

  // Always use programmatic mode to avoid TUI
  // Pass prompt via -p flag
  return spawn('vibe', ['-p', prompt, '--output', 'text'], spawnOptions);
}

/**
 * Main function
 */
function main(): void {
  // Check if we're in Herdr
  if (!isInHerdr()) {
    // Not in Herdr - just exec vibe
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

  console.error(`[herdr-vibe] Running in Herdr pane: ${getHerdrEnv().paneId}`);

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

  // Report initial state
  reportState('idle', 'Vibe starting...');

  // Manage conversation loop for Herdr
  // Herdr sends input to our stdin, we read it and pass to Vibe in programmatic mode
  // This avoids the TUI entirely
  
  // Read from stdin line by line
  const stdinBuffer: string[] = [];
  let currentVibe: ChildProcess | null = null;
  let isProcessing = false;

  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk: string) => {
    const lines = chunk.split('\n');
    for (const line of lines) {
      if (line.trim()) {
        stdinBuffer.push(line);
        processLine();
      }
    }
  });

  // Handle EOF (pipe closed)
  process.stdin.on('end', () => {
    // If there's buffered input, process it
    if (stdinBuffer.length > 0) {
      processLine();
    } else if (!isProcessing && currentVibe === null) {
      // No input and not processing - just exit
      reportState('idle', 'No input received');
      process.exit(0);
    }
  });

  function processLine(): void {
    // If already processing, wait for current request to finish
    if (isProcessing || stdinBuffer.length === 0) {
      return;
    }

    isProcessing = true;
    const prompt = stdinBuffer.shift()!;
    
    reportState('working', `Processing: ${prompt.substring(0, 50)}`);
    
    // Spawn Vibe in programmatic mode with the prompt
    currentVibe = spawnVibe(prompt);

    let outputBuffer = '';
    let hasDetectedState = false;

    // Collect output from Vibe
    if (currentVibe.stdout) {
      currentVibe.stdout.on('data', (chunk: Buffer) => {
        const text = chunk.toString();
        outputBuffer += text;
        
        // Try to detect state from output lines
        if (!hasDetectedState) {
          const lines = text.split('\n');
          for (const line of lines) {
            if (line.trim()) {
              const detected = detectState(line);
              if (detected) {
                reportState(detected, line);
                hasDetectedState = true;
                break;
              }
            }
          }
        }
      });
    }
    if (currentVibe.stderr) {
      currentVibe.stderr.on('data', (chunk: Buffer) => {
        // Forward stderr immediately (might contain errors)
        const cleanText = stripAnsiCodes(chunk.toString());
        if (cleanText.trim()) {
          process.stderr.write(cleanText);
        }
      });
    }

    currentVibe.on('error', (err: Error) => {
      console.error('[herdr-vibe] Vibe error:', err.message);
      reportState('idle', 'Error: ' + err.message);
      isProcessing = false;
      currentVibe = null;
      // Try to process next line
      processLine();
    });

    currentVibe.on('exit', () => {
      // Strip ANSI codes and forward the complete output
      const cleanOutput = stripAnsiCodes(outputBuffer);
      if (cleanOutput.trim()) {
        process.stdout.write(cleanOutput);
      }
      
      reportState('idle', 'Ready for next input');
      isProcessing = false;
      currentVibe = null;
      
      // Process next line if available
      processLine();
    });
  }

  // Handle initial input if any
  process.stdin.resume();
}

// Run main
main();
