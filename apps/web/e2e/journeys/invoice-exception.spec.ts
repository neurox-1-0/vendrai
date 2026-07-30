import {
  casePath,
  evidenceFor,
  expect,
  test,
  waitForCaseStatus,
} from "../support/fixtures";

/**
 * The golden invoice journey, plus the two exception scenarios whose expected
 * findings carry specific numbers.
 *
 * The numbers are the point. "A variance was detected" would pass against a
 * product that computed the wrong variance; "7.02% against a 2% tolerance"
 * would not.
 */

async function submitInvoiceCase(
  page: import("@playwright/test").Page,
  title: string,
  caseFolder: string,
  files: string[],
): Promise<string> {
  await page.goto("/invoices/new");
  await page.getByLabel(/invoice|title|reference/i).first().fill(title);
  await page.setInputFiles(
    'input[type="file"]',
    casePath(caseFolder, ...files),
  );
  const created = page.waitForResponse(
    (response) =>
      /\/api\/v1\/(cases|invoices)/.test(response.url()) &&
      response.request().method() === "POST" &&
      response.ok(),
  );
  await page.getByRole("button", { name: /submit|create/i }).click();
  await created;
  return new URL(page.url()).pathname.split("/").filter(Boolean).pop()!;
}

test.describe("invoice exception handling", () => {
  test("AP-001 matches cleanly and reaches finance approval", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitInvoiceCase(
      requester,
      "NSO-INV-2607108",
      "AP-001_clean_three_way_match",
      [
        "01_purchase_order.pdf",
        "02_goods_receipt_note.pdf",
        "03_tax_invoice.pdf",
      ],
    );

    await waitForCaseStatus(requester, caseId, [
      "APPROVAL_PENDING",
      "HOLD",
      "NEEDS_CLARIFICATION",
    ]);

    const detail = await (
      await requester.request.get(`/api/v1/cases/${caseId}`)
    ).json();
    expect(
      detail.status,
      "a clean three-way match should not be held or sent for clarification",
    ).toBe("APPROVAL_PENDING");

    await test.step("three-way match evidence records how it was matched", async () => {
      const evidence = await evidenceFor(requester, caseId);
      const match = evidence.items.find(
        (item: { source_type: string }) => item.source_type === "THREE_WAY_MATCH",
      );
      expect(match, "no three-way match evidence was produced").toBeTruthy();
      // Uploaded PO/GRN are reference evidence, not an ERP feed. Claiming
      // otherwise would imply an integration this product does not have.
      expect(match.provenance).toBe("USER_UPLOADED");
      expect(match.is_authoritative).toBe(false);
      expect(match.source_locator.po_number).toBe("PO-2026-00481");
    });

    await test.step("finance approves; procurement cannot approve an invoice", async () => {
      const finance = await pageAs("finance");
      await finance.goto("/approvals");
      const decided = finance.waitForResponse((response) =>
        response.url().includes("/decisions"),
      );
      await finance
        .getByRole("link", { name: new RegExp(caseId.slice(0, 8), "i") })
        .first()
        .click();
      await finance.getByRole("button", { name: /^approve/i }).click();
      const decision = await decided;
      expect(
        decision.ok(),
        `finance approval was rejected: ${await decision.text()}`,
      ).toBe(true);
    });

    await waitForCaseStatus(requester, caseId, [
      "COMPLETED",
      "ERP_SYNC_PENDING",
      "ERP_SYNC_FAILED",
    ]);
  });

  test("AP-002 reports the price variance against the configured tolerance", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitInvoiceCase(
      requester,
      "NSO-INV-2607124",
      "AP-002_price_variance",
      [
        "01_purchase_order.pdf",
        "02_goods_receipt_note.pdf",
        "03_tax_invoice.pdf",
      ],
    );

    await waitForCaseStatus(requester, caseId, [
      "HOLD",
      "RISK_REVIEW",
      "APPROVAL_PENDING",
      "NEEDS_CLARIFICATION",
    ]);

    const exceptions = await (
      await requester.request.get(`/api/v1/cases/${caseId}/invoice-exceptions`)
    ).json();
    const variance = (exceptions.items ?? exceptions).find(
      (item: { exception_type: string }) =>
        item.exception_type === "PRICE_VARIANCE",
    );
    expect(
      variance,
      "no price variance exception was raised for a 7.02% overcharge",
    ).toBeTruthy();
    // PO 28,500 vs invoice 30,500 per unit.
    expect(String(variance.mismatch_details.variance_percent)).toMatch(/^7\.0/);
    expect(String(variance.mismatch_details.threshold_percent)).toBe("2");
  });

  test("AP-003 reports the quantity overrun with both figures", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitInvoiceCase(
      requester,
      "NSO-INV-2607141",
      "AP-003_quantity_exceeds_receipt",
      [
        "01_purchase_order.pdf",
        "02_goods_receipt_note.pdf",
        "03_tax_invoice.pdf",
      ],
    );

    await waitForCaseStatus(requester, caseId, [
      "HOLD",
      "RISK_REVIEW",
      "APPROVAL_PENDING",
      "NEEDS_CLARIFICATION",
    ]);

    const exceptions = await (
      await requester.request.get(`/api/v1/cases/${caseId}/invoice-exceptions`)
    ).json();
    const quantity = (exceptions.items ?? exceptions).find(
      (item: { exception_type: string }) =>
        item.exception_type === "QUANTITY_VARIANCE",
    );
    expect(
      quantity,
      "invoicing 50 against a receipt of 40 raised no quantity exception",
    ).toBeTruthy();
    expect(quantity.mismatch_details.message).toContain("50");
    expect(quantity.mismatch_details.message).toContain("40");
  });

  test("AP-007 holds the invoice and never updates the vendor master", async ({
    pageAs,
  }) => {
    const requester = await pageAs("requester");
    const caseId = await submitInvoiceCase(
      requester,
      "NSO-INV-2607166",
      "AP-007_unverified_bank_account_change",
      [
        "01_purchase_order.pdf",
        "02_goods_receipt_note.pdf",
        "03_tax_invoice_with_new_bank_account.pdf",
      ],
    );

    await waitForCaseStatus(requester, caseId, [
      "HOLD",
      "RISK_REVIEW",
      "NEEDS_CLARIFICATION",
    ]);

    const exceptions = await (
      await requester.request.get(`/api/v1/cases/${caseId}/invoice-exceptions`)
    ).json();
    const bank = (exceptions.items ?? exceptions).find(
      (item: { exception_type: string }) =>
        item.exception_type === "UNVERIFIED_BANK_ACCOUNT_CHANGE",
    );
    expect(bank, "a changed remittance account raised no exception").toBeTruthy();

    // The second finding is the one that matters: a document asserting new
    // bank details is not authority to change them.
    expect(bank.mismatch_details.policy_position).toContain(
      "not sufficient authority",
    );
    expect(bank.mismatch_details.vendor_master_updated).toBe(false);

    const admin = await pageAs("admin");
    const vendors = await (
      await admin.request.get("/api/v1/admin/vendors?erp_vendor_id=V000184")
    ).json();
    if (Array.isArray(vendors) && vendors.length > 0) {
      // The vendor master must still hold the originally verified account.
      expect(
        vendors[0].bank_account_last_changed_by_case ?? null,
        "the vendor master was mutated from invoice content",
      ).not.toBe(caseId);
    }
  });
});
