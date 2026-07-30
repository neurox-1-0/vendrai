"""The bootstrap's data path, against the shipped corpus.

The blind-index assertion is the important one. A loader that writes plaintext
into ``tax_id_hash`` produces a vendor master that looks correct in every
report and matches nothing, so VO-002 fails with no error and no clue.
"""

import uuid
from pathlib import Path

import pytest
from app.config import settings
from app.database import AsyncSessionLocal, set_tenant_context
from app.domain.security import blind_index
from app.models import InvoiceHistoryRecord, Vendor
from sqlalchemy import select

from scripts.bootstrap import identities, reference_data
from scripts.bootstrap.report import BootstrapReport

CORPUS_ROOT = Path(__file__).parents[3] / "Vendrai_Procurement_Document_Corpus_v2"
TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")

pytestmark = pytest.mark.skipif(
    not (CORPUS_ROOT / reference_data.VENDOR_MASTER).exists(),
    reason="corpus not present",
)


async def _load(session):
    await set_tenant_context(session, str(TENANT_ID))
    await identities.ensure_tenant(session, TENANT_ID)
    vendors = await reference_data.load_vendor_master(session, TENANT_ID, CORPUS_ROOT)
    history = await reference_data.load_invoice_history(session, TENANT_ID, CORPUS_ROOT)
    return vendors, history


async def test_vendor_master_and_invoice_history_load():
    async with AsyncSessionLocal() as session, session.begin():
        vendors, history = await _load(session)
    assert vendors.created > 0
    assert history.created > 0


async def test_identifiers_are_stored_as_blind_indexes_not_plaintext():
    async with AsyncSessionLocal() as session, session.begin():
        await _load(session)
        vendor = await session.scalar(
            select(Vendor).where(
                Vendor.tenant_id == TENANT_ID, Vendor.erp_vendor_id == "V000233"
            )
        )
        assert vendor is not None
        # The exact value the corpus states for V000233. If this is stored as
        # plaintext, or hashed with a different secret, duplicate detection
        # never matches and the failure is completely silent.
        assert vendor.tax_id_hash == blind_index("119887654", settings.BLIND_INDEX_SECRET)
        assert vendor.bank_account_hash == blind_index(
            "011-987-4402", settings.BLIND_INDEX_SECRET
        )
        assert vendor.email_domain == "apex-digital.example"


async def test_blind_index_verification_passes_after_a_correct_load():
    async with AsyncSessionLocal() as session, session.begin():
        await _load(session)
        await reference_data.verify_blind_indexes(session, TENANT_ID, CORPUS_ROOT)


async def test_blind_index_verification_catches_a_plaintext_load():
    """Prove the guard bites - it is the only thing that makes the bug loud."""
    async with AsyncSessionLocal() as session, session.begin():
        await _load(session)
        vendor = await session.scalar(
            select(Vendor).where(
                Vendor.tenant_id == TENANT_ID, Vendor.erp_vendor_id == "V000184"
            )
        )
        vendor.tax_id_hash = b"114598732"  # what a naive loader would write
        await session.flush()

        rows = reference_data._read_rows(
            CORPUS_ROOT / reference_data.VENDOR_MASTER, {"vendor_id", "tax_id"}
        )
        assert rows[0]["vendor_id"] == "V000184", "probe row moved; update this test"

        with pytest.raises(reference_data.ReferenceDataError, match="Blind index mismatch"):
            await reference_data.verify_blind_indexes(session, TENANT_ID, CORPUS_ROOT)


async def test_loading_twice_changes_nothing():
    async with AsyncSessionLocal() as session, session.begin():
        first_vendors, first_history = await _load(session)
    async with AsyncSessionLocal() as session, session.begin():
        second_vendors, second_history = await _load(session)

    assert second_vendors.created == 0
    assert second_history.created == 0
    assert second_vendors.total == first_vendors.total
    assert second_history.total == first_history.total

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, str(TENANT_ID))
        vendor_rows = len(
            (
                await session.execute(
                    select(Vendor.vendor_id).where(Vendor.tenant_id == TENANT_ID)
                )
            ).all()
        )
        history_rows = len(
            (
                await session.execute(
                    select(InvoiceHistoryRecord.record_id).where(
                        InvoiceHistoryRecord.tenant_id == TENANT_ID
                    )
                )
            ).all()
        )
    assert vendor_rows == first_vendors.total
    assert history_rows == first_history.total


async def test_seven_identities_each_hold_exactly_one_role():
    async with AsyncSessionLocal() as session, session.begin():
        await set_tenant_context(session, str(TENANT_ID))
        await identities.ensure_tenant(session, TENANT_ID)
        count = await identities.ensure_users(session, TENANT_ID)
        assert count == 7
        assert await identities.role_separation_holds(session, TENANT_ID)

    assert [identity.role for identity in identities.IDENTITIES] == [
        "requester",
        "analyst",
        "procurement_approver",
        "compliance_approver",
        "finance_approver",
        "auditor",
        "admin",
    ], "role separation is the point; do not merge these"


async def test_rerunning_repairs_an_identity_that_gained_a_second_role():
    from app.models import User

    async with AsyncSessionLocal() as session, session.begin():
        await set_tenant_context(session, str(TENANT_ID))
        await identities.ensure_tenant(session, TENANT_ID)
        await identities.ensure_users(session, TENANT_ID)
        auditor = await session.get(User, identities.IDENTITIES[5].user_id)
        auditor.roles = ["auditor", "admin"]
        await session.flush()
        assert not await identities.role_separation_holds(session, TENANT_ID)

        await identities.ensure_users(session, TENANT_ID)
        assert await identities.role_separation_holds(session, TENANT_ID)


def test_report_names_the_blocker_rather_than_just_failing():
    report = BootstrapReport()
    report.add("Vendor master", "OK", "24 vendors")
    report.add("Sanctions", "MISSING", "EU NOT CONFIGURED")
    rendered = report.render()

    assert report.business_ready is False
    assert "Business-ready:" in rendered
    assert "sanctions" in rendered


def test_a_non_blocking_step_does_not_hold_back_readiness():
    report = BootstrapReport()
    report.add("Vendor master", "OK", "24 vendors")
    report.add("Sanctions", "SKIPPED", "--skip-sanctions", blocking=False)
    assert report.business_ready is True
