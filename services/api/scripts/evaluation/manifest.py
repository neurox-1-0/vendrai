"""Read and validate the 100-case manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class ManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mutation:
    contrast: float = 1.0
    rotate_degrees: float = 0.0
    seed: int = 0

    @classmethod
    def from_dict(cls, payload: dict) -> Mutation:
        return cls(
            contrast=float(payload.get("contrast", 1.0)),
            rotate_degrees=float(payload.get("rotate_degrees", 0.0)),
            seed=int(payload.get("seed", 0)),
        )

    def as_dict(self) -> dict[str, float | int]:
        return {
            "contrast": self.contrast,
            "rotate_degrees": self.rotate_degrees,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    workflow: str
    scenario: str
    source_case: str
    documents: tuple[str, ...]
    expected_reason_codes: tuple[str, ...]
    mutation: Mutation
    requires_real_gemini: bool
    resumable_on_quota: bool
    synthetic_only: bool

    @property
    def base_scenario(self) -> str:
        """The corpus scenario key, e.g. VO-001, used to look up the oracle."""
        return self.source_case.split("_", 1)[0]

    @classmethod
    def from_dict(cls, payload: dict) -> EvaluationCase:
        try:
            return cls(
                case_id=str(payload["case_id"]),
                workflow=str(payload["workflow"]),
                scenario=str(payload["scenario"]),
                source_case=str(payload["source_case"]),
                documents=tuple(str(item) for item in payload["documents"]),
                expected_reason_codes=tuple(
                    str(item) for item in payload.get("expected_reason_codes", [])
                ),
                mutation=Mutation.from_dict(payload.get("mutation", {})),
                requires_real_gemini=bool(payload.get("requires_real_gemini", True)),
                resumable_on_quota=bool(payload.get("resumable_on_quota", True)),
                synthetic_only=bool(payload.get("synthetic_only", True)),
            )
        except KeyError as error:
            raise ManifestError(f"manifest row is missing {error}") from error


def load_manifest(path: Path) -> list[EvaluationCase]:
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    cases = [
        EvaluationCase.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ManifestError("manifest contains duplicate case_id values")
    return cases


def verify_manifest_digest(path: Path, digest_path: Path) -> str:
    """Confirm the manifest has not drifted from its recorded digest.

    An evaluation whose input changed silently is not reproducible, and the
    published numbers would describe a dataset nobody can reconstruct.
    """
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = digest_path.read_text(encoding="utf-8").split()[0]
    if actual != expected:
        raise ManifestError(
            f"manifest digest mismatch: {path.name} hashes to {actual} but "
            f"{digest_path.name} records {expected}. Line endings are a common "
            "cause - the digest is over the LF form."
        )
    return actual


def load_oracle(path: Path) -> dict[str, dict]:
    """Per-scenario expected status, risk, findings, and required human action."""
    if not path.exists():
        raise ManifestError(f"scoring oracle not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
