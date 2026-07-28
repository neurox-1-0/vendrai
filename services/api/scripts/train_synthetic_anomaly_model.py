"""Train a synthetic-only shadow anomaly model for competition evaluation.

This command never promotes a model to active authority. Production models
must be trained from a reviewed, tenant-scoped immutable snapshot and pass the
separate activation gates documented by the API.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime

import numpy as np
import skops.io as sio
from app.models import ModelVersion
from app.services.storage import store_private_artifact
from app.workers.database import WorkerSession, set_worker_tenant
from sklearn.ensemble import IsolationForest
from sqlalchemy import select

FEATURES = [
    "unit_price_ratio",
    "quantity_receipt_ratio",
    "invoice_total_percentile",
    "days_since_previous_invoice",
    "days_since_bank_change",
    "bank_changes_30d",
]


def synthetic_history(seed: int, rows: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.column_stack(
        [
            rng.normal(1.0, 0.06, rows),
            rng.normal(1.0, 0.08, rows),
            rng.uniform(0.0, 1.0, rows),
            rng.gamma(2.5, 6.0, rows),
            rng.gamma(4.0, 45.0, rows),
            rng.binomial(1, 0.01, rows),
        ]
    )


async def train(
    tenant_id: uuid.UUID,
    *,
    seed: int = 42,
    rows: int = 2000,
) -> dict:
    if rows < 1000:
        raise ValueError("At least 1,000 synthetic rows are required")
    training = synthetic_history(seed, rows)
    model = IsolationForest(
        n_estimators=200,
        contamination=0.02,
        random_state=seed,
    ).fit(training)
    artifact = sio.dumps(model)
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    recipe = {
        "data_origin": "SYNTHETIC",
        "mode": "SHADOW",
        "seed": seed,
        "row_count": rows,
        "features": FEATURES,
        "estimator": "IsolationForest",
        "n_estimators": 200,
        "contamination": 0.02,
    }
    configuration_hash = hashlib.sha256(
        json.dumps(recipe, sort_keys=True).encode()
    ).hexdigest()
    version = f"synthetic-{datetime.now(UTC):%Y%m%d}-{configuration_hash[:8]}"
    artifact_key = f"models/{tenant_id}/invoice-anomaly/{version}.skops"
    manifest_key = f"models/{tenant_id}/invoice-anomaly/{version}.json"
    manifest = {
        **recipe,
        "version": version,
        "artifact_key": artifact_key,
        "artifact_sha256": artifact_sha256,
        "configuration_hash": configuration_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "activation_eligible": False,
    }
    store_private_artifact(
        artifact_key, artifact, "application/octet-stream"
    )
    store_private_artifact(
        manifest_key,
        json.dumps(manifest, sort_keys=True, indent=2).encode(),
        "application/json",
    )
    async with WorkerSession() as session, session.begin():
        await set_worker_tenant(session, str(tenant_id))
        existing = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.tenant_id == tenant_id,
                ModelVersion.provider == "SKLEARN",
                ModelVersion.model_name == "invoice-anomaly-isolation-forest",
                ModelVersion.version == version,
            )
        )
        if not existing:
            session.add(
                ModelVersion(
                    tenant_id=tenant_id,
                    provider="SKLEARN",
                    model_name="invoice-anomaly-isolation-forest",
                    version=version,
                    configuration_hash=configuration_hash,
                    status="EVALUATION_REQUIRED",
                )
            )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rows", type=int, default=2000)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                train(args.tenant_id, seed=args.seed, rows=args.rows)
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
