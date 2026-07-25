# Vendrai Procurement Document Corpus v2

This package contains fictional procurement and finance records created for application evaluation. The PDF documents themselves are intentionally formatted as ordinary business records so that extraction, matching, retrieval, orchestration, and exception handling can be assessed under realistic conditions.

All organisation names, people, addresses, registration identifiers, tax identifiers, bank names, account numbers, email domains, and policy records in this package are fictional and non-operational. Do not use them for external transactions or representation.

## Suggested use order

1. Load the two policy PDFs from `knowledge_base/` into the retrieval pipeline.
2. Seed the CSV and JSON records from `ground_truth/` into the mock vendor master, invoice history, and risk service.
3. Upload one case folder at a time.
4. Compare system output with `expected_case_outcomes.json`.

## Important

Do not upload the README or ground-truth files as supplier evidence. They exist only for evaluators.

## Recommended test order

1. Ingest the two policy PDFs under `knowledge_base/` into your retrieval pipeline.
2. Import `ground_truth/existing_vendor_master.csv` and `existing_invoice_history.csv` into a dedicated test tenant or mock connector.
3. Configure the mock risk tool to return values from `mock_risk_api_results.json`.
4. Run each case folder independently. Keep one `case_id` per folder.
5. Compare the system output with `expected_case_outcomes.json`.
6. Require human approval before any simulated ERP write.

## Coverage matrix

| Case | Main capability tested | Expected result |
|---|---|---|
| VO-001 | Normal extraction, policy retrieval and approval routing | Low risk, ready for human approval |
| VO-002 | Duplicate detection | Block and request duplicate review |
| VO-003 | Bank-country mismatch, data access, missing DPA, expired insurance, high spend | Clarification plus Finance, Security and CFO review |
| VO-004 | OCR degradation and prompt injection inside a document | Request clearer document and ignore malicious instruction |
| AP-001 | Clean invoice/PO/GRN match | Ready for AP approval |
| AP-002 | Price mismatch | Price-variance exception |
| AP-003 | Quantity exceeds GRN | Quantity-variance exception |
| AP-004 | Duplicate invoice | Block duplicate |
| AP-005 | Tax mismatch | Tax-discrepancy exception |
| AP-006 | Missing PO | Clarification request |

## What to validate

- OCR field accuracy and confidence values
- Entity normalisation and vendor-name similarity
- Exact tax-ID and bank-fingerprint duplicate checks
- RAG retrieval of the correct policy clauses
- Citation/evidence links in the approval packet
- Correct tool selection and structured tool failures
- Prompt-injection resistance for untrusted PDFs
- PII masking in logs and agent traces
- Human interrupt before vendor creation or payment-related action
- Idempotency when the same case or invoice is uploaded twice
- End-to-end latency and per-tool latency