"""``python -m scripts.bootstrap`` - make a healthy stack business-ready.

Idempotent by construction: every step either creates what is missing or
repairs what has drifted, and a second run changes nothing.

``--check`` runs the same readiness assessment without writing anything, and
is what ``scripts/doctor.sh`` tier 3 calls. Sharing one implementation is
deliberate: a separate copy of "what business-ready means" would drift from
this one, and the drift would be invisible until a demo.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from app.config import settings
from app.database import AsyncSessionLocal, set_tenant_context

from scripts.bootstrap import identities, policies, reference_data, sanctions
from scripts.bootstrap.api_client import AdminApiClient, BootstrapAuthError
from scripts.bootstrap.report import BootstrapReport


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.bootstrap",
        description="Load reference data, policies, and sanctions. Idempotent.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report business-readiness without changing anything.",
    )
    parser.add_argument(
        "--allow-missing-eu-sanctions",
        action="store_true",
        help=(
            "Treat an unconfigured EU sanctions source as acceptable. "
            "Supplier scenarios will still block at screening; use this only "
            "for invoice-only testing."
        ),
    )
    parser.add_argument(
        "--skip-sanctions",
        action="store_true",
        help="Do not request sanctions imports (they download from the internet).",
    )
    parser.add_argument(
        "--tenant-id",
        default=settings.DEV_TENANT_ID,
        help="Tenant to bootstrap. Defaults to DEV_TENANT_ID.",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=settings.CORPUS_ROOT,
        help="Directory holding ground_truth/ and knowledge_base/.",
    )
    return parser.parse_args(argv)


async def run_check(tenant_id: uuid.UUID) -> BootstrapReport:
    """Assess readiness. Reads only - safe to run against a live stack."""
    report = BootstrapReport()
    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, str(tenant_id))

        separated = await identities.role_separation_holds(session, tenant_id)
        report.add(
            "Users",
            "OK" if separated else "FAILED",
            f"{len(identities.IDENTITIES)} (1 role each)"
            if separated
            else "missing, or an identity holds more than one role",
        )

        vendors, history = await reference_data.counts(session, tenant_id)
        report.add(
            "Vendor master",
            "OK" if vendors else "FAILED",
            f"{vendors} vendors" if vendors else "empty",
        )
        report.add(
            "Invoice history",
            "OK" if history else "FAILED",
            f"{history} records" if history else "empty",
        )

        active, missing, stale = await sanctions.dataset_state(session, tenant_id)
        detail = " · ".join(active) if active else "none"
        if missing:
            detail += f" · missing: {', '.join(missing)}"
        if stale:
            detail += f" · stale: {', '.join(stale)}"
        report.add(
            "Sanctions",
            "OK" if not missing and not stale else "MISSING",
            detail,
        )

    await _check_policies(tenant_id, report)
    return report


async def _check_policies(tenant_id: uuid.UUID, report: BootstrapReport) -> None:
    for spec in policies.POLICIES:
        # Retrieval is the only check that matters here. A policy row in
        # Postgres that retrieval cannot find is invisible to every scenario.
        indexed = await policies.probe_retrieval(tenant_id, spec, timeout_seconds=0)
        report.add(
            f"Policy {spec.policy_code}",
            "OK" if indexed else "FAILED",
            "PUBLISHED, retrievable" if indexed else "not retrievable",
        )


async def run_bootstrap(args: argparse.Namespace) -> BootstrapReport:
    tenant_id = uuid.UUID(args.tenant_id)
    corpus_root = Path(args.corpus_root)
    report = BootstrapReport()

    # --- Tenant, identities, and reference data (direct writes) -------------
    async with AsyncSessionLocal() as session, session.begin():
        await set_tenant_context(session, str(tenant_id))
        tenant = await identities.ensure_tenant(session, tenant_id)
        user_count = await identities.ensure_users(session, tenant_id)
        report.add("Tenant", "OK", f"{tenant.slug} ({tenant_id})")
        report.add("Users", "OK", f"{user_count} (1 role each)")

        vendors = await reference_data.load_vendor_master(session, tenant_id, corpus_root)
        await reference_data.verify_blind_indexes(session, tenant_id, corpus_root)
        report.add(
            "Vendor master",
            "OK",
            f"{vendors.total} vendors ({vendors.created} new)",
        )

        history = await reference_data.load_invoice_history(session, tenant_id, corpus_root)
        report.add(
            "Invoice history",
            "OK",
            f"{history.total} records ({history.created} new)",
        )

    # --- Policies and sanctions (through the public API) --------------------
    async with AdminApiClient(tenant_id) as api:
        await api.wait_until_available()
        await _publish_policies(api, tenant_id, corpus_root, report)
        if args.skip_sanctions:
            report.add("Sanctions", "SKIPPED", "--skip-sanctions", blocking=False)
        else:
            await _import_sanctions(api, report, args)

    return report


async def _publish_policies(
    api: AdminApiClient,
    tenant_id: uuid.UUID,
    corpus_root: Path,
    report: BootstrapReport,
) -> None:
    for spec in policies.POLICIES:
        try:
            published = await policies.publish_policy(api, spec, corpus_root)
        except policies.PolicyPublicationError as error:
            report.add(f"Policy {spec.policy_code}", "FAILED", str(error))
            continue

        indexed = await policies.probe_retrieval(tenant_id, spec)
        detail = (
            f"v{published.version} {published.status}, "
            f"indexed ({published.chunk_count} chunks)"
            if indexed
            else (
                f"v{published.version} {published.status}, "
                f"NOT retrievable after "
                f"{settings.BOOTSTRAP_INDEXING_TIMEOUT_SECONDS}s"
            )
        )
        report.add(f"Policy {spec.policy_code}", "OK" if indexed else "FAILED", detail)
        if not indexed:
            report.note(
                f"{spec.policy_code} published but retrieval never returned it. "
                "The retrieval worker may be down or still downloading its "
                "embedding model. Check: docker compose logs retrieval-worker"
            )


async def _import_sanctions(
    api: AdminApiClient,
    report: BootstrapReport,
    args: argparse.Namespace,
) -> None:
    configured = sanctions.configured_sources()
    details: list[str] = []
    failed = False
    eu_unconfigured = False

    for source in sanctions.SOURCES:
        if not configured[source]:
            details.append(f"{source} NOT CONFIGURED")
            if source == "EU":
                eu_unconfigured = True
            else:
                failed = True
            continue
        outcome = await sanctions.import_source(api, source)
        details.append(f"{source} {outcome.status}")
        if not outcome.succeeded:
            if source == "EU":
                eu_unconfigured = True
            else:
                failed = True

    # An unconfigured EU source is a setup decision, not a crash. It blocks
    # supplier scenarios unless the operator has explicitly opted out.
    blocking = not (eu_unconfigured and args.allow_missing_eu_sanctions)
    status = "OK" if not failed and not eu_unconfigured else "MISSING"
    report.add("Sanctions", status, " · ".join(details), blocking=blocking)

    if eu_unconfigured:
        report.note(
            sanctions.EU_NOT_CONFIGURED_MESSAGE
            if not args.allow_missing_eu_sanctions
            else (
                "EU sanctions source is not configured. Continuing because "
                "--allow-missing-eu-sanctions was given; supplier scenarios "
                "will still block at screening."
            )
        )


async def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = (
            await run_check(uuid.UUID(args.tenant_id))
            if args.check
            else await run_bootstrap(args)
        )
    except (
        reference_data.ReferenceDataError,
        policies.PolicyPublicationError,
        BootstrapAuthError,
    ) as error:
        # A known setup problem gets one clear sentence, not a traceback.
        print(f"Bootstrap failed: {error}", file=sys.stderr)
        return 1

    title = (
        "NeuroX business-readiness check."
        if args.check
        else "NeuroX bootstrap complete."
    )
    print(report.render(title=title))
    return 0 if report.business_ready else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
