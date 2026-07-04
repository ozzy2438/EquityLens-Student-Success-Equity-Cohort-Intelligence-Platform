"""Command-line interface for the normalization and warehouse layer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from equitylens_normalization.errors import NormalizationError
from equitylens_normalization.extraction_map import load_extraction_map
from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.reconciliation import run_all_checks
from equitylens_normalization.warehouse import build_warehouse, load_file_manifest, run_normalizers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="equitylens-normalize")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--extraction-map", type=Path, default=Path("config/extraction_map.yml"))
    parser.add_argument("--institution-map", type=Path, default=Path("config/institution_map.yml"))
    parser.add_argument("--warehouse", type=Path, default=Path("data/warehouse/equitylens.duckdb"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="normalize all sources and rebuild the DuckDB warehouse")
    subparsers.add_parser("reconcile", help="run cross-source reconciliation checks")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            return _build(args)
        if args.command == "reconcile":
            return _reconcile(args)
    except NormalizationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


def _build(args: argparse.Namespace) -> int:
    resolver = load_institution_map(args.institution_map)
    rules = load_extraction_map(args.extraction_map)
    manifest_by_source = load_file_manifest(args.data_root)
    records = run_normalizers(rules, manifest_by_source, resolver, project_root=args.project_root)
    loaded = build_warehouse(args.warehouse, records, resolver)
    print(
        f"Normalized {len(records)} records, loaded {loaded} after deduplication "
        f"into {args.warehouse}"
    )
    return 0


def _reconcile(args: argparse.Namespace) -> int:
    connection = duckdb.connect(str(args.warehouse), read_only=True)
    try:
        findings = run_all_checks(connection)
    finally:
        connection.close()
    for finding in findings:
        print(
            f"[{finding.severity}] {finding.check_name} "
            f"institution={finding.institution_id} year={finding.year_value}: {finding.message}"
        )
    print(f"{len(findings)} reconciliation findings")
    return 1 if any(finding.severity == "error" for finding in findings) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
