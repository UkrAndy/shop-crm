import { defineConfig, devices } from '@playwright/test'

// Both must share a host, not merely a machine. `localhost:3000` and
// `127.0.0.1:8000` are *different sites* to a browser, so a `SameSite=Lax`
// session cookie set by one is never sent to the other and every login silently
// fails to stick. Overriding one of these alone reintroduces that.
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000'
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'

/**
 * End-to-end suite.
 *
 * Runs against the real stack — Nuxt, FastAPI and PostgreSQL — because the
 * behaviour under test is precisely what a mock would paper over: whether the
 * session cookie survives SSR, and whether organization scope is enforced by
 * the server rather than by the UI.
 *
 * `globalSetup` migrates and seeds, so `pnpm test:e2e` is a single command
 * given a running database. Both servers are started here too, and reused when
 * they are already up locally.
 */
export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',

  // Serial in CI: the suite shares one database, and the point of these tests
  // is user-visible flow rather than throughput. Real concurrency is Issue 26's
  // job, at the API level where it can be reasoned about.
  fullyParallel: false,
  workers: 1,

  // A test that only passes sometimes is worse than one that fails, so a
  // `test.only` left behind fails the build instead of silently shrinking it.
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,

  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],

  webServer: [
    {
      command: 'uv run uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: `${API_URL}/api/v1/health/live`,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 120_000,
    },
    {
      command: 'pnpm dev --port 3000',
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 180_000,
    },
  ],
})
