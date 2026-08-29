#!/usr/bin/env python3
"""
Herdr-Vibe Integration Test Suite

Programmatically tests the Herdr-Vibe integration by:
1. Sending keys to Vibe panes
2. Verifying hooks fire
3. Checking Herdr state updates

Usage:
    python3 scripts/test-herdr-vibe.py              # Run full test suite
    python3 scripts/test-herdr-vibe.py --pane w78J:p2  # Test specific pane
    python3 scripts/test-herdr-vibe.py --list        # List available panes
"""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

HERDR_SOCKET = "/Users/rtuerlings/.config/herdr/herdr.sock"
HOOK_DEBUG_LOG = "/tmp/herdr-debug/hook-debug.log"


def send_herdr_request(method: str, params: dict = None) -> dict:
    """Send request to Herdr socket."""
    if params is None:
        params = {}
    request = {
        'id': f'test-{int(time.time() * 1000)}',
        'method': method,
        'params': params
    }
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect(HERDR_SOCKET)
        sock.sendall((json.dumps(request) + '\n').encode())
        response = sock.recv(65536).decode()
        sock.close()
        return json.loads(response)
    except Exception as e:
        return {'error': str(e)}


def get_panes(workspace_id: str = None) -> list:
    """Get list of panes, optionally filtered by workspace."""
    params = {}
    if workspace_id:
        params['workspace_id'] = workspace_id
    response = send_herdr_request('pane.list', params)
    return response.get('result', {}).get('panes', [])


def get_vibe_panes() -> list:
    """Get panes with Vibe agents."""
    all_panes = get_panes()
    return [p for p in all_panes if p.get('agent') == 'vibe']


def read_pane(pane_id: str) -> str:
    """Read pane content."""
    response = send_herdr_request('pane.read', {'pane_id': pane_id, 'source': 'visible'})
    return response.get('result', {}).get('read', {}).get('text', '')


def send_keys(pane_id: str, text: str) -> bool:
    """Send keys to a pane with Enter."""
    # Convert text to key sequence
    keys = []
    for char in text:
        if char == ' ':
            keys.append('Space')
        elif char == '\n':
            keys.append('Enter')
        else:
            keys.append(char)
    keys.append('Enter')
    
    response = send_herdr_request('pane.send_keys', {'pane_id': pane_id, 'keys': keys})
    return response.get('result', {}).get('type') == 'ok'


def wait_for_hook(pane_id: str, timeout: int = 10) -> bool:
    """Wait for a hook to fire for a specific pane."""
    if not Path(HOOK_DEBUG_LOG).exists():
        return False
    
    start_time = time.time()
    last_position = 0
    
    while time.time() - start_time < timeout:
        try:
            with open(HOOK_DEBUG_LOG, 'r') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                
                for line in new_lines:
                    if f"HERDR_PANE_ID={pane_id}" in line and "Hook script invoked" in line:
                        return True
                    if f"pane_id\": \"{pane_id}\"" in line and "hook_event_name" in line:
                        return True
                
                last_position = f.tell()
        except Exception:
            pass
        time.sleep(0.5)
    
    return False


def get_agent_state(pane_id: str) -> dict:
    """Get agent state from Herdr."""
    response = send_herdr_request('agent.list')
    agents = response.get('result', {}).get('agents', [])
    for agent in agents:
        if agent.get('pane_id') == pane_id:
            return agent
    return {}


def test_pane(pane_id: str, test_prompt: str = "What is the time?") -> dict:
    """Test a single pane."""
    print(f"\n{'='*60}")
    print(f"Testing pane: {pane_id}")
    print(f"{'='*60}")
    
    result = {
        'pane_id': pane_id,
        'success': False,
        'errors': [],
        'hook_fired': False,
        'state_updated': False
    }
    
    # Read initial state
    initial_state = get_agent_state(pane_id)
    print(f"Initial state: {initial_state.get('agent_status', 'unknown')}")
    
    # Clear hook log position tracking
    if Path(HOOK_DEBUG_LOG).exists():
        with open(HOOK_DEBUG_LOG, 'r') as f:
            result['_last_hook_pos'] = f.tell()
    else:
        result['_last_hook_pos'] = 0
    
    # Send test prompt
    print(f"Sending: '{test_prompt}'")
    if not send_keys(pane_id, test_prompt):
        result['errors'].append("Failed to send keys")
        return result
    
    print("Keys sent. Waiting for Vibe response...")
    
    # Wait for hook to fire
    if wait_for_hook(pane_id, timeout=15):
        result['hook_fired'] = True
        print("✅ Hook fired!")
    else:
        result['errors'].append("Hook did not fire within timeout")
        print("⚠️  Hook did not fire")
    
    # Check state update
    time.sleep(2)  # Wait for state to propagate
    final_state = get_agent_state(pane_id)
    final_status = final_state.get('agent_status')
    
    if final_status and final_status != initial_state.get('agent_status'):
        result['state_updated'] = True
        print(f"✅ State updated: {initial_state.get('agent_status')} -> {final_status}")
    elif final_status == 'working':
        result['state_updated'] = True
        print(f"✅ State is working (Vibe processing)")
    else:
        print(f"⚠️  State unchanged: {final_status}")
    
    # Read pane to see response
    content = read_pane(pane_id)
    if content:
        lines = content.split('\n')
        # Check if our prompt appears in the pane
        if test_prompt in content:
            print(f"✅ Prompt visible in pane")
        # Check for response
        if len(lines) > 0:
            print(f"Last line: {lines[-1][:80]}")
    
    result['success'] = result['hook_fired'] or result['state_updated']
    return result


def list_panes() -> None:
    """List all panes with Vibe agents."""
    print("\n" + "="*60)
    print("VIBE PANES IN HERDR")
    print("="*60)
    
    panes = get_vibe_panes()
    if not panes:
        print("No Vibe panes found")
        return
    
    for pane in panes:
        print(f"\nPane: {pane.get('pane_id')}")
        print(f"  Title: {pane.get('terminal_title', 'N/A')[:50]}")
        print(f"  Status: {pane.get('agent_status', 'unknown')}")
        print(f"  Workspace: {pane.get('workspace_id')}")
        print(f"  Tab: {pane.get('tab_id')}")


def main():
    parser = argparse.ArgumentParser(description="Test Herdr-Vibe Integration")
    parser.add_argument("--pane", "-p", help="Test specific pane")
    parser.add_argument("--list", "-l", action="store_true", help="List Vibe panes")
    parser.add_argument("--prompt", default="What is the time?", help="Test prompt to send")
    parser.add_argument("--all", "-a", action="store_true", help="Test all Vibe panes")
    args = parser.parse_args()
    
    if args.list:
        list_panes()
        return
    
    if args.all:
        panes = get_vibe_panes()
        print(f"\nFound {len(panes)} Vibe panes to test")
        results = []
        for pane in panes:
            pane_id = pane.get('pane_id')
            result = test_pane(pane_id, args.prompt)
            results.append(result)
        
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for result in results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status}: {result['pane_id']}")
            if result['hook_fired']:
                print(f"  Hook fired: YES")
            if result['state_updated']:
                print(f"  State updated: YES")
            if result['errors']:
                for error in result['errors']:
                    print(f"  Error: {error}")
        return
    
    if args.pane:
        test_pane(args.pane, args.prompt)
        return
    
    # Default: test first Vibe pane
    panes = get_vibe_panes()
    if panes:
        test_pane(panes[0].get('pane_id'), args.prompt)
    else:
        print("No Vibe panes found. Use --list to see available panes.")


if __name__ == "__main__":
    main()
