"""Command-line interface for governed source selection and ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from equitylens_ingestion.errors import IngestionError
from equitylens_ingestion.logging import configure_logging
from equitylens_ingestion.registry import load_registry, select_sources
from equitylens_ingestion.service import IngestionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="equitylens-ingest")
    parser.add_argument("--config", type=Path, default=Path("config/sources.yml"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="ingest active sources")
    ingest.add_argument("--all", action="store_true", help="ingest every active source")
    ingest.add_argument("--publisher")
    ingest.add_argument("--section")
    ingest.add_argument("--year", type=int)
    ingest.add_argument("--include-inactive", action="store_true")

    list_command = subparsers.add_parser("list", help="list registry entries")
    list_command.add_argument("--publisher")
    list_command.add_argument("--section")
    list_command.add_argument("--year", type=int)
    list_command.add_argument("--include-inactive", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    try:
        sources = load_registry(args.config)
        selected = select_sources(
            sources,
            publisher=getattr(args, "publisher", None),
            section=getattr(args, "section", None),
            year=getattr(args, "year", None),
            include_inactive=getattr(args, "include_inactive", False),
        )
        if args.command == "list":
            for source in selected:
                print(
                    json.dumps(
                        {
                            "source_id": source.source_id,
                            "publisher": source.publisher,
                            "section": source.section,
                            "year": source.year,
                            "status": source.status,
                        },
                        sort_keys=True,
                    )
                )
            return 0

        if not selected:
            print("No sources matched the supplied filters", file=sys.stderr)
            return 2
        service = IngestionService(data_root=args.data_root)
        service.store.write_source_snapshot(sources)
        results = service.ingest_all(selected)
        print(json.dumps([asdict(result) for result in results], indent=2))
        return 1 if any(result.outcome == "failed" for result in results) else 0
    except IngestionError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
