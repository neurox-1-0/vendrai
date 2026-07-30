import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

const PROJECT_ROOT = path.resolve(__dirname, "../../../..");

/**
 * Manipulate the real stack for failure injection.
 *
 * Stopping an actual container is preferred over mocking, because the point is
 * to exercise the real failure path - connection refusal, timeout handling,
 * retry behaviour - and mocks systematically get all three wrong. A mocked
 * Qdrant outage returns a tidy exception; a stopped Qdrant makes the client
 * hang until its timeout, which is the case that actually breaks products.
 */
async function compose(...args: string[]): Promise<string> {
  const { stdout } = await run("docker", ["compose", ...args], {
    cwd: PROJECT_ROOT,
    timeout: 120_000,
  });
  return stdout;
}

export async function stopService(service: string): Promise<void> {
  await compose("stop", service);
}

export async function startService(service: string): Promise<void> {
  await compose("start", service);
}

export async function restartService(service: string): Promise<void> {
  await compose("restart", service);
}

/**
 * Run a body with a service stopped, and restart it whatever happens.
 *
 * A failure test that leaves the stack broken takes every later test with it,
 * and the resulting cascade hides which one actually failed.
 */
export async function withServiceStopped<T>(
  service: string,
  body: () => Promise<T>,
): Promise<T> {
  await stopService(service);
  try {
    return await body();
  } finally {
    await startService(service);
  }
}

/** Wait for a service to report healthy again after a restart. */
export async function waitForHealthy(
  service: string,
  { timeoutMs = 120_000, intervalMs = 2_000 } = {},
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await compose(
      "ps",
      "--format",
      "{{.Service}}\t{{.Health}}",
    );
    const line = status
      .split("\n")
      .find((row) => row.startsWith(`${service}\t`));
    if (line && /healthy/i.test(line)) return;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(
    `${service} did not become healthy within ${timeoutMs}ms after restart`,
  );
}
