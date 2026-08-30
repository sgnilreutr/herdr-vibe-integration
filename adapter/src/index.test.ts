/**
 * Tests for Herdr-Vibe adapter
 *
 * Tests the core functionality: Herdr detection, environment handling,
 * and state reporting.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Import the module functions directly
import { isInHerdr, getHerdrEnv, SOURCE, AGENT } from "./index";

// Mock process.env for testing
const originalEnv = { ...process.env };

beforeEach(() => {
  // Reset environment before each test - clear Herdr-specific vars
  process.env = {
    ...originalEnv,
  };
  // Explicitly clear Herdr vars
  delete process.env.HERDR_ENV;
  delete process.env.HERDR_PANE_ID;
  delete process.env.HERDR_BIN_PATH;
  delete process.env.HERDR_SOCKET_PATH;
  vi.restoreAllMocks();
});

afterEach(() => {
  // Restore environment after each test
  process.env = originalEnv;
});

// ============================================================================
// Herdr Environment Detection Tests
// ============================================================================

describe("Herdr Environment Detection", () => {
  it("should detect Herdr environment when all variables are set", () => {
    process.env.HERDR_ENV = "1";
    process.env.HERDR_PANE_ID = "w1:p1";
    process.env.HERDR_BIN_PATH = "/usr/bin/herdr";

    expect(isInHerdr()).toBe(true);
    const env = getHerdrEnv();
    expect(env.paneId).toBe("w1:p1");
    expect(env.herdrBin).toBe("/usr/bin/herdr");
    // socketPath may or may not be set
    expect(env.socketPath).toBeUndefined();
  });

  it("should not detect Herdr environment when HERDR_ENV is not 1", () => {
    process.env.HERDR_ENV = "0";
    process.env.HERDR_PANE_ID = "w1:p1";
    process.env.HERDR_BIN_PATH = "/usr/bin/herdr";

    expect(isInHerdr()).toBe(false);
  });

  it("should not detect Herdr environment when HERDR_PANE_ID is missing", () => {
    process.env.HERDR_ENV = "1";
    // HERDR_PANE_ID not set
    process.env.HERDR_BIN_PATH = "/usr/bin/herdr";

    expect(isInHerdr()).toBe(false);
  });

  it("should not detect Herdr environment when HERDR_BIN_PATH is missing", () => {
    process.env.HERDR_ENV = "1";
    process.env.HERDR_PANE_ID = "w1:p1";
    // HERDR_BIN_PATH not set

    expect(isInHerdr()).toBe(false);
  });
});

// ============================================================================
// Configuration Tests
// ============================================================================

describe("Configuration", () => {
  it("should have correct SOURCE constant", () => {
    expect(SOURCE).toBe("herdr:vibe");
  });

  it("should have correct AGENT constant", () => {
    expect(AGENT).toBe("vibe");
  });
});
