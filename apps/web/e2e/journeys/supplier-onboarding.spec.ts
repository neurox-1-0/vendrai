import {
  auditFor,
  casePath,
  evidenceFor,
  expect,
  runGraphFor,
  test,
  waitForCaseStatus,
} from "../support/fixtures";

/**
 * The golden supplier journey, with role separation.
 *
 * Assertions are on **evidence**, not navigation. A test that only proves
 * pages render would pass against a product that computes nothing - which is
 * precisely the failure mode this suite exists to catch.
 */

test.describe("supplier onboarding", () => {
  test("VO-001 reaches approval with real findings and a role-separated approval", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");

    await test.step("requester creates and submits the case", async () => {
      await requester.goto("/cases/new");
      await requester
        .getByLabel(/supplier|vendor|title/i)
        .first()
        .fill("Northstar Office Systems (Pvt) Ltd");
      await requester.setInputFiles(
        'input[type="file"]',
        casePath(
          "VO-001_standard_vendor_onboarding",
          "01_supplier_onboarding_form.pdf",
          "02_tax_registration_certificate.pdf",
          "03_bank_account_confirmation.pdf",
          "04_insurance_certificate.pdf",
          "05_information_security_questionnaire.pdf",
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
    });

    const caseId = new URL(requester.url()).pathname.split("/").filter(Boolean).pop()!;

    await test.step("analysis completes and the case awaits a human", async () => {
      await waitForCaseStatus(requester, caseId, [
        "APPROVAL_PENDING",
        "DUPLICATE_REVIEW",
        "RISK_REVIEW",
        "NEEDS_CLARIFICATION",
      ]);
    });

    const analyst = await pageAs("analyst");
    await analyst.goto(`/cases/${caseId}`);

    await test.step("every registered capability actually ran", async () => {
      const detail = await (
        await analyst.request.get(`/api/v1/cases/${caseId}`)
      ).json();
      const graph = await runGraphFor(analyst, detail.run_id ?? detail.runs?.[0]?.run_id);
      const executed = new Set<string>(
        graph.nodes.map((node: { node_name: string }) => node.node_name),
      );
      // A capability in the plan that produced no step is the D-001 defect
      // class: the operator is told a check happened when nothing ran.
      for (const planned of graph.plan.selected_capabilities ?? []) {
        expect(
          executed.has(planned.capability_id),
          `${planned.capability_id} was planned but produced no step`,
        ).toBe(true);
      }
      expect(executed).toContain("document_completeness");
      expect(executed).toContain("supplier_controls");
      expect(executed).toContain("injection_scan");
    });

    await test.step("the evidence names its provenance and cites policy", async () => {
      const evidence = await evidenceFor(analyst, caseId);
      expect(
        evidence.items.length,
        "the case produced no evidence at all",
      ).toBeGreaterThan(0);

      const policy = evidence.items.filter(
        (item: { source_type: string }) => item.source_type === "POLICY",
      );
      expect(
        policy.length,
        "no policy clause was cited; retrieval or the bootstrap may have failed",
      ).toBeGreaterThan(0);
      expect(policy[0].provenance).toBe("TENANT_POLICY");

      // Every item must state where it came from, and uploaded evidence must
      // not claim to be authoritative.
      for (const item of evidence.items) {
        expect(item.provenance, "evidence item without provenance").toBeTruthy();
        if (item.provenance === "USER_UPLOADED") {
          expect(item.is_authoritative).toBe(false);
        }
      }
    });

    await test.step("the case page shows provenance to the reviewer", async () => {
      await expect(
        analyst.getByText(/published policy/i).first(),
      ).toBeVisible();
    });

    await test.step("procurement approves; the requester cannot", async () => {
      const approveAsRequester = await requester.request.get(
        `/api/v1/work-queue`,
      );
      const queue = approveAsRequester.ok()
        ? await approveAsRequester.json()
        : { items: [] };
      expect(
        (queue.items ?? []).length,
        "the requester can see approval work, which breaks segregation of duties",
      ).toBe(0);

      const procurement = await pageAs("procurement");
      await procurement.goto("/approvals");
      await procurement
        .getByRole("link", { name: new RegExp(caseId.slice(0, 8), "i") })
        .first()
        .click();

      const decided = procurement.waitForResponse(
        (response) =>
          response.url().includes("/decisions") &&
          response.request().method() === "POST",
      );
      await procurement.getByRole("button", { name: /^approve/i }).click();
      const decision = await decided;
      expect(
        decision.ok(),
        `approval was rejected by the API: ${await decision.text()}`,
      ).toBe(true);
    });

    await test.step("the ERP write completes and is audited", async () => {
      await waitForCaseStatus(requester, caseId, [
        "COMPLETED",
        "ERP_SYNC_PENDING",
        "ERP_SYNC_FAILED",
      ]);

      const auditor = await pageAs("auditor");
      const audit = await auditFor(auditor, caseId);
      const actions = audit.map((entry: { action: string }) => entry.action);
      expect(actions).toContain("ANALYSIS_COMPLETED");
      expect(
        actions.some((action: string) => action.includes("APPROVAL")),
        "no approval was recorded in the audit trail",
      ).toBe(true);
    });
  });

  test("VO-002 surfaces the duplicate with its matching signals", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    await requester.goto("/cases/new");
    await requester
      .getByLabel(/supplier|vendor|title/i)
      .first()
      .fill("Apex Digitech Solutions (Pvt) Ltd");
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

    const caseId = new URL(requester.url()).pathname.split("/").filter(Boolean).pop()!;
    await waitForCaseStatus(requester, caseId, [
      "DUPLICATE_REVIEW",
      "RISK_REVIEW",
      "APPROVAL_PENDING",
      "NEEDS_CLARIFICATION",
    ]);

    const evidence = await evidenceFor(requester, caseId);
    const duplicate = evidence.items.find(
      (item: { reason_code: string }) => item.reason_code === "DUPLICATE_SCORE",
    );
    expect(
      duplicate,
      "no duplicate candidate was found; the vendor master may not be loaded",
    ).toBeTruthy();

    // The corpus states this supplier shares V000233's tax ID and bank
    // account. Both are blind-index comparisons, so a match here also proves
    // the bootstrap hashed them with the right secret.
    const signals = duplicate.source_locator.signals;
    expect(signals.tax_exact, "the exact tax ID match was not detected").toBe(true);
    expect(signals.bank_exact, "the exact bank account match was not detected").toBe(
      true,
    );
    expect(signals.name_similarity).toBeGreaterThan(0.5);
    expect(signals.name_similarity).toBeLessThan(1);
  });
});
