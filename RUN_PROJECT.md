# Run and test NeuroX on another machine

This guide is for a trusted tester running NeuroX on macOS, Linux, or Windows.
It uses the checked-in synthetic document corpus. Do not use real supplier,
bank, tax, employee, or invoice data in a development environment.

## 1. Know what this revision supports

| Preference | Supported now | Configuration |
|---|---:|---|
| Local document processing with no external AI | Yes | Local native PDF, Docling, Tesseract, EasyOCR, and local retrieval; `ALLOW_EXTERNAL_LLM=false` |
| Local document processing plus Gemini reasoning | Yes | Same local OCR; set `ALLOW_EXTERNAL_LLM=true` and provide a Gemini key |
| Cloud OCR with local fallback | No | A cloud OCR provider adapter and tenant policy have not been implemented |
| Cloud-only OCR | No | A lightweight cloud document-worker profile has not been implemented |

Gemini is not the OCR engine in the current build. Source documents and raw
OCR stay local. When Gemini is enabled, the application sends only the
allowlisted, locally masked synthetic context.

Do not add undocumented OCR environment variables or send real documents to a
cloud service. Until the cloud OCR adapter is implemented and tested, the
supported document path is the local `document-worker`.

## 2. Share the correct source revision

A normal clone contains only committed and pushed files. On the owner's
machine, check the revision before asking another person to test:

```bash
git status --short
git branch --show-current
git log -1 --oneline
```

If `git status --short` prints files, those changes are not available to a
friend who clones the remote repository. Review them, commit them, and push the
intended branch before sharing its name.

Alternatively, after committing the intended revision, create a clean archive:

```bash
git archive --format=zip --output=NeuroX-test.zip HEAD
```

`git archive` does not include `.env`, virtual environments, Docker volumes, or
untracked secrets. Send secrets separately through an approved secret-sharing
channel. Never send `.env` through source control, email, or chat.

The tester should record these values with the test result:

```bash
git rev-parse HEAD
git status --short
docker version
docker compose version
```

## 3. Machine requirements

Required for the complete product stack:

- Git
- Docker Desktop on macOS or Windows, or Docker Engine with the Compose v2
  plugin on Linux
- Docker Compose v2, invoked as `docker compose`
- At least 8 CPU cores and 16 GB memory assigned to Docker for the full local
  model stack
- Enough Docker storage for the images, model cache, malware definitions, and
  test volumes on that particular machine
- Internet access during the first image build and model download

Required only for running code-quality tests directly on the host:

- Python 3.12
- Node.js 22.22 or another compatible Node 22 release
- npm

Check the tools:

```bash
git --version
docker version
docker compose version
```

The first build can take a long time. ClamAV, EasyOCR, and retrieval models are
downloaded into Docker images or volumes. Apple Silicon machines run the pinned
ClamAV `linux/amd64` image through emulation, so its first start may be slower.

## 4. Operating-system setup

### macOS

Install and start Docker Desktop. If Homebrew is available:

```bash
brew install --cask docker
brew install git python@3.12 node@22
```

Open Docker Desktop once and wait until the engine reports that it is running.
Run the remaining commands from Terminal in the repository root.

### Linux

Install Git, OpenSSL, Docker Engine, and the Docker Compose v2 plugin using the
instructions for the Linux distribution. Add the tester to the Docker group
only if that is consistent with the machine's security policy.

Verify that Docker works without changing NeuroX:

```bash
docker run --rm hello-world
docker compose version
```

Run the remaining commands from a Bash shell in the repository root.

### Windows 11 or Windows 10

The supported Windows route is WSL2 with Ubuntu. The project bootstrap and
stack scripts are Bash scripts; native PowerShell is not currently a supported
execution environment.

From an Administrator PowerShell window:

```powershell
wsl --install -d Ubuntu-24.04
winget install --exact --id Docker.DockerDesktop
```

Restart Windows if requested. In Docker Desktop, enable:

1. **Use the WSL 2 based engine**
2. **Resources → WSL Integration → Ubuntu-24.04**

Open the Ubuntu terminal and install basic tools:

```bash
sudo apt update
sudo apt install -y git openssl ca-certificates curl
```

Clone the repository inside the WSL filesystem, for example under
`~/projects/NeuroX`, rather than under `/mnt/c`. Linux filesystem paths provide
better Docker bind-mount performance and avoid common permission problems.

All commands below are then run inside the Ubuntu terminal. If scripts lost
their executable bit in a manually copied archive, repair it:

```bash
chmod +x scripts/*.sh infra/keycloak/*.sh infra/postgres/*.sh
```

## 5. Obtain the source

Clone the exact branch shared by the owner:

```bash
git clone --branch BRANCH_NAME --single-branch REPOSITORY_URL NeuroX
cd NeuroX
git rev-parse HEAD
git status --short
```

Replace `BRANCH_NAME` and `REPOSITORY_URL` with the real values. The final
`git status` should be empty.

For an archive, extract it, open a Bash shell in the extracted `NeuroX`
directory, and continue below.

## 6. Create the local environment

From the repository root:

```bash
./scripts/bootstrap-local-env.sh
```

The bootstrap:

- creates the ignored `.env`;
- generates independent local service secrets;
- preserves existing non-empty values;
- never prints secret values.

Validate that Docker Compose can resolve the configuration:

```bash
docker compose config --quiet
```

If this command fails, do not start the stack. Correct the named missing value
in `.env` first.

### Preference A: fully local, no external AI

This is the safest first run. In `.env`, keep:

```dotenv
APP_ENV=development
AUTH_MODE=development
ALLOW_EXTERNAL_LLM=false
ALLOW_SYNTHETIC_LLM_DATA_ONLY=true
LLM_DATA_CLASSIFICATION=SYNTHETIC
GEMINI_API_KEY=
```

OCR, fuzzy matching, rules, anomaly shadow logic, storage, retrieval, workflow,
alerts, mock ERP, and notifications still run locally. Optional LLM reasoning
uses the application's explicit local fallback.

### Preference B: local OCR plus Gemini

Use synthetic documents only. In `.env`, set:

```dotenv
APP_ENV=development
AUTH_MODE=development
ALLOW_EXTERNAL_LLM=true
ALLOW_SYNTHETIC_LLM_DATA_ONLY=true
LLM_DATA_CLASSIFICATION=SYNTHETIC
GEMINI_API_KEY=REPLACE_WITH_A_SERVER_SIDE_KEY
```

Do not commit `.env`. A Gemini key is not required to build or run Preference
A.

To test Keycloak roles later, change only:

```dotenv
AUTH_MODE=keycloak
```

Rebuild the web and API containers after changing `AUTH_MODE`:

```bash
docker compose --profile acceptance up --build --detach web api
```

The synthetic Keycloak usernames are:

- `requester`
- `analyst`
- `procurement`
- `compliance`
- `finance`
- `auditor`
- `admin`

They share the generated `KEYCLOAK_E2E_USER_PASSWORD` stored in the local
`.env`. Do not print or share that password in test evidence.

## 7. Build and start the product

From the repository root:

```bash
./scripts/stack.sh product-up
```

This starts the functional product stack, including PostgreSQL, migrations,
seed data, RabbitMQ, Redis, MinIO, ClamAV, Keycloak, OPA, Qdrant, local OCR,
local retrieval, workers, Mailpit, mock ERP, API, and web application.

Watch the status:

```bash
./scripts/stack.sh status
docker compose ps --all
```

The one-shot `migrate`, `seed`, `minio-init`, and `keycloak-bootstrap` services
should finish with exit code `0`. Long-running services should be `Up`; health
checked services should become `healthy`.

If a service fails:

```bash
docker compose logs --tail=200 SERVICE_NAME
```

For the main workflow services:

```bash
docker compose logs --tail=200 api document-worker agent-worker invoice-worker outbox-relay
```

To follow logs continuously:

```bash
docker compose logs --follow api document-worker agent-worker invoice-worker
```

Press `Ctrl+C` to stop following logs; this does not stop the containers.

## 8. Verify health and open the application

From a Bash terminal:

```bash
curl --fail --silent --show-error http://localhost:8000/health/live
curl --fail --silent --show-error http://localhost:8000/health/ready
```

Open:

- Web application: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- Keycloak: <http://localhost:8080>
- Mailpit: <http://localhost:8025>
- MinIO console: <http://localhost:9001>

The API readiness endpoint may briefly report `degraded` while dependencies are
starting. If it remains degraded, inspect:

```bash
docker compose ps --all
docker compose logs --tail=200 api
```

An admin user can also inspect the application integration view at:

<http://localhost:3000/admin>

## 9. Manual end-to-end smoke test

Use only files under:

```text
Vendrai_Procurement_Document_Corpus_v2/cases/
```

### Clean supplier onboarding

1. Open <http://localhost:3000/cases/new>.
2. Use title `VO-001 local smoke`.
3. Upload every PDF from
   `Vendrai_Procurement_Document_Corpus_v2/cases/VO-001_standard_vendor_onboarding/`.
4. Submit the case.
5. Confirm quarantine, malware scan, document extraction, agent steps, evidence,
   and any human tasks are visible.
6. Confirm the same case appears in the work queue.

The clean supplier case can intentionally stop in a visible verification state
if current OFAC, UN, and EU datasets or published tenant policies have not been
loaded. That is fail-closed behaviour, not a successful full onboarding. Do
not bypass it to make the smoke test green.

### Clean invoice match

1. Open <http://localhost:3000/invoices/new>.
2. Use invoice number `AP-001-SMOKE` and PO number `PO-AP-001`.
3. Upload all three PDFs from
   `Vendrai_Procurement_Document_Corpus_v2/cases/AP-001_clean_three_way_match/`.
4. Submit the invoice.
5. Confirm invoice, PO, and GRN extraction; matching; evidence; agent steps; and
   the resulting automatic, review, or fail-closed verification path.

A complete ERP-confirmed journey requires the policy, sanctions, role, approval,
and OPA prerequisites listed in `MASTER_TODO.md`. This smoke test proves that
the submitted evidence travels through the running stack and that missing
control data remains visible.

### Exception and fraud cases

Repeat the invoice flow with:

- `AP-002_price_variance`
- `AP-003_quantity_exceeds_receipt`
- `AP-004_duplicate_invoice_submission`
- `AP-005_tax_rate_mismatch`
- `AP-006_missing_purchase_order_reference`
- `AP-007_unverified_bank_account_change`

Repeat supplier onboarding with:

- `VO-002_potential_duplicate_vendor`
- `VO-004_low_quality_document_and_untrusted_instruction`
- `VO-005_bank_beneficiary_mismatch`

Expected safety behaviour:

- duplicate, bank-change, sanctions, and critical low-confidence findings
  require human review;
- shadow anomaly findings do not approve, reject, pay, or change vendors;
- source documents and raw bank/tax values do not reach Gemini;
- an SMTP failure does not change workflow state;
- an OPA failure blocks ERP authorization.

### Dashboards and notifications

After submitting cases, check:

- Work queue: <http://localhost:3000>
- Analytics: <http://localhost:3000/analytics>
- Approvals: <http://localhost:3000/approvals>
- Reports: <http://localhost:3000/reports>
- Mailpit: <http://localhost:8025>

Verify that chart drill-downs show authorized cases and that requester-only
users cannot access tenant aggregate analytics.

## 10. Automated code tests

These tests do not replace the full browser and failure-injection acceptance
work.

### Backend tests on macOS, Linux, or WSL2

From the repository root:

```bash
cd services/api
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
ruff check .
mypy --ignore-missing-imports app/domain
pytest -q
python -m compileall -q app tests
cd ../..
```

If the executable is named `python3` rather than `python3.12`, first verify
that `python3 --version` reports Python 3.12, then substitute `python3`.

The two live PostgreSQL integration tests are expected to skip unless their
`NEUROX_LIVE_*` database URLs are explicitly supplied.

### Frontend tests on macOS, Linux, or WSL2

From the repository root:

```bash
cd apps/web
npm ci
npm run api:generate
git diff --exit-code -- src/generated
npm run lint
npx tsc --noEmit
npm run build
npm audit --omit=dev --audit-level=high
cd ../..
```

### Contract and evaluation-manifest checks

From the repository root with the backend virtual environment already created:

```bash
docker compose config --quiet
docker run --rm -v "$PWD/policies:/policies:ro" openpolicyagent/opa:1.5.1-static check /policies
cd services/api
source .venv/bin/activate
python -m scripts.export_openapi
git diff --exit-code -- ../../packages/contracts/openapi.json
pytest -q tests/test_evaluation_manifest.py
python scripts/generate_evaluation_cases.py
git diff --exit-code -- ../../evaluation/cases.jsonl ../../evaluation/manifest.sha256
cd ../..
```

The repository currently contains a deterministic 100-case manifest. It does
not yet contain a single command that executes all 100 cases through live
services; that execution runner and its measured result remain release work.

### Optional live Gemini smoke

Use synthetic data only. After configuring Preference B:

```bash
docker compose exec api python scripts/smoke_gemini.py
```

The script prints status, model metadata, latency, and a count. It does not
print the Gemini key or raw sensitive content.

## 11. Stop, restart, and inspect

Stop without deleting test data:

```bash
./scripts/stack.sh product-down
```

Restart later:

```bash
./scripts/stack.sh product-up
```

Inspect Docker storage without deleting anything:

```bash
docker system df
docker compose ps --all
```

### Destructive clean reset

The following command permanently deletes the local NeuroX PostgreSQL data,
documents, queues, model data, and other Docker volumes for this Compose
project. Use it only when the tester intentionally wants a completely fresh
synthetic environment:

```bash
docker compose down --volumes --remove-orphans
```

After a destructive reset:

```bash
./scripts/stack.sh product-up
```

Do not run broad cleanup commands such as `docker system prune --all --volumes`
on a machine that contains unrelated Docker projects.

## 12. Troubleshooting

### Docker is not reachable

Start Docker Desktop or the Linux Docker daemon, then run:

```bash
docker version
```

Both a client and server section must appear.

### A port is already in use

Check the port owner before stopping anything:

```bash
docker compose ps
```

NeuroX binds localhost ports `3000`, `8000`, `8080`, `8025`, `9000`, and
`9001`. Stop or reconfigure the conflicting application deliberately.

### ClamAV remains unhealthy

The first malware-definition initialization can be slow:

```bash
docker compose logs --tail=200 clamav
```

Do not disable `CLAMAV_REQUIRED` to make an acceptance test pass.

### OCR or retrieval build fails

Inspect the failed build and available Docker storage:

```bash
docker system df
docker compose build document-worker retrieval-api
```

Do not delete unrelated Docker data automatically. Capture the final build
error and the output of `docker system df`.

### Windows files have `^M` or scripts fail

Clone inside WSL and verify Git's line-ending setting:

```bash
git config --get core.autocrlf
file scripts/stack.sh
```

Do not edit shell scripts with forced Windows CRLF endings.

## 13. Test-result template

Copy this into the test report:

```text
Commit:
Branch:
Operating system:
CPU/RAM:
Docker version:
Docker Compose version:
Preference: local-only | local-OCR-plus-Gemini
AUTH_MODE: development | keycloak

Compose config: PASS/FAIL
Product stack health: PASS/FAIL
API live/ready: PASS/FAIL
Backend tests: PASS/FAIL, count:
Frontend lint/type/build: PASS/FAIL
OPA check: PASS/FAIL
Supplier VO-001: PASS/FAIL
Invoice AP-001: PASS/FAIL
Exception/fraud cases tested:
Analytics/alerts: PASS/FAIL
Keycloak roles: PASS/FAIL/NOT RUN
Gemini smoke: PASS/FAIL/NOT RUN

Failed service:
Sanitized error:
Steps to reproduce:
No secrets or real business data attached: YES/NO
```

Passing the smoke steps on another machine is valuable evidence, but it does
not by itself mark NeuroX production-ready. The remaining security, chaos,
load, backup/restore, complete browser, and 100-case numerical gates remain in
`MASTER_TODO.md`.
