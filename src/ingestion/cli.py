import argparse
import asyncio
import json
from pathlib import Path

import httpx

from src.ingestion.acquire import acquire, catalog, sha256_file
from src.integrations.opensearch import OpenSearch
from src.observability.logging import configure_logging
from src.pipelines.load import load_silver
from src.pipelines.runner import process
from src.services.db import make_engine, session_factory
from src.services.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire, validate and ingest public incident/log datasets"
    )
    parser.add_argument("dataset", help="Manifest key or 'all'")
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, default=Path("data/dataset_manifest.json"))
    parser.add_argument(
        "--limit", type=int, default=100, help="Records or complete XES traces; default 100"
    )
    parser.add_argument(
        "--full", action="store_true", help="Process every record in the acquired input"
    )
    parser.add_argument(
        "--timezone",
        help="Explicit assumption for timestamps with no timezone, e.g. Europe/Amsterdam",
    )
    parser.add_argument(
        "--input", type=Path, help="Larger local uncompressed log file or original BPI input"
    )
    parser.add_argument(
        "--sha256", help="Required checksum for --input; records provenance of full local datasets"
    )
    parser.add_argument("--load", action="store_true", help="Load Silver into migrated database")
    parser.add_argument(
        "--index", action="store_true", help="Also index logs in OpenSearch (requires --load)"
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.index and not args.load:
        parser.error("--index requires --load")
    if args.input and (not args.sha256 or args.dataset == "all"):
        parser.error("--input requires a single dataset and --sha256")
    manifest = catalog(args.manifest)
    if args.dataset != "all" and args.dataset not in manifest["datasets"]:
        parser.error("unknown dataset")
    configure_logging()
    datasets = list(manifest["datasets"]) if args.dataset == "all" else [args.dataset]

    async def run() -> None:
        settings = Settings()
        engine = make_engine(settings.database_url)
        auth = (
            (settings.opensearch_username, settings.opensearch_password.get_secret_value())
            if settings.opensearch_username and settings.opensearch_password
            else None
        )
        try:
            async with httpx.AsyncClient(
                base_url=settings.opensearch_url, timeout=settings.request_timeout, auth=auth
            ) as client:
                search = OpenSearch(client) if args.index else None
                for dataset in datasets:
                    path = args.input or await asyncio.to_thread(
                        acquire, dataset, args.root, manifest
                    )
                    if args.input and sha256_file(path) != args.sha256:
                        raise ValueError("local input checksum differs from --sha256")
                    result = await asyncio.to_thread(
                        process,
                        dataset,
                        path,
                        args.root,
                        manifest["datasets"][dataset],
                        None if args.full else args.limit,
                        args.timezone,
                    )
                    if args.load:
                        result["loaded"] = await load_silver(
                            Path(result["silver_path"]), session_factory(engine), search
                        )
                    print(json.dumps(result))
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
