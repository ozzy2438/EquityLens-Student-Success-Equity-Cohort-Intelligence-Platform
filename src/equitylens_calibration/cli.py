"""Command-line interface for the calibration target layer."""

from __future__ import annotations

import argparse
from pathlib import Path

from equitylens_calibration.errors import CalibrationError
from equitylens_calibration.targets import REFERENCE_YEAR, build_target_set, save_target_set


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="equitylens-calibrate")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--warehouse", type=Path, default=Path("data/warehouse/equitylens.duckdb"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/calibration"))
    parser.add_argument("--reference-year", type=int, default=REFERENCE_YEAR)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("targets", help="build and save the versioned calibration target set")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "targets":
            return _targets(args)
    except CalibrationError as exc:
        print(str(exc))
        return 2
    return 2


def _targets(args: argparse.Namespace) -> int:
    target_set = build_target_set(
        args.warehouse, reference_year=args.reference_year, project_root=args.project_root
    )
    path = save_target_set(target_set, args.output_dir)
    counts = {name: len(rows) for name, rows in target_set["targets"].items()}
    print(f"Saved target set to {path}")
    print(f"Reference year: {target_set['reference_year']}")
    print(f"Warehouse sha256: {target_set['warehouse_sha256'][:12]}...")
    print(f"Git commit: {target_set['git_commit']}")
    for name, count in counts.items():
        print(f"  {name}: {count} targets")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
