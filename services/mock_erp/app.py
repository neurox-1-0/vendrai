import hashlib
import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="NeuroX Simulated ERP", version="1.0.0")
DB_PATH = Path(os.getenv("ERP_DB_PATH", "/data/mock-erp.sqlite"))


class VendorCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=240)
    registered_country: str | None = Field(default=None, min_length=2, max_length=2)
    approval_task_id: str
    evidence_hash: str = Field(min_length=64, max_length=64)


def connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS vendor_writes (idempotency_key TEXT PRIMARY KEY, erp_vendor_id TEXT NOT NULL, payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS invoice_resolutions (idempotency_key TEXT PRIMARY KEY, resolution_id TEXT NOT NULL, case_id TEXT NOT NULL, payload TEXT NOT NULL)")
    return db


@app.post("/v1/vendors", status_code=201)
def create_vendor(body: VendorCreate, idempotency_key: str = Header(alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(400, detail={"code": "IDEMPOTENCY_KEY_REQUIRED"})
    db = connection()
    try:
        existing = db.execute("SELECT erp_vendor_id FROM vendor_writes WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing:
            return {"erp_vendor_id": existing[0], "idempotent_replay": True}
        erp_vendor_id = "ERP-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()
        db.execute(
            "INSERT INTO vendor_writes(idempotency_key, erp_vendor_id, payload) VALUES (?, ?, ?)",
            (idempotency_key, erp_vendor_id, json.dumps(body.model_dump(), sort_keys=True)),
        )
        db.commit()
        return {"erp_vendor_id": erp_vendor_id, "idempotent_replay": False}
    finally:
        db.close()


@app.post("/v1/invoice-exceptions/{case_id}/resolve", status_code=201)
def resolve_invoice_exception(case_id: str, body: dict, idempotency_key: str = Header(alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(400, detail={"code": "IDEMPOTENCY_KEY_REQUIRED"})
    db = connection()
    try:
        existing = db.execute("SELECT resolution_id FROM invoice_resolutions WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing:
            return {"resolution_id": existing[0], "idempotent_replay": True}
        resolution_id = "RES-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()
        db.execute(
            "INSERT INTO invoice_resolutions(idempotency_key, resolution_id, case_id, payload) VALUES (?, ?, ?, ?)",
            (idempotency_key, resolution_id, case_id, json.dumps(body, sort_keys=True)),
        )
        db.commit()
        return {"resolution_id": resolution_id, "idempotent_replay": False}
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "healthy"}
