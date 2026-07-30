"""Where a piece of evidence came from, and how much weight that permits.

An uploaded purchase order and a purchase order read from the ERP look
identical once they are text. They are not the same evidence. Treating a
document the supplier or requester provided as though it came from the system
of record implicitly claims an ERP integration the product does not have, and
lets a party to the transaction supply the evidence used to check it.

Recording provenance is a small change. Not recording it is a claim.
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    #: Supplied by a party to the case - the requester or the supplier. Usable
    #: as evidence, never as corroboration of itself.
    USER_UPLOADED = "USER_UPLOADED"
    #: Read from the authoritative system of record.
    ERP_SYSTEM_OF_RECORD = "ERP_SYSTEM_OF_RECORD"
    #: An official external list (sanctions, registries) imported with a
    #: recorded source URL and checksum.
    EXTERNAL_OFFICIAL_LIST = "EXTERNAL_OFFICIAL_LIST"
    #: The tenant's own published, versioned policy corpus.
    TENANT_POLICY = "TENANT_POLICY"
    #: Produced by the platform's deterministic controls from other evidence.
    DERIVED_BY_SYSTEM = "DERIVED_BY_SYSTEM"


#: Human-readable labels for the case UI. Kept beside the enum so a new value
#: cannot reach a screen without someone deciding what it says.
PROVENANCE_LABELS: dict[Provenance, str] = {
    Provenance.USER_UPLOADED: "Uploaded document",
    Provenance.ERP_SYSTEM_OF_RECORD: "ERP system of record",
    Provenance.EXTERNAL_OFFICIAL_LIST: "Official external list",
    Provenance.TENANT_POLICY: "Published policy",
    Provenance.DERIVED_BY_SYSTEM: "Derived by the system",
}

#: Provenances that cannot independently corroborate a claim made by the same
#: party that supplied them.
SELF_ASSERTED = frozenset({Provenance.USER_UPLOADED})


def is_authoritative(provenance: Provenance | str) -> bool:
    """Can this evidence stand on its own as verification?

    A user-uploaded document cannot. That is the whole distinction, and the
    reason AP-007's second finding exists: an invoice asserting new bank
    details is not authority to change them.
    """
    return Provenance(provenance) not in SELF_ASSERTED


#: The source_type values already written by the workers, mapped to the
#: provenance each implies. Existing rows predate the column, so the mapping
#: also serves as the backfill rule.
SOURCE_TYPE_PROVENANCE: dict[str, Provenance] = {
    "POLICY": Provenance.TENANT_POLICY,
    "POLICY_CLAUSE": Provenance.TENANT_POLICY,
    "VENDOR_MASTER": Provenance.ERP_SYSTEM_OF_RECORD,
    "INVOICE_HISTORY": Provenance.ERP_SYSTEM_OF_RECORD,
    "PURCHASE_ORDER": Provenance.ERP_SYSTEM_OF_RECORD,
    "GOODS_RECEIPT": Provenance.ERP_SYSTEM_OF_RECORD,
    "SANCTIONS_LIST": Provenance.EXTERNAL_OFFICIAL_LIST,
    "RISK_SERVICE": Provenance.EXTERNAL_OFFICIAL_LIST,
    "DOCUMENT": Provenance.USER_UPLOADED,
    "DOCUMENT_PAGE": Provenance.USER_UPLOADED,
    "EXTRACTED_FIELD": Provenance.USER_UPLOADED,
    "UPLOADED_PURCHASE_ORDER": Provenance.USER_UPLOADED,
    "UPLOADED_GOODS_RECEIPT": Provenance.USER_UPLOADED,
}


def provenance_for(source_type: str) -> Provenance:
    """Infer provenance from a source type.

    Unknown types are DERIVED_BY_SYSTEM rather than authoritative: an
    unrecognised source should never be promoted to system-of-record by
    accident.
    """
    return SOURCE_TYPE_PROVENANCE.get(source_type.upper(), Provenance.DERIVED_BY_SYSTEM)
