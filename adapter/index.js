/**
 * Herdr Integration Adapter for Mistral Vibe
 * 
 * This adapter runs Mistral Vibe inside Herdr and reports agent state.
 * When not running in Herdr, it simply execs the vibe CLI.
 */

const { spawn } = require('child_process');
const { existsSync } = require('fs');
const path = require('path');
const os = require('os');

// Configuration
const SOURCE = 'custom:vibe';
const AGENT = 'vibe';

// State patterns for detecting Vibe's state from output
const STATE_PATTERNS = {
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
    /^[|/-\\]/,
    /^[▰▱▱▱|▱▰▱▱|▱▱▰▱|▱▱▱▰]/,
    /^[▉▊]/,
    /^\.\.\./,
    // Streaming output (token by token)
    /^[a-zA-Z]/, // Simple heuristic: output without prompt
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
};

// Current state tracking
let currentState = 'idle';
let sequenceNumber = 0;

/**
 * Check if we're running inside Herdr
 */
function isInHerdr() {
  return process.env.HERDR_ENV === '1' &&
         process.env.HERDR_PANE_ID &&
         process.env.HERDR_BIN_PATH;
}

/**
 * Get Herdr environment variables
 */
function getHerdrEnv() {
  return {
    paneId: process.env.HERDR_PANE_ID,
    herdrBin: process.env.HERDR_BIN_PATH,
    socketPath: process.env.HERDR_SOCKET_PATH,
  };
}

/**
 * Report agent state to Herdr via CLI
 */
function reportState(state, message = '') {
  const { paneId, herdrBin } = getHerdrEnv();
  
  // Only report if state actually changed
  if (state === currentState) {
    return;
  }
  
  currentState = state;
  sequenceNumber++;
  
  const args = [
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
    spawn(herdrBin, args, { stdio: 'ignore', detached: true });
  } catch (err) {
    // Silently ignore errors - Herdr might not be available
  }
}

/**
 * Release agent on exit
 */
function releaseAgent() {
  const { paneId, herdrBin } = getHerdrEnv();
  
  try {
    spawn(herdrBin, [
      'pane', 'release-agent', paneId,
      '--source', SOURCE,
      '--agent', AGENT,
    ], { stdio: 'ignore', detached: true });
  } catch (err) {
    // Silently ignore
  }
}

/**
 * Detect state from a line of output
 */
function detectState(line) {
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
function processOutput(chunk, vibeProcess) {
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
 * Main function
 */
function main() {
  // Check if we're in Herdr
  if (!isInHerdr()) {
    // Not in Herdr - just exec vibe
    const vibe = spawn('vibe', process.argv.slice(2), {
      stdio: 'inherit',
    });
    
    vibe.on('error', (err) => {
      console.error('Failed to start vibe:', err.message);
      process.exit(1);
    });
    
    vibe.on('exit', (code) => {
      process.exit(code || 0);
    });
    
    return;
  }
  
  console.log(`[herdr-vibe] Running in Herdr pane: ${getHerdrEnv().paneId}`);
  
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
  
  // If no arguments and stdin is a TTY, run in interactive mode
  // Otherwise, add --prompt to force programmatic mode
  if (args.length === 0 && process.stdin.isTTY) {
    // Interactive mode - just run vibe
    const vibe = spawn('vibe', args, {
      stdio: ['inherit', 'pipe', 'pipe'],
    });
    
    // Forward stdout and stderr
    vibe.stdout.on('data', (chunk) => processOutput(chunk, vibe));
    vibe.stderr.on('data', (chunk) => {
      process.stderr.write(chunk);
    });
    
    vibe.on('error', (err) => {
      console.error('Vibe error:', err.message);
      reportState('idle', 'Error: ' + err.message);
    });
    
    vibe.on('exit', (code) => {
      reportState('done', `Exited with code ${code}`);
      process.exit(code || 0);
    });
  } else {
    // Programmatic mode
    args.unshift('-p');
    const vibe = spawn('vibe', args, {
      stdio: ['inherit', 'pipe', 'pipe'],
    });
    
    vibe.stdout.on('data', (chunk) => processOutput(chunk, vibe));
    vibe.stderr.on('data', (chunk) => {
      process.stderr.write(chunk);
    });
    
    vibe.on('error', (err) => {
      console.error('Vibe error:', err.message);
      reportState('idle', 'Error: ' + err.message);
    });
    
    vibe.on('exit', (code) => {
      reportState('done', `Exited with code ${code}`);
      process.exit(code || 0);
    });
  }
}

// Run main
main();
