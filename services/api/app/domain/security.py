import hashlib
import hmac
import json
import os
import re
import unicodedata
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LEGAL_SUFFIXES = re.compile(r"\b(llc|inc|incorporated|ltd|limited|plc|pvt|private|corp|corporation|company|co)\b", re.I)


def normalize_vendor_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    without_suffixes = LEGAL_SUFFIXES.sub(" ", ascii_value.lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_suffixes).split())


def blind_index(value: str, secret: str) -> bytes:
    normalized = "".join(value.upper().split())
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).digest()


def encrypt_sensitive_value(value: str, secret: str) -> bytes:
    key = hashlib.sha256(secret.encode()).digest()
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, value.encode(), None)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def chained_audit_hash(previous_hash: str | None, record: dict[str, Any]) -> str:
    return canonical_hash({"previous_hash": previous_hash, "record": record})
