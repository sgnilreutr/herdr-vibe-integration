/**
 * Test Mistral Vibe CLI behavior with PTY
 * This helps us understand what Vibe outputs in interactive mode
 */

const { spawn } = require('child_process');
const { createInterface } = require('readline');

console.log('=== Vibe PTY Behavior Test ===\n');

// Test 1: Programmatic mode
console.log('Test 1: Programmatic mode (-p flag)');
const proc1 = spawn('vibe', ['-p', 'What is 2+2?', '--max-turns', '1', '--output', 'text']);
proc1.stdout.on('data', (data) => {
  console.log('STDOUT:', data.toString());
});
proc1.stderr.on('data', (data) => {
  console.log('STDERR:', data.toString());
});
proc1.on('close', (code) => {
  console.log('Exit code:', code);
  console.log('');
  
  // Test 2: Check if --prompt accepts stdin
  console.log('Test 2: Programmatic mode with --prompt -');
  const proc2 = spawn('vibe', ['--prompt', '-', '--max-turns', '1', '--output', 'text']);
  proc2.stdin.write('What is 5+5?\n');
  proc2.stdin.end();
  proc2.stdout.on('data', (data) => {
    console.log('STDOUT:', data.toString());
  });
  proc2.stderr.on('data', (data) => {
    console.log('STDERR:', data.toString());
  });
  proc2.on('close', (code) => {
    console.log('Exit code:', code);
    console.log('');
    
    // Test 3: Version
    console.log('Test 3: Version');
    const proc3 = spawn('vibe', ['--version']);
    proc3.stdout.on('data', (data) => {
      console.log('Version:', data.toString().trim());
    });
    proc3.on('close', () => {
      console.log('');
      console.log('=== Tests Complete ===');
    });
  });
});
