import { defineConfig, devices } from "@playwright/test";

/**
 * Acceptance tests run against the **real running stack**, never a mocked
 * backend.
 *
 * That is the whole point. On 2026-07-28 this repository had 82 passing
 * backend tests, clean ESLint, and clean TypeScript - and could not complete a
 * single document upload, because both agent workers were crash-looping, every
 * MinIO URL returned connection-refused, and every generated-client call 404'd
 * on a doubled path prefix. None of it was visible to a suite that substitutes
 * SQLite, mocks, and MockTransport for the real infrastructure.
 *
 * A Playwright suite against mocks would repeat exactly that mistake.
 *
 * Start the stack first:
 *   ./scripts/stack.sh product-up
 *   ./scripts/stack.sh bootstrap
 *   ./scripts/stack.sh doctor
 */
const WEB_URL = process.env.NEUROX_WEB_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  // Journeys wait on real document processing, OCR, and agent workflows.
  timeout: 5 * 60 * 1000,
  expect: { timeout: 30 * 1000 },
  // A flaky acceptance suite gets ignored, then deleted. Retries hide flake
  // rather than fixing it, so locally there are none; CI gets one retry only
  // to absorb genuine infrastructure noise.
  retries: process.env.CI ? 1 : 0,
  // Each test creates its own case, so they do not depend on each other - but
  // they share one stack, and a single worker keeps failure diagnosis sane.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["list"]],
  use: {
    baseURL: WEB_URL,
    // Artefacts on failure only. A screenshot gallery of passing runs is
    // noise that makes the real failures harder to find.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 30 * 1000,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "journeys",
      testMatch: /journeys\/.*\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"] },
    },
    {
      // Failure injection stops and starts infrastructure, so it must not run
      // beside the golden journeys.
      name: "failure-injection",
      testMatch: /failures\/.*\.spec\.ts/,
      dependencies: ["journeys"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
