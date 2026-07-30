import path from "node:path";
import { expect, type Page, test as base } from "@playwright/test";

import { type Role, storageStatePath } from "./roles";

/**
 * Helpers shared by the journeys.
 *
 * One rule runs through all of them: **never `waitForTimeout`.** Every wait is
 * on an API response, an SSE event, or explicit UI state, and every wait is
 * bounded with a message naming what was expected. A sleep that is long enough
 * today is a flake tomorrow, and a flaky acceptance suite gets ignored and then
 * deleted.
 */

export const CORPUS_ROOT = path.resolve(
  __dirname,
  "../../../../Vendrai_Procurement_Document_Corpus_v2",
);

export function casePath(caseFolder: string, ...files: string[]): string[] {
  return files.map((file) => path.join(CORPUS_ROOT, "cases", caseFolder, file));
}

export const test = base.extend<{
  /** Open a page authenticated as a specific role. */
  pageAs: (role: Role) => Promise<Page>;
}>({
  pageAs: async ({ browser }, use) => {
    const contexts: Awaited<ReturnType<typeof browser.newContext>>[] = [];
    await use(async (role: Role) => {
      const context = await browser.newContext({
        storageState: storageStatePath(role),
      });
      contexts.push(context);
      return context.newPage();
    });
    await Promise.all(contexts.map((context) => context.close()));
  },
});

export { expect };

/**
 * Wait for a case to reach one of the expected statuses.
 *
 * Polls the case API rather than the rendered page, because the status is the
 * fact and the page is one of several views of it. The failure message names
 * the status actually reached, which is almost always the thing you need.
 */
export async function waitForCaseStatus(
  page: Page,
  caseId: string,
  expected: string[],
  { timeout = 240_000 }: { timeout?: number } = {},
): Promise<string> {
  let last = "unknown";
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/api/v1/cases/${caseId}`);
        last = response.ok()
          ? (await response.json()).status
          : `http ${response.status()}`;
        return expected.includes(last);
      },
      {
        timeout,
        // The message is fixed at poll time, so the status actually reached is
        // reported by the assertion below rather than here.
        message: `case ${caseId} did not settle; check the agent worker logs`,
      },
    )
    .toBe(true);
  expect(
    expected,
    `case ${caseId} reached ${last}, not one of ${expected.join(", ")}`,
  ).toContain(last);
  return last;
}

/** Fetch the evidence packet for assertions on values, not just rendering. */
export async function evidenceFor(page: Page, caseId: string) {
  const response = await page.request.get(`/api/v1/cases/${caseId}/evidence`);
  expect(
    response.ok(),
    `evidence for case ${caseId} was not readable (${response.status()})`,
  ).toBe(true);
  return response.json();
}

/** Fetch the run graph, to assert on which capabilities actually executed. */
export async function runGraphFor(page: Page, runId: string) {
  const response = await page.request.get(`/api/v1/runs/${runId}/graph`);
  expect(
    response.ok(),
    `run graph ${runId} was not readable (${response.status()})`,
  ).toBe(true);
  return response.json();
}

/** The audit trail. An action with no audit entry did not really happen. */
export async function auditFor(page: Page, caseId: string) {
  const response = await page.request.get(`/api/v1/cases/${caseId}/audit`);
  expect(
    response.ok(),
    `audit for case ${caseId} was not readable (${response.status()})`,
  ).toBe(true);
  return response.json();
}
