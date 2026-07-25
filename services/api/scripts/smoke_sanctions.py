"""Download and parse official sanctions sources without persisting records."""

import argparse
import asyncio

from app.sanctions import (
    configured_source_url,
    download_official_dataset,
    parse_official_dataset,
)


async def main(sources: list[str]) -> None:
    for source in sources:
        result = await download_official_dataset(
            source,
            configured_source_url(source),
        )
        records = await asyncio.to_thread(
            parse_official_dataset,
            source,
            result.payload,
        )
        print(
            f"{source}: records={len(records)} "
            f"sha256={result.sha256[:12]} version={result.version}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "sources",
        nargs="+",
        choices=["OFAC", "UN", "EU"],
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.sources))
