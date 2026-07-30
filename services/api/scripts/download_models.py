"""Download model weights at image build time, with retries.

Run as a dedicated build step so the weights land in their own layer, before
the application code is copied. Editing a worker then costs a layer rebuild
rather than a multi-gigabyte re-download.

The retry loop is not defensive padding: a clean build on 2026-07-28 failed
partway through a model download and lost the whole 35-minute build with it.

Usage:
    python -m scripts.download_models document
    python -m scripts.download_models retrieval
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 5


def _download_document_models() -> None:
    import easyocr

    easyocr.Reader(
        ["en"],
        gpu=False,
        model_storage_directory="/opt/easyocr",
        download_enabled=True,
    )


def _download_retrieval_models() -> None:
    from fastembed import SparseTextEmbedding, TextEmbedding
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    SparseTextEmbedding("Qdrant/bm25")
    TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")


TARGETS: dict[str, Callable[[], None]] = {
    "document": _download_document_models,
    "retrieval": _download_retrieval_models,
}


def download_with_retries(target: str) -> None:
    downloader = TARGETS[target]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            downloader()
        except Exception as error:  # noqa: BLE001 - any failure is worth retrying
            if attempt == MAX_ATTEMPTS:
                raise
            delay = BACKOFF_SECONDS * attempt
            print(
                f"{target} model download attempt {attempt}/{MAX_ATTEMPTS} failed "
                f"({type(error).__name__}: {error}); retrying in {delay}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
        else:
            print(f"{target} models ready", flush=True)
            return


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TARGETS:
        print(f"usage: python -m scripts.download_models {{{'|'.join(TARGETS)}}}", file=sys.stderr)
        return 2
    download_with_retries(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
