"""Import a checksum-pinned normalized export from OFAC, UN, or EU.

Expected CSV columns: external_id,name,aliases,countries. Aliases and countries
are pipe-separated. Fetching official data is intentionally kept outside the
runtime so provenance and checksum approval can happen before publication.
"""

import argparse
import asyncio
import csv
import hashlib
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.domain.security import normalize_vendor_name
from app.models import SanctionsDataset, SanctionsEntityRecord
from app.workers.database import WorkerSession


async def load(source: str, version: str, source_url: str, path: Path, expected_sha256: str) -> None:
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256.lower():
        raise SystemExit(f"Checksum mismatch: expected {expected_sha256}, got {actual}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"external_id", "name", "aliases", "countries"}
    if not rows or not required.issubset(rows[0]):
        raise SystemExit(f"CSV must contain {sorted(required)}")
    async with WorkerSession() as session:
        async with session.begin():
            existing = await session.scalar(select(SanctionsDataset).where(SanctionsDataset.source == source, SanctionsDataset.version == version))
            if existing and existing.status == "PUBLISHED":
                print(f"Already published: {source} {version} {existing.dataset_id}")
                return
            dataset = existing or SanctionsDataset(
                dataset_id=uuid.uuid4(), source=source, version=version,
                source_url=source_url, sha256=actual, status="STAGED",
            )
            if not existing:
                session.add(dataset)
                await session.flush()
            else:
                await session.execute(delete(SanctionsEntityRecord).where(SanctionsEntityRecord.dataset_id == dataset.dataset_id))
            for row in rows:
                primary_name = " ".join(row["name"].split())
                if not row["external_id"].strip() or not primary_name:
                    raise SystemExit("Every row requires external_id and name")
                session.add(SanctionsEntityRecord(
                    dataset_id=dataset.dataset_id,
                    external_id=row["external_id"].strip(),
                    primary_name=primary_name,
                    normalized_name=normalize_vendor_name(primary_name),
                    aliases=[value.strip() for value in row["aliases"].split("|") if value.strip()],
                    countries=[value.strip().upper() for value in row["countries"].split("|") if value.strip()],
                ))
            dataset.status = "PUBLISHED"
            from datetime import UTC, datetime
            dataset.published_at = datetime.now(UTC)
    print(f"Published {len(rows)} {source} entities for version {version}; sha256={actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["OFAC", "UN", "EU"], required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    asyncio.run(load(args.source, args.version, args.source_url, args.file, args.sha256))


if __name__ == "__main__":
    main()
