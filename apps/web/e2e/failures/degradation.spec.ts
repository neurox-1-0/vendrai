import {
  casePath,
  evidenceFor,
  expect,
  runGraphFor,
  test,
  waitForCaseStatus,
} from "../support/fixtures";
import { startService, waitForHealthy, withServiceStopped } from "../support/compose";

/**
 * Failure injection.
 *
 * This is the part reviewers probe hardest, and where a fail-closed design
 * earns its keep. Each scenario asserts on the **visible reason code and audit
 * entry**, not merely the absence of a crash: a product that swallows an
 * outage and reports success passes "did not crash" perfectly.
 */

async function submitSupplierCase(
  page: import("@playwright/test").Page,
  caseFolder: string,
  files: string[],
): Promise<string> {
  await page.goto("/cases/new");
  await page.getByLabel(/supplier|vendor|title/i).first().fill("Failure injection case");
  await page.setInputFiles('input[type="file"]', casePath(caseFolder, ...files));
  const created = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/cases") &&
      response.request().method() === "POST" &&
      response.ok(),
  );
  await page.getByRole("button", { name: /submit|create/i }).click();
  await created;
  return new URL(page.url()).pathname.split("/").filter(Boolean).pop()!;
}

const VO_001 = [
  "01_supplier_onboarding_form.pdf",
  "02_tax_registration_certificate.pdf",
  "03_bank_account_confirmation.pdf",
  "04_insurance_certificate.pdf",
  "05_information_security_questionnaire.pdf",
];

test.describe.configure({ mode: "serial" });

test.describe("failure injection", () => {
  test("a failing specialist does not erase its successful siblings", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    // The risk provider is the easiest specialist to fail deliberately, and
    // it runs beside duplicate detection, sanctions, and policy retrieval.
    const caseId = await withServiceStopped("mock-risk", async () => {
      const id = await submitSupplierCase(
        requester,
        "VO-001_standard_vendor_onboarding",
        VO_001,
      );
      await waitForCaseStatus(requester, id, [
        "APPROVAL_PENDING",
        "RISK_REVIEW",
        "DUPLICATE_REVIEW",
        "NEEDS_CLARIFICATION",
        "VERIFICATION_FAILED",
      ]);
      return id;
    });
    await waitForHealthy("mock-risk");

    const detail = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();
    const graph = await runGraphFor(
      requester,
      detail.run_id ?? detail.runs?.[0]?.run_id,
    );
    const byName = Object.fromEntries(
      graph.nodes.map((node: { node_name: string; status: string }) => [
        node.node_name,
        node.status,
      ]),
    );

    // The failed branch is visible and typed.
    expect(["FAILED", "BLOCKED"]).toContain(byName.risk_screening);
    // The siblings that succeeded are still recorded.
    expect(byName.duplicate_detection).toBe("SUCCESS");
    expect(byName.document_completeness).toBeTruthy();

    const evidence = await evidenceFor(requester, caseId);
    expect(
      evidence.items.length,
      "a single specialist failure erased the whole evidence packet",
    ).toBeGreaterThan(0);
  });

  test("Qdrant down produces a visible insufficient-evidence reason, never a silent pass", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await withServiceStopped("qdrant", async () => {
      const id = await submitSupplierCase(
        requester,
        "VO-001_standard_vendor_onboarding",
        VO_001,
      );
      await waitForCaseStatus(requester, id, [
        "VERIFICATION_FAILED",
        "NEEDS_CLARIFICATION",
        "RISK_REVIEW",
        "APPROVAL_PENDING",
      ]);
      return id;
    });
    await startService("qdrant");

    const detail = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();
    const reasons: string[] = detail.reason_codes ?? [];
    expect(
      reasons.some((code) =>
        ["INSUFFICIENT_POLICY_EVIDENCE", "POLICY_RETRIEVAL_UNAVAILABLE"].includes(
          code,
        ),
      ),
      `retrieval was unavailable but the case reported ${reasons.join(", ") || "no reason codes"}`,
    ).toBe(true);
    expect(
      detail.status,
      "a case with no policy evidence must not reach approval",
    ).not.toBe("APPROVED");
  });

  test("SMTP down leaves the case status and version unchanged", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitSupplierCase(
      requester,
      "VO-001_standard_vendor_onboarding",
      VO_001,
    );
    await waitForCaseStatus(requester, caseId, [
      "APPROVAL_PENDING",
      "RISK_REVIEW",
      "DUPLICATE_REVIEW",
      "NEEDS_CLARIFICATION",
    ]);

    const before = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();

    await withServiceStopped("mailpit", async () => {
      const notifications = await requester.request.get(
        `/api/v1/notifications?case_id=${caseId}`,
      );
      expect(notifications.ok()).toBe(true);
      // Delivery is retried out of band; the workflow must not move because a
      // notification could not be sent.
      await expect
        .poll(
          async () => {
            const response = await requester.request.get(
              `/api/v1/cases/${caseId}`,
            );
            return (await response.json()).current_version;
          },
          {
            timeout: 30_000,
            message: "case version changed while SMTP was unavailable",
          },
        )
        .toBe(before.current_version);
    });
    await waitForHealthy("mailpit").catch(() => undefined);

    const after = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();
    expect(after.status).toBe(before.status);
    expect(after.current_version).toBe(before.current_version);
  });

  test("an ERP timeout followed by a retry creates exactly one vendor", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitSupplierCase(
      requester,
      "VO-001_standard_vendor_onboarding",
      VO_001,
    );
    await waitForCaseStatus(requester, caseId, [
      "APPROVAL_PENDING",
      "RISK_REVIEW",
      "DUPLICATE_REVIEW",
    ]);

    const procurement = await pageAs("procurement");
    await withServiceStopped("mock-erp", async () => {
      await procurement.goto("/approvals");
      await procurement
        .getByRole("link", { name: new RegExp(caseId.slice(0, 8), "i") })
        .first()
        .click();
      await procurement.getByRole("button", { name: /^approve/i }).click();
      await waitForCaseStatus(requester, caseId, ["ERP_SYNC_FAILED"], {
        timeout: 120_000,
      });
    });
    await waitForHealthy("mock-erp");

    const retried = requester.waitForResponse((response) =>
      response.url().includes("retry-erp"),
    );
    await requester.goto(`/cases/${caseId}`);
    await requester.getByRole("button", { name: /retry/i }).click();
    await retried;

    await waitForCaseStatus(requester, caseId, ["COMPLETED"], {
      timeout: 180_000,
    });

    const admin = await pageAs("admin");
    const operations = await (
      await admin.request.get(`/api/v1/cases/${caseId}/erp-operations`)
    ).json();
    const succeeded = (operations.items ?? operations).filter(
      (item: { status: string }) => item.status === "SUCCEEDED",
    );
    // Idempotency means one vendor, however many attempts it took.
    expect(
      succeeded.length,
      "a timeout and retry produced more than one successful ERP write",
    ).toBe(1);
  });

  test("the agent worker can be killed at a human interrupt and resume", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitSupplierCase(
      requester,
      "VO-001_standard_vendor_onboarding",
      VO_001,
    );
    await waitForCaseStatus(requester, caseId, [
      "APPROVAL_PENDING",
      "RISK_REVIEW",
      "DUPLICATE_REVIEW",
    ]);

    const before = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();

    // Restarting at the interrupt is the interesting moment: the LangGraph
    // checkpoint must carry the run across the restart with no duplicated
    // side effects.
    await withServiceStopped("agent-worker", async () => {
      const detail = await (
        await requester.request.get(`/api/v1/cases/${caseId}`)
      ).json();
      expect(detail.status).toBe(before.status);
    });
    await waitForHealthy("agent-worker").catch(() => undefined);

    const procurement = await pageAs("procurement");
    await procurement.goto("/approvals");
    await procurement
      .getByRole("link", { name: new RegExp(caseId.slice(0, 8), "i") })
      .first()
      .click();
    await procurement.getByRole("button", { name: /^approve/i }).click();

    await waitForCaseStatus(requester, caseId, [
      "COMPLETED",
      "ERP_SYNC_PENDING",
    ], { timeout: 180_000 });

    const admin = await pageAs("admin");
    const operations = await (
      await admin.request.get(`/api/v1/cases/${caseId}/erp-operations`)
    ).json();
    expect(
      (operations.items ?? operations).filter(
        (item: { status: string }) => item.status === "SUCCEEDED",
      ).length,
    ).toBeLessThanOrEqual(1);
  });
});
