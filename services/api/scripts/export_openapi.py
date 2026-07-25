"""Export the deterministic API contract consumed by Orval and CI."""

import json
from pathlib import Path

from app.main import app


def main() -> None:
    target = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "contracts"
        / "openapi.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
