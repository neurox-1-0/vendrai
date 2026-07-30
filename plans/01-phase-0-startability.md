# Phase 0 — Make it start, every time

**Depends on:** nothing · **Blocks:** every other phase
**Defects addressed:** D-007, D-008, D-009, D-010

---

## Why this phase exists

Starting NeuroX currently takes hours and fails in platform-specific ways that
give no useful diagnostic. On 2026-07-28 a single startup attempt surfaced four
distinct defects (D-004 to D-007), none of which were visible to a passing
82-test suite or to clean lint and type checks.

That ratio is the whole argument. Every hour of startup friction is an hour not
spent on the twenty open defects, and every silent startup failure mode is a
defect that reaches a user instead of a developer.

The goal is not elegance. The goal is: **one command, works or tells you exactly
why not, within seconds.**

---

## Design principles

1. **Fail fast and loudly at the boundary.** A missing precondition must be
   caught by a preflight check, not surface 20 minutes later as a container
   crash loop.
2. **Every error message names the fix.** "Port 8025 in use by container
   `swiftdrop-mailhog-1`" beats "bind failed."
3. **Liveness is not readiness, and readiness is not business-readiness.** All
   three are distinct and all three get checked.
4. **Make invalid states unrepresentable in the repo.** CRLF corruption should
   be impossible via `.gitattributes`, not documented as a troubleshooting step.

---

## Work items

### 0.1 — Prevent the CRLF class of defect permanently (D-007)

**Problem.** `git core.autocrlf=true` on Windows rewrites committed LF shell
scripts to CRLF on checkout. Inside a Linux container this breaks the very first
line: `set: pipefail: invalid option name`. It hit `scripts/stack.sh`,
`scripts/bootstrap-local-env.sh`, `infra/keycloak/bootstrap-acceptance.sh`, and
`infra/postgres/001-roles.sh`. `keycloak-bootstrap` exited 2 as a direct result.

This is already documented in `RUN_PROJECT.md` §12 as a troubleshooting step —
which is the tell. A recurring, documented, manually-repaired defect is an
unfixed defect.

**Fix.** Add a root `.gitattributes`:

```gitattributes
* text=auto eol=lf
*.sh    text eol=lf
*.rego  text eol=lf
*.sql   text eol=lf
Dockerfile* text eol=lf
*.ps1   text eol=crlf
*.bat   text eol=crlf
*.png binary
*.pdf binary
```

Then renormalize once: `git add --renormalize .`

**Verify.** On a fresh clone with `core.autocrlf=true`, `file scripts/stack.sh`
reports no CRLF, and `docker compose --profile acceptance up` completes
`keycloak-bootstrap` with exit 0.

---

### 0.2 — Repository hygiene (D-009)

`erl_crash.dump` (1.5 MB) was committed in `f55cc3a`. Remove it and prevent
recurrence.

```bash
git rm --cached erl_crash.dump
```

Add to `.gitignore`:

```gitignore
*.dump
erl_crash.dump
native/
```

Also audit for `.DS_Store` files (flagged in `AUDIT.md` §10.6) and remove them in
the same change.

---

### 0.3 — Fix the Redis version fragility properly (D-008)

**Problem.** [`rate_limit.py:29-38`](../services/api/app/services/rate_limit.py#L29-L38)
wraps the whole pipeline in `except Exception` and returns
`503 RATE_LIMIT_SERVICE_UNAVAILABLE`. The pipeline uses `EXPIRE … NX`, which
requires Redis 7.0+. Against Redis 3.0.504 this raises `ResponseError`, and the
API reports "service unavailable" — a wrong diagnosis that sent debugging in the
direction of Redis connectivity when Redis was answering `PONG` perfectly.

**Why this matters beyond the immediate bug.** A catch-all that collapses
"unsupported command" and "server unreachable" into one error code will mislead
whoever debugs it next, too.

**Fix — three parts:**

1. **Assert the version at startup.** In the API lifespan, issue `INFO server`,
   parse `redis_version`, and refuse to start with a clear message if
   `< 7.0`:
   ```
   REDIS_VERSION_UNSUPPORTED: found 3.0.504, requires >= 7.0
   (EXPIRE ... NX is used by the rate limiter). Update Redis or
   set RATE_LIMIT_ENABLED=false for local development.
   ```
2. **Separate the error paths** in `enforce_rate_limit`: distinguish
   `ConnectionError`/`TimeoutError` (genuine outage → 503) from `ResponseError`
   (unsupported command / bad request → log loudly, fail *open* with a warning
   rather than blocking every request on a config problem).
3. **Pin the floor** in `docker-compose.yml` (already `redis:7.4.2-alpine`) and
   document the minimum in the native runbook.

**Verify.** Point `REDIS_URL` at a Redis 6 instance; the API refuses to start
with the message above rather than starting and 503-ing every request.

---

### 0.4 — Real preflight checks in the startup script

**Problem.** `scripts/stack.sh` has exactly one guard — a disk-space warning in
`warn_low_disk`. Every other failure mode surfaces as an opaque Docker error
minutes in. The 2026-07-28 session hit three of them: a port taken by an
unrelated project's container, a stale Docker port-proxy binding, and a Postgres
password mismatch against an existing volume.

**Fix.** Add a `preflight` step that runs before `docker compose up` and checks:

| Check | Failure message must include |
|---|---|
| Docker daemon reachable | "Start Docker Desktop" |
| Compose v2 present | detected version |
| Disk headroom (≥ 25 GB for a clean build) | actual free space |
| Memory assigned to Docker (≥ 8 GB) | actual, and where to change it |
| Ports 3000/8000/8080/8025/9000/9001 free | **which process or container** holds each |
| `.env` exists and every `${VAR:?}` in compose resolves | the specific missing key |
| Postgres volume/password consistency | how to reset, and that it is destructive |

The port check is the highest-value one — it caught a real conflict with an
unrelated `swiftdrop-mailhog-1` container. Report the holder, not just the
conflict:

```bash
docker ps --filter "publish=8025" --format '{{.Names}}'
```

**Verify.** Deliberately occupy port 8000, run `./scripts/stack.sh product-up`,
and get a named-holder error within ~5 seconds instead of a Compose failure
minutes later.

---

### 0.5 — Distinguish liveness, readiness, and business-readiness

**Problem.** `stack.sh status` shells out to `docker compose ps`. Containers can
be `Up (healthy)` while the product cannot serve a single business scenario —
which is exactly the state the audit describes in §7.

**Fix.** Add `./scripts/stack.sh doctor` reporting three tiers:

1. **Liveness** — every container running; one-shot jobs (`migrate`, `seed`,
   `minio-init`, `keycloak-bootstrap`) exited 0.
2. **Readiness** — `/health/live` and `/health/ready` green; RabbitMQ queues
   declared; MinIO buckets exist; Qdrant reachable; Keycloak realm resolves;
   OPA answers a trivial query.
3. **Business-readiness** — vendor master loaded, invoice history loaded, both
   policies published *and indexed*, sanctions datasets present and not stale.

Tier 3 will fail until Phase 1 lands. **That is the point** — it makes the
audit's central finding visible and measurable instead of a surprise at demo
time.

Output one line per check with `PASS`/`FAIL` and, on failure, the command that
fixes it.

---

### 0.6 — Reduce first-build cost

The document-worker and retrieval images download OCR and embedding models at
build time. The 2026-07-28 build took ~35 minutes and one attempt failed on a
transient pip hash mismatch mid-download.

- Add BuildKit cache mounts for pip so a rebuild does not re-download PyTorch.
- Split model download into its own layer so an application code change does not
  invalidate it.
- Add `--retries` to the model-download step for transient network faults.
- Measure and document actual image sizes after a clean build (the audit asks
  for this; the 45–50 GB figure in `README.md` is an estimate, not a
  measurement).

---

## Acceptance criteria

Phase 0 is complete when all of the following are demonstrated on a machine that
has never run the project:

- [ ] A fresh clone with `core.autocrlf=true` produces no CRLF-corrupted scripts.
- [ ] `./scripts/bootstrap-local-env.sh && ./scripts/stack.sh product-up`
      reaches a fully healthy stack with no manual intervention.
- [ ] Every one-shot job exits 0 on the first attempt.
- [ ] `./scripts/stack.sh doctor` reports tier 1 and 2 green (tier 3 fails
      until Phase 1 — expected and clearly labelled).
- [ ] Each of these produces a clear, actionable message in under 10 seconds:
      Docker stopped · port occupied · missing `.env` key · insufficient disk.
- [ ] `erl_crash.dump` is gone from the index; `*.dump` is ignored.
- [ ] Pointing at a Redis < 7.0 refuses startup with a specific message.
- [ ] A second `product-up` after `product-down` succeeds without cleanup.

---

## Explicitly out of scope

- Making RabbitMQ work on native Windows (D-010). See
  [ADR-001](./91-decisions.md#adr-001--docker-is-the-supported-local-runtime-native-windows-is-best-effort).
  Native stays documented as best-effort.
- CI changes — Phase 5.
- Kubernetes, or any new runtime. `AUDIT.md` §13 deferral list is binding.

---

## Estimated effort

2–3 days. Item 0.4 (preflight) carries the most value per hour; do it first.
