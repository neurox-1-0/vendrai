"""Publish the tenant's policies through the product's own knowledge API.

Publishing is not the hard part. **Waiting for indexing is.**

``POST .../:publish`` only enqueues ``policy.published.v1``; the retrieval
worker consumes it asynchronously and writes the vectors. A bootstrap that
returns as soon as the publish call succeeds reports "policies published"
while retrieval still answers nothing - and every downstream scenario then
fails on missing policy evidence, pointing at retrieval rather than at the
race that actually caused it.

So each policy is probed with a phrase drawn from its own text until retrieval
returns it, with a bounded timeout and an explicit failure when it expires.
That is the difference between "policies exist in Postgres" and "policy
retrieval works", and only the second one matters to a scenario.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from app.config import settings

from scripts.bootstrap.api_client import AdminApiClient

KNOWLEDGE_BASE = Path("knowledge_base")


class PolicyPublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicySpec:
    filename: str
    policy_code: str
    title: str
    owner_department: str
    version: str
    effective_date: str
    # A phrase that appears in this policy and in no other, used to prove
    # retrieval can actually find the document after indexing.
    probe_query: str
    probe_expects: str


POLICIES: tuple[PolicySpec, ...] = (
    PolicySpec(
        filename="PROC-001_Supplier_Onboarding_Policy.pdf",
        policy_code="PROC-001",
        title="Supplier Onboarding and Due Diligence Policy",
        owner_department="Procurement and Finance Governance",
        version="3.2",
        effective_date="2026-06-01",
        probe_query=(
            "required documents for supplier onboarding tax registration "
            "bank account confirmation insurance"
        ),
        probe_expects="onboarding form",
    ),
    PolicySpec(
        filename="AP-001_Invoice_Matching_and_Exception_Policy.pdf",
        policy_code="AP-001",
        title="Invoice Matching and Exception Management Policy",
        owner_department="Procurement and Finance Governance",
        version="2.5",
        effective_date="2026-06-01",
        probe_query="invoice price variance tolerance percent procurement review",
        # The clause body reads "...requires procurement review and documented
        # approval." - "tolerance" only appears in the section *heading*
        # ("3. Price tolerance"), which this probe never inspects, so the
        # probe reported AP-001 as unretrievable when retrieval was in fact
        # returning exactly the right clause.
        probe_expects="procurement review",
    ),
)


@dataclass
class PublicationResult:
    policy_code: str
    version: str
    status: str
    chunk_count: int
    already_present: bool
    indexed: bool = False


def extract_pdf_text(path: Path) -> str:
    """Read policy text with pypdf - the library the project actually pins.

    The superseded ad-hoc script imported PyPDF2, which is not in
    requirements.txt, so it could never have run inside the API image as built.
    """
    from pypdf import PdfReader

    if not path.exists():
        raise PolicyPublicationError(
            f"Policy PDF missing: {path}. The corpus is mounted at "
            f"{settings.CORPUS_ROOT}; check the read-only mount in "
            "docker-compose.yml."
        )
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < 200:
        raise PolicyPublicationError(
            f"{path.name} yielded only {len(text.strip())} characters of text. "
            "A scanned or image-only policy cannot be chunked or retrieved."
        )
    return text


async def publish_policy(
    api: AdminApiClient,
    spec: PolicySpec,
    corpus_root: Path,
) -> PublicationResult:
    text = extract_pdf_text(corpus_root / KNOWLEDGE_BASE / spec.filename)
    # A stable key makes a re-run a no-op rather than a duplicate.
    key = f"bootstrap-policy-{spec.policy_code}-{spec.version}"

    response = await api.post(
        "/knowledge/documents",
        json={
            "policy_code": spec.policy_code,
            "title": spec.title,
            "owner_department": spec.owner_department,
            "version": spec.version,
            "effective_date": spec.effective_date,
            "content": text,
        },
        idempotency_key=key,
    )
    if response.status_code == 409:
        # Already created by an earlier run. Idempotency means finishing the
        # job, not stopping - the version may still be unpublished.
        existing = await _find_existing(api, spec)
        if existing is None:
            raise PolicyPublicationError(
                f"{spec.policy_code} reports POLICY_ALREADY_EXISTS but no "
                "version is readable. The policy tables may be inconsistent."
            )
        return await _ensure_published(api, spec, existing, already_present=True)
    if response.status_code != 201:
        raise PolicyPublicationError(
            f"Creating {spec.policy_code} failed with {response.status_code}: "
            f"{response.text[:300]}"
        )
    return await _ensure_published(
        api, spec, response.json(), already_present=False
    )


async def _find_existing(api: AdminApiClient, spec: PolicySpec) -> dict | None:
    response = await api.get("/knowledge/documents", params={"policy_code": spec.policy_code})
    if response.status_code != 200:
        return None
    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return next(
        (item for item in items if item.get("policy_code") == spec.policy_code),
        None,
    )


async def _ensure_published(
    api: AdminApiClient,
    spec: PolicySpec,
    payload: dict,
    *,
    already_present: bool,
) -> PublicationResult:
    version_id = payload["policy_version_id"]
    if payload.get("status") != "PUBLISHED":
        response = await api.post(
            f"/knowledge/documents/{version_id}:publish",
            idempotency_key=f"bootstrap-publish-{spec.policy_code}-{spec.version}",
        )
        if response.status_code != 200:
            raise PolicyPublicationError(
                f"Publishing {spec.policy_code} failed with "
                f"{response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
    return PublicationResult(
        policy_code=spec.policy_code,
        version=payload.get("version", spec.version),
        status=payload.get("status", "PUBLISHED"),
        chunk_count=int(payload.get("chunk_count", 0)),
        already_present=already_present,
    )


async def probe_retrieval(
    tenant_id: uuid.UUID,
    spec: PolicySpec,
    *,
    timeout_seconds: int | None = None,
    poll_seconds: float = 3.0,
) -> bool:
    """Poll retrieval until this policy's clauses come back, or time out.

    Returns True on success. The caller decides what an expired timeout means;
    it is never treated as success.
    """
    budget = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.BOOTSTRAP_INDEXING_TIMEOUT_SECONDS
    )
    deadline = time.monotonic() + budget
    async with httpx.AsyncClient(timeout=30) as client:
        # Always probe at least once, so timeout_seconds=0 means "check now"
        # rather than "do not check" - the readiness check relies on that.
        while True:
            if await _probe_once(client, tenant_id, spec):
                return True
            if time.monotonic() + poll_seconds >= deadline:
                return False
            await asyncio.sleep(poll_seconds)


async def _probe_once(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    spec: PolicySpec,
) -> bool:
    try:
        response = await client.post(
            f"{settings.RETRIEVAL_URL}/v1/search",
            json={
                "query": spec.probe_query,
                "tenant_id": str(tenant_id),
                "roles": ["admin"],
                "limit": 8,
            },
        )
    except httpx.HTTPError:
        # The retrieval service may still be downloading its embedding model.
        return False
    if response.status_code != 200:
        return False
    items = response.json().get("items", [])
    return any(
        item.get("policy_code") == spec.policy_code
        and spec.probe_expects.lower() in str(item.get("content", "")).lower()
        for item in items
    )
