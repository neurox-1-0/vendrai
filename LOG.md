# NeuroX build log

This is the concise chronological log requested by the project owner. Detailed
acceptance evidence remains in [`CURRENT_STATUS.md`](./CURRENT_STATUS.md), and
unfinished gates remain in [`MASTER_TODO.md`](./MASTER_TODO.md).

## 2026-07-27 — product-first runtime and adaptive UI guidance

### Implemented

- Split the runtime into two Compose modes without forking product code:
  - `./scripts/stack.sh product-up` starts every functional supplier and
    invoice dependency, including Keycloak, malware scanning, the complete
    Docling/Tesseract/EasyOCR document worker, retrieval, Gemini workers,
    notifications and ERP sandbox.
  - `./scripts/stack.sh operations-up` adds OpenTelemetry, Tempo, Prometheus,
    Grafana and encrypted PostgreSQL WAL backup.
- Removed telemetry and backup from the default startup dependency path.
  Optional operational infrastructure can no longer prevent product
  functionality from starting.
- Preserved the existing Docker containers, images and volumes. No cleanup or
  deletion was performed.
- Replaced the copilot's hardcoded case-tour selector list with a semantic,
  self-registering assistance registry.
- Added dynamic, masked UI-target context to the copilot request contract.
  Gemini may choose only server-validated read-only spotlight actions for
  controls that the browser reports as currently visible.
- Added accessible user-controlled spotlight tours with title, explanation,
  Back, Next, Finish and Skip controls. The copilot never takes workflow action
  or hijacks the pointer.
- Improved the mobile copilot layout, made the send icon unambiguous, added a
  retry affordance and replaced raw `Failed to fetch` text with an actionable
  service-unavailable message.
- Regenerated OpenAPI and Orval artifacts.

### Verified

- Copilot API/security tests: `5 passed`.
- Full API/domain/contract suite: `77 passed, 2 skipped`.
- Ruff: passed.
- Frontend ESLint: passed.
- Frontend TypeScript: passed.
- Frontend production build: passed.
- Default product Compose and operations-overlay Compose both resolve.
- `scripts/stack.sh` shell syntax: passed.

### Current workstation constraint

- Host free space was rechecked at approximately 8.9 GB.
- No NeuroX OCR or retrieval image is cached. Building the complete local
  product would risk filling the system disk, so the heavy Docker build was
  not started.
- The full OCR stack remains required in the product profile. Nothing was
  removed or substituted.

## 2026-07-27 — live UI and environment audit

### Verified today

- The Gemini key exists in the uncommitted root `.env`; its value was never
  displayed.
- Real external Gemini participation is enabled only for synthetic demo data:
  `ALLOW_EXTERNAL_LLM=true`, `ALLOW_SYNTHETIC_LLM_DATA_ONLY=true`, and
  `LLM_DATA_CLASSIFICATION=SYNTHETIC`.
- Docker Desktop is running and can be inspected.
- The Next.js frontend started successfully at `http://localhost:3000`.
- Browser smoke checks passed for:
  - Dashboard navigation and work-queue controls.
  - Supplier onboarding intake.
  - Invoice exception intake.
  - Application copilot dialog and its safe read-only messaging.
- The frontend has no browser console warnings or errors.
- With the API stopped, the dashboard and copilot correctly expose connection
  failures instead of displaying fabricated business results.
- API/domain/contract suite: `76 passed, 2 skipped`.
- Frontend lint, TypeScript and production build: passed.
- Compose syntax resolves successfully with `.env.example`.

### Environment truth

- Repository size: approximately 2.1 GB.
- Existing Docker images: approximately 13.1 GB.
- Existing Docker volumes: approximately 4.0 GB.
- Free host space observed: approximately 7.1 GB.
- NeuroX Compose services are not currently running.
- Before automated setup, the root `.env` had the Gemini key but lacked the
  required internal service secrets. The bootstrap has now run successfully:
  all required Compose values are present, the Gemini key was preserved, and
  `.env` remains ignored with mode `600`.
- `scripts/bootstrap-local-env.sh` now generates those internal local secrets
  while preserving the existing Gemini key and never printing secret values.
- One old `vendortopay_db` container from the prototype Compose project is
  still running. It is not evidence that the current application stack is
  running and was not deleted because its data may belong to the owner.

### Why the full-stack disk recommendation is large

The 45–50 GB number is safe build headroom, not the steady-state size of the
application. The heavy components are the Docling/Tesseract/EasyOCR image,
CPU-only PyTorch and downloaded OCR/layout models, ClamAV definitions,
PostgreSQL, RabbitMQ, MinIO, Qdrant, Keycloak, OPA, observability images,
database/object volumes, and temporary Docker build layers.

- Frontend-only development needs well under 2 GB beyond dependencies.
- A lean born-digital workflow profile is expected to require materially less
  than the full acceptance stack.
- The complete OCR, security, observability and failure-testing profile still
  needs substantially more than the current 7.1 GB. The recommendation keeps
  Docker and the operating system away from a disk-full failure during builds.

### External credentials

- Required for real agent reasoning: `GEMINI_API_KEY`.
- No paid key is required for local PostgreSQL, Redis, RabbitMQ, MinIO, Qdrant,
  Keycloak, ClamAV, Tesseract, EasyOCR, OPA, Mailpit, Grafana, Prometheus or
  Tempo; they run as local containers.
- OFAC and UN sanctions sources are public and require no API key.
- An approved official EU sanctions export URL is still required.
- SMTP credentials are required only for real external email; Mailpit is used
  locally without credentials.
- A real ERP credential is not required for P0/P1 because the acceptance
  release intentionally uses the local mock ERP.

### Not complete

- Neither workflow has passed a fresh full-Compose browser journey.
- OCR/ClamAV/MinIO/Qdrant/RabbitMQ/Keycloak/OPA and worker integration remains
  unverified as one running stack on this workstation.
- Role-specific HITL journeys, worker restarts, broker retries/DLQs, SMTP
  outage, ERP timeout and security/chaos tests remain.
- The 100-case real-Gemini evaluation and numerical quality thresholds remain.
- Browser accessibility and responsive acceptance remains broader than the
  smoke check completed today.
- CI has not run this feature branch, and no PR to `dev` is open.

## 2026-07-27 — agent execution visibility

- Added failure-isolated parallel specialist execution.
- Added a PII-free tenant/run-scoped Redis live projection.
- PostgreSQL remains authoritative and replaces projected steps after commit.
- Added execution lanes, dependencies, attempts, measured latency, critical
  path, parallel time saved and sanitized diagnostics to the case UI.
- Added and tested the read-only application copilot, safe UI actions and
  versioned user feedback.
- Commit: `1390e90 feat(agent): stream live parallel progress safely`.
