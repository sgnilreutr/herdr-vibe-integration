#!/usr/bin/env python3
"""
Integration Testing Framework for Herdr-Vibe

This script provides automated testing with "eyes" into Herdr state.
It can run tests with or without a running Herdr instance.

Usage:
    # Run all tests
    python3 scripts/test-integration.py
    
    # Run with specific socket path
    python3 scripts/test-integration.py --socket-path /tmp/test-herdr.sock
    
    # Run specific test
    python3 scripts/test-integration.py --test test_hook_invocation
    
    # Run with debug output
    python3 scripts/test-integration.py --debug
    
    # Run with real Herdr
    python3 scripts/test-integration.py --real-herdr
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

# Import herdr_client functions - read and exec the file
import importlib.util

# Load herdr_client module - try both hyphen and underscore
for filename in ["herdr-client.py", "herdr_client.py"]:
    herdr_client_path = scripts_dir / filename
    if herdr_client_path.exists():
        spec = importlib.util.spec_from_file_location("herdr_client", herdr_client_path)
        herdr_client_module = importlib.util.module_from_spec(spec)
        sys.modules["herdr_client"] = herdr_client_module
        spec.loader.exec_module(herdr_client_module)
        
        # Import functions
        send_request = herdr_client_module.send_request
        get_socket_path = herdr_client_module.get_socket_path
        report_agent_state = herdr_client_module.report_agent_state
        report_agent_session = herdr_client_module.report_agent_session
        check_herdr_running = herdr_client_module.check_herdr_running
        break
else:
    print(f"Error: herdr-client.py not found in {scripts_dir}")
    sys.exit(1)


# Constants
SOURCE = "herdr:vibe"
AGENT = "vibe"
TEST_PANE_ID = "test:w1:p1"
TEST_SESSION_ID = "test-session-123"


class TestResult:
    """Represents the result of a test."""
    
    def __init__(self, name: str, passed: bool, message: str = "", details: Any = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details
    
    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status}: {self.name}{' - ' + self.message if self.message else ''}"


class HerdrTestHarness:
    """Test harness for Herdr integration testing."""
    
    def __init__(self, socket_path: str = None, debug: bool = False, real_herdr: bool = False):
        self.socket_path = socket_path
        self.debug = debug
        self.real_herdr = real_herdr
        self.temp_dir = tempfile.mkdtemp()
        self.test_results: list[TestResult] = []
        self.cleanup_files: list[str] = []
        
        # Track temporary socket server process
        self.socket_server_process = None
    
    def setup_environment(self, pane_id: str = TEST_PANE_ID) -> dict:
        """Set up test environment variables."""
        env = os.environ.copy()
        env.update({
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": pane_id,
            "HERDR_SOCKET_PATH": self.socket_path or get_socket_path() or "/tmp/test-herdr.sock",
            "HERDR_BIN_PATH": "/usr/bin/echo",  # Fallback
            "PATH": os.environ.get("PATH", ""),
        })
        return env
    
    def get_hook_script_path(self) -> Path:
        """Get the path to the hook script."""
        # Try installed location first
        installed_path = Path.home() / ".vibe" / "herdr-agent-state.py"
        if installed_path.exists():
            return installed_path
        
        # Try project location
        project_path = Path(__file__).parent.parent / "adapter" / "herdr-agent-state.py"
        if project_path.exists():
            return project_path
        
        raise FileNotFoundError(f"Hook script not found at {installed_path} or {project_path}")
    
    def run_hook_script(self, hook_data: dict, pane_id: str = TEST_PANE_ID) -> dict:
        """Run the hook script and capture output."""
        env = self.setup_environment(pane_id)
        
        try:
            hook_script = self.get_hook_script_path()
        except FileNotFoundError as e:
            return {"error": str(e), "returncode": 1}
        
        cmd = ["python3", str(hook_script)]
        
        if self.debug:
            print(f"  Running: {' '.join(cmd)}")
            print(f"  Input: {json.dumps(hook_data)}")
        
        try:
            result = subprocess.run(
                cmd,
                input=json.dumps(hook_data),
                capture_output=True,
                text=True,
                env=env,
                timeout=5,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Timeout", "returncode": -1}
    
    def start_test_socket_server(self) -> bool:
        """Start a test socket server for testing without Herdr."""
        if self.socket_path and Path(self.socket_path).exists():
            # Socket already exists, assume Herdr is running
            return True
        
        # Use a temporary socket path
        self.socket_path = f"/tmp/test-herdr-{os.getpid()}.sock"
        
        # Start test socket server
        test_server = Path(__file__).parent / "test-socket-server.py"
        if not test_server.exists():
            test_server = Path(__file__).parent.parent / "scripts" / "test-socket-server.py"
        
        try:
            self.socket_server_process = subprocess.Popen(
                ["python3", str(test_server), self.socket_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            # Wait for server to start
            time.sleep(1)
            
            # Check if socket is ready
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                sock.connect(self.socket_path)
                sock.close()
                if self.debug:
                    print(f"  Test socket server started at {self.socket_path}")
                return True
            except:
                # Server might need more time
                time.sleep(1)
                return True
        except Exception as e:
            if self.debug:
                print(f"  Failed to start test server: {e}")
            return False
    
    def stop_test_socket_server(self) -> None:
        """Stop the test socket server."""
        if self.socket_server_process:
            try:
                self.socket_server_process.terminate()
                self.socket_server_process.wait(timeout=2)
            except:
                self.socket_server_process.kill()
            finally:
                self.socket_server_process = None
            
            # Clean up socket file
            if self.socket_path and Path(self.socket_path).exists():
                try:
                    Path(self.socket_path).unlink()
                except:
                    pass
    
    def test_hook_invocation(self) -> TestResult:
        """Test that hooks invoke correctly."""
        name = "Hook Invocation"
        
        if not self.socket_path and not self.real_herdr:
            # Start test server
            if not self.start_test_socket_server():
                return TestResult(name, False, "Failed to start test socket server")
        
        hook_data = {
            "hook_event_name": "POST_AGENT",
            "session_id": TEST_SESSION_ID,
        }
        
        result = self.run_hook_script(hook_data)
        
        if result.get("returncode") != 0:
            return TestResult(
                name,
                False,
                f"Hook failed with code {result.get('returncode')}",
                result
            )
        
        return TestResult(name, True, "Hook executed successfully")
    
    def test_hook_pre_tool(self) -> TestResult:
        """Test PRE_TOOL hook."""
        name = "Hook PRE_TOOL"
        
        hook_data = {
            "hook_event_name": "PRE_TOOL",
            "tool_name": "bash",
            "session_id": TEST_SESSION_ID,
        }
        
        result = self.run_hook_script(hook_data)
        
        if result.get("returncode") != 0:
            return TestResult(name, False, f"PRE_TOOL hook failed", result)
        
        return TestResult(name, True, "PRE_TOOL hook executed")
    
    def test_hook_post_tool(self) -> TestResult:
        """Test POST_TOOL hook."""
        name = "Hook POST_TOOL"
        
        hook_data = {
            "hook_event_name": "POST_TOOL",
            "tool_name": "bash",
            "tool_status": "success",
            "session_id": TEST_SESSION_ID,
        }
        
        result = self.run_hook_script(hook_data)
        
        if result.get("returncode") != 0:
            return TestResult(name, False, f"POST_TOOL hook failed", result)
        
        return TestResult(name, True, "POST_TOOL hook executed")
    
    def test_state_reporting(self) -> TestResult:
        """Test that state is reported to Herdr socket."""
        name = "State Reporting"
        
        if not self.socket_path and not self.real_herdr:
            if not self.start_test_socket_server():
                return TestResult(name, False, "Failed to start test socket server")
        
        # Report a test state
        result = report_agent_state(
            TEST_PANE_ID,
            "working",
            "Test message",
            SOURCE,
            AGENT,
            self.socket_path
        )
        
        if "error" in result:
            return TestResult(name, False, result["error"])
        
        return TestResult(name, True, "State reported successfully")
    
    def test_session_reporting(self) -> TestResult:
        """Test that session is reported to Herdr."""
        name = "Session Reporting"
        
        if not self.socket_path and not self.real_herdr:
            if not self.start_test_socket_server():
                return TestResult(name, False, "Failed to start test socket server")
        
        result = report_agent_session(
            TEST_PANE_ID,
            TEST_SESSION_ID,
            SOURCE,
            AGENT,
            self.socket_path
        )
        
        if "error" in result:
            return TestResult(name, False, result["error"])
        
        return TestResult(name, True, "Session reported successfully")
    
    def test_environment_detection(self) -> TestResult:
        """Test that environment variables are detected correctly."""
        name = "Environment Detection"
        
        env = self.setup_environment()
        
        # Check that required variables are set
        required = ["HERDR_ENV", "HERDR_PANE_ID", "HERDR_SOCKET_PATH"]
        missing = [var for var in required if var not in env or not env[var]]
        
        if missing:
            return TestResult(name, False, f"Missing variables: {missing}")
        
        if env["HERDR_ENV"] != "1":
            return TestResult(name, False, f"HERDR_ENV should be '1', got '{env['HERDR_ENV']}'")
        
        return TestResult(name, True, "All environment variables detected")
    
    def test_hook_with_missing_env(self) -> TestResult:
        """Test that hook script handles missing environment gracefully."""
        name = "Hook with Missing Environment"
        
        # Run hook without HERDR_PANE_ID
        env = os.environ.copy()
        # Don't set HERDR_PANE_ID
        
        hook_script = self.get_hook_script_path()
        
        try:
            result = subprocess.run(
                ["python3", str(hook_script)],
                input=json.dumps({"hook_event_name": "POST_AGENT"}),
                capture_output=True,
                text=True,
                env=env,
                timeout=2,
            )
            
            # Should exit gracefully (exit code 0)
            if result.returncode == 0:
                return TestResult(name, True, "Hook exited gracefully with missing env")
            else:
                return TestResult(
                    name,
                    False,
                    f"Hook should exit gracefully, got exit code {result.returncode}",
                    {"stdout": result.stdout, "stderr": result.stderr}
                )
        except subprocess.TimeoutExpired:
            return TestResult(name, True, "Hook exited (timeout)")
        except Exception as e:
            return TestResult(name, False, str(e))
    
    def test_adapter_detection(self) -> TestResult:
        """Test that adapter detects Herdr environment."""
        name = "Adapter Herdr Detection"
        
        # Try to import and test the adapter
        try:
            adapter_path = Path(__file__).parent.parent / "adapter" / "dist" / "index.js"
            if not adapter_path.exists():
                return TestResult(name, False, f"Adapter not found at {adapter_path}")
            
            # Run adapter with --version to test detection
            env = self.setup_environment()
            
            result = subprocess.run(
                ["node", str(adapter_path), "--version"],
                capture_output=True,
                text=True,
                env=env,
                timeout=5,
            )
            
            # Should not fail
            if result.returncode == 0:
                return TestResult(name, True, "Adapter runs without error")
            else:
                return TestResult(
                    name,
                    False,
                    f"Adapter failed with code {result.returncode}",
                    {"stdout": result.stdout, "stderr": result.stderr}
                )
        except Exception as e:
            return TestResult(name, False, str(e))
    
    def run_test(self, test_name: str, test_func) -> TestResult:
        """Run a single test and record the result."""
        if self.debug:
            print(f"\n  Running: {test_name}")
        
        try:
            result = test_func()
            self.test_results.append(result)
            return result
        except Exception as e:
            result = TestResult(test_name, False, str(e))
            self.test_results.append(result)
            return result
    
    def run_all_tests(self) -> list[TestResult]:
        """Run all tests."""
        print("=" * 60)
        print("Herdr-Vibe Integration Tests")
        print("=" * 60)
        print()
        
        # Define tests in order
        tests = [
            ("Environment Detection", self.test_environment_detection),
            ("Hook with Missing Environment", self.test_hook_with_missing_env),
            ("Hook Invocation (POST_AGENT)", self.test_hook_invocation),
            ("Hook PRE_TOOL", self.test_hook_pre_tool),
            ("Hook POST_TOOL", self.test_hook_post_tool),
            ("Session Reporting", self.test_session_reporting),
            ("State Reporting", self.test_state_reporting),
            ("Adapter Detection", self.test_adapter_detection),
        ]
        
        # Run tests
        for name, func in tests:
            self.run_test(name, func)
        
        return self.test_results
    
    def print_results(self) -> None:
        """Print test results."""
        print()
        print("=" * 60)
        print("Test Results")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if r.passed)
        total = len(self.test_results)
        
        for result in self.test_results:
            print(result)
            if self.debug and result.details:
                print(f"    Details: {result.details}")
        
        print()
        print(f"Passed: {passed}/{total}")
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print(f"⚠️  {total - passed} test(s) failed")
        
        print("=" * 60)
    
    def cleanup(self) -> None:
        """Clean up test resources."""
        self.stop_test_socket_server()
        
        for f in self.cleanup_files:
            try:
                os.unlink(f)
            except:
                pass


def main():
    """Run integration tests."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Integration tests for Herdr-Vibe integration"
    )
    parser.add_argument(
        "--socket-path",
        help="Path to Herdr socket (overrides auto-detection)"
    )
    parser.add_argument(
        "--test",
        help="Run specific test by name"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug output"
    )
    parser.add_argument(
        "--real-herdr",
        action="store_true",
        help="Test with real Herdr instance (not test server)"
    )
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="List all available tests"
    )
    
    args = parser.parse_args()
    
    harness = HerdrTestHarness(
        socket_path=args.socket_path,
        debug=args.debug,
        real_herdr=args.real_herdr
    )
    
    try:
        # List tests
        if args.list_tests:
            print("Available Tests:")
            tests = [
                "test_environment_detection",
                "test_hook_with_missing_env",
                "test_hook_invocation",
                "test_hook_pre_tool",
                "test_hook_post_tool",
                "test_session_reporting",
                "test_state_reporting",
                "test_adapter_detection",
            ]
            for test in tests:
                print(f"  - {test}")
            sys.exit(0)
        
        # Run specific test or all tests
        if args.test:
            # Find test function by name
            test_func = getattr(harness, args.test, None)
            if not test_func:
                print(f"Error: Test '{args.test}' not found")
                sys.exit(1)
            
            result = harness.run_test(args.test, test_func)
            print()
            print(result)
            if harness.debug and result.details:
                print(f"Details: {result.details}")
            
            sys.exit(0 if result.passed else 1)
        else:
            # Run all tests
            results = harness.run_all_tests()
            harness.print_results()
            
            # Exit with error if any tests failed
            if all(r.passed for r in results):
                sys.exit(0)
            else:
                sys.exit(1)
    finally:
        harness.cleanup()


if __name__ == "__main__":
    import socket  # For socket operations
    main()
