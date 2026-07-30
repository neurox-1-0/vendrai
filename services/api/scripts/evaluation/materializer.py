"""Apply each case's declared mutation to produce the documents to submit.

Determinism is the requirement, not a nicety: the same seed must produce
byte-identical output, because that is what makes the whole evaluation
reproducible. If materialisation drifts, a score change cannot be attributed to
a code change.

Output is cached by content hash. Materialising 100 cases on every run, when
the inputs and mutations have not changed, is wasted wall-clock time on the
cheapest stage of the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from scripts.evaluation.manifest import EvaluationCase, Mutation


class MaterializationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterializedDocument:
    source: Path
    path: Path
    sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": str(self.source),
            "path": str(self.path),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class MaterializedCase:
    case_id: str
    documents: tuple[MaterializedDocument, ...]
    mutation: Mutation

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "mutation": self.mutation.as_dict(),
            "documents": [document.as_dict() for document in self.documents],
        }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutation_key(source: Path, mutation: Mutation) -> str:
    """Cache key over the source bytes and the mutation parameters.

    Both halves matter: the same mutation over a changed source must produce a
    different artefact, and so must a changed mutation over the same source.
    """
    payload = json.dumps(
        {"source": _digest(source), "mutation": mutation.as_dict()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _is_identity(mutation: Mutation) -> bool:
    return mutation.contrast == 1.0 and mutation.rotate_degrees == 0.0


def _apply_image_mutation(source: Path, destination: Path, mutation: Mutation) -> None:
    """Render, mutate, and re-emit each page.

    Pillow's operations are deterministic for fixed parameters, and the seed is
    folded into the cache key rather than into any random draw - there is no
    randomness here to seed. The seed exists so that a future stochastic
    mutation can be added without changing the manifest format.
    """
    try:
        import fitz  # type: ignore[import-not-found]  # PyMuPDF
        from PIL import Image, ImageEnhance
    except ImportError as error:
        raise MaterializationError(
            "Document mutation needs PyMuPDF and Pillow. Install the "
            "evaluation extras: pip install -r requirements-evaluation.txt"
        ) from error

    document = fitz.open(source)
    pages: list[Image.Image] = []
    try:
        for page in document:
            # A fixed DPI keeps output byte-identical across machines.
            pixmap = page.get_pixmap(dpi=200)
            image = Image.frombytes(
                "RGB", (pixmap.width, pixmap.height), pixmap.samples
            )
            if mutation.contrast != 1.0:
                image = ImageEnhance.Contrast(image).enhance(mutation.contrast)
            if mutation.rotate_degrees:
                image = image.rotate(
                    mutation.rotate_degrees, expand=True, fillcolor=(255, 255, 255)
                )
            pages.append(image.convert("RGB"))
    finally:
        document.close()

    if not pages:
        raise MaterializationError(f"{source} produced no pages")
    destination.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        destination,
        save_all=True,
        append_images=pages[1:],
        format="PDF",
        resolution=200.0,
    )
    _freeze_pdf_timestamps(destination)


# Pillow stamps the current time into /CreationDate and /ModDate, which makes
# every materialisation of the same inputs a different file. That would break
# the one property this stage has to have.
#
# The replacement is byte-for-byte the same length as what Pillow writes
# (D:YYYYMMDDHHMMSSZ), so the xref offsets stay valid.
_PDF_TIMESTAMP = re.compile(rb"/(CreationDate|ModDate) \(D:\d{14}Z\)")
_FROZEN_TIMESTAMP = b"D:19700101000000Z"


def _freeze_pdf_timestamps(path: Path) -> None:
    data = path.read_bytes()

    def replace(match: re.Match[bytes]) -> bytes:
        return b"/" + match.group(1) + b" (" + _FROZEN_TIMESTAMP + b")"

    frozen, count = _PDF_TIMESTAMP.subn(replace, data)
    if count:
        path.write_bytes(frozen)


def materialize_document(
    source: Path,
    mutation: Mutation,
    cache_root: Path,
) -> MaterializedDocument:
    if not source.exists():
        raise MaterializationError(f"source document not found: {source}")

    key = mutation_key(source, mutation)
    destination = cache_root / key[:2] / f"{key}{source.suffix}"
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _is_identity(mutation):
            # No mutation declared. Copying keeps the artefact manifest
            # uniform without paying to re-render an unchanged document.
            shutil.copyfile(source, destination)
        else:
            _apply_image_mutation(source, destination, mutation)
    return MaterializedDocument(
        source=source, path=destination, sha256=_digest(destination)
    )


def materialize_case(
    case: EvaluationCase,
    *,
    repository_root: Path,
    cache_root: Path,
) -> MaterializedCase:
    documents = tuple(
        materialize_document(repository_root / document, case.mutation, cache_root)
        for document in case.documents
    )
    return MaterializedCase(
        case_id=case.case_id, documents=documents, mutation=case.mutation
    )


def materialize_manifest(
    cases: list[EvaluationCase],
    *,
    repository_root: Path,
    cache_root: Path,
    artifact_manifest: Path | None = None,
) -> list[MaterializedCase]:
    materialized = [
        materialize_case(
            case, repository_root=repository_root, cache_root=cache_root
        )
        for case in cases
    ]
    if artifact_manifest is not None:
        artifact_manifest.parent.mkdir(parents=True, exist_ok=True)
        artifact_manifest.write_text(
            json.dumps(
                [item.as_dict() for item in materialized],
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return materialized
