import { defineConfig } from 'vitest/config'

// Current coverage baseline (from coverage report 2026-09-01):
// Statements: 34.12% (72/211)
// Branches: 63.15% (12/19)
// Functions: 53.84% (7/13)
// Lines: 34.12% (72/211)
//
// Locking in current numbers so coverage can NEVER go down

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    coverage: {
      enabled: true,
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './coverage',
      include: ['src/index.ts'],
      exclude: [
        '**/*.test.*',
        '**/*.spec.*',
        '**/coverage/**',
        '**/node_modules/**',
        '**/dist/**',
        '**/htmlcov/**',
        '**/vitest.config.*',
      ],
      // Baseline thresholds - locked at current coverage (2026-09-01)
      // These will FAIL the test run if coverage drops below
      thresholds: {
        statements: 34.12,
        branches: 63.15,
        functions: 53.84,
        lines: 34.12,
      },
    },
  },
})
