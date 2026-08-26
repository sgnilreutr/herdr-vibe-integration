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
 * Process a chunk of output from Vibe
 */
function processOutput(chunk: Buffer): void {
  const text = chunk.toString();
  const lines = text.split('\n');
  
  for (const line of lines) {
    if (!line.trim()) continue;
    
    const detected = detectState(line);
    if (detected) {
      reportState(detected, line);
    }
  }
  
  // Forward output to stdout (so user sees it in Herdr)
  process.stdout.write(chunk);
}

/**
 * Spawn Vibe process with proper configuration
 */
function spawnVibe(args: string[]): ChildProcess {
  const spawnOptions: SpawnOptions = {
    stdio: ['inherit', 'pipe', 'pipe'],
  };
  
  return spawn('vibe', args, spawnOptions);
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
  
  // Spawn Vibe with arguments
  const args = process.argv.slice(2);
  const vibe = spawnVibe(args);
  
  // Forward stdout and stderr
  if (vibe.stdout) {
    vibe.stdout.on('data', processOutput);
  }
  if (vibe.stderr) {
    vibe.stderr.on('data', (chunk: Buffer) => {
      process.stderr.write(chunk);
    });
  }
  
  vibe.on('error', (err: Error) => {
    console.error('[herdr-vibe] Vibe error:', err.message);
    reportState('idle', 'Error: ' + err.message);
  });
  
  vibe.on('exit', (code: number | null) => {
    reportState('done', `Exited with code ${code}`);
    process.exit(code || 0);
  });
}

// Run main
main();
