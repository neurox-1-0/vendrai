import {
  casePath,
  expect,
  runGraphFor,
  test,
  waitForCaseStatus,
} from "../support/fixtures";

/**
 * The most important failure scenario in the suite.
 *
 * The central claim of this architecture is that the product degrades to
 * deterministic controls when the LLM is unavailable. That claim is either
 * demonstrated here or it is marketing.
 *
 * Two things must hold when Gemini is gone:
 *   1. Every deterministic check still completes and still produces findings.
 *   2. Nothing fabricates reasoning to fill the gap. The failure is typed,
 *      named, and visible.
 */

test.describe("LLM provider outage", () => {
  test("deterministic controls still complete with no LLM available", async ({
    pageAs,
  }) => {
    const admin = await pageAs("admin");

    // The API exposes the provider state through its own integration health
    // endpoint; asserting it up front means a passing test cannot be a test
    // that quietly ran with a working key.
    const health = await (
      await admin.request.get("/api/v1/admin/integration-health")
    ).json();
    test.skip(
      health.checks?.llm?.status === "HEALTHY",
      "This test requires the LLM provider to be unavailable. Run it with " +
        "GEMINI_API_KEY unset, or point it at an invalid key.",
    );

    const requester = await pageAs("requester");
    await requester.goto("/cases/new");
    await requester
      .getByLabel(/supplier|vendor|title/i)
      .first()
      .fill("LLM outage degradation case");
    await requester.setInputFiles(
      'input[type="file"]',
      casePath(
        "VO-002_potential_duplicate_vendor",
        "01_supplier_onboarding_form.pdf",
        "02_tax_registration_certificate.pdf",
        "03_bank_account_confirmation.pdf",
      ),
    );
    const created = requester.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/cases") &&
        response.request().method() === "POST" &&
        response.ok(),
    );
    await requester.getByRole("button", { name: /submit|create/i }).click();
    await created;

    const caseId = new URL(requester.url())
      .pathname.split("/")
      .filter(Boolean)
      .pop()!;

    await waitForCaseStatus(requester, caseId, [
      "VERIFICATION_FAILED",
      "DUPLICATE_REVIEW",
      "RISK_REVIEW",
      "NEEDS_CLARIFICATION",
      "APPROVAL_PENDING",
    ]);

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

    await test.step("the planner failure is typed and visible", async () => {
      expect(byName.goal_planner).toBe("FAILED");
      const planner = graph.nodes.find(
        (node: { node_name: string }) => node.node_name === "goal_planner",
      );
      expect(
        planner.error.error_code,
        "the planner failed without a reason code",
      ).toBeTruthy();
    });

    await test.step("every mandatory deterministic check still ran", async () => {
      for (const capability of [
        "document_intelligence",
        "duplicate_detection",
        "sanctions_screening",
        "document_completeness",
        "supplier_controls",
        "injection_scan",
      ]) {
        expect(
          byName[capability],
          `${capability} did not run without the LLM, so the product did not ` +
            "degrade to deterministic controls",
        ).toBeTruthy();
        expect(byName[capability]).not.toBe("FAILED");
      }
    });

    await test.step("the duplicate was still detected", async () => {
      const evidence = await (
        await requester.request.get(`/api/v1/cases/${caseId}/evidence`)
      ).json();
      expect(
        evidence.items.some(
          (item: { reason_code: string }) =>
            item.reason_code === "DUPLICATE_SCORE",
        ),
        "the deterministic duplicate check did not survive the LLM outage",
      ).toBe(true);
    });

    await test.step("no reasoning was fabricated to fill the gap", async () => {
      for (const node of graph.nodes) {
        if (["gemini_contradiction", "gemini_evidence_critique"].includes(node.node_name)) {
          expect(
            ["FAILED", "BLOCKED", "SKIPPED"],
            `${node.node_name} reported ${node.status} with no provider available`,
          ).toContain(node.status);
        }
      }
    });
  });
});
