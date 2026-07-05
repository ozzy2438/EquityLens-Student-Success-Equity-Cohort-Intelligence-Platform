"""Command-line interface for the synthetic population layer."""

from __future__ import annotations

import argparse
from pathlib import Path

from equitylens_synthetic.errors import SyntheticError
from equitylens_synthetic.population import (
    build_baseline_population,
    build_raked_population,
    compare_marginals,
    load_target_set,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="equitylens-synthesize")
    parser.add_argument("--targets", type=Path, required=True, help="calibration target set JSON")
    parser.add_argument("--institution-id", default="acu")
    parser.add_argument("--n-students", type=int, default=20000)
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--seed", type=int, default=42)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("baseline", help="Step 2a: independent-marginal baseline population")
    raked = subparsers.add_parser("raked", help="Step 2c: jointly raked population")
    raked.add_argument("--tolerance", type=float, default=0.001)
    raked.add_argument("--max-iter", type=int, default=50)
    raked.add_argument("--exclude-imputed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target_set = load_target_set(args.targets)
        if args.command == "baseline":
            return _build_baseline(args, target_set)
        if args.command == "raked":
            return _build_raked(args, target_set)
    except SyntheticError as exc:
        print(str(exc))
        return 2
    return 2


def _write(population, comparison, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    population.to_csv(output_dir / f"{name}_population.csv", index=False)
    comparison.to_csv(output_dir / f"{name}_marginal_comparison.csv", index=False)
    print(f"Wrote {len(population)} students to {output_dir / f'{name}_population.csv'}")
    print(comparison.to_string(index=False))
    print(f"Max abs deviation: {comparison['abs_diff_pp'].max():.2f}pp")


def _build_baseline(args: argparse.Namespace, target_set: dict) -> int:
    population = build_baseline_population(
        target_set, args.n_students, institution_id=args.institution_id, seed=args.seed
    )
    comparison = compare_marginals(population, target_set, args.institution_id)
    _write(population, comparison, args.output_dir, "baseline")
    return 0


def _build_raked(args: argparse.Namespace, target_set: dict) -> int:
    population, convergence, integerization = build_raked_population(
        target_set,
        args.n_students,
        institution_id=args.institution_id,
        include_imputed=not args.exclude_imputed,
        tolerance=args.tolerance,
        max_iter=args.max_iter,
        seed=args.seed,
    )
    comparison = compare_marginals(population, target_set, args.institution_id)
    _write(population, comparison, args.output_dir, "raked")
    print(f"Converged: {convergence.converged} in {convergence.iterations} iterations")
    if convergence.structural_zero_margins:
        print(f"Structural zero margins: {convergence.structural_zero_margins}")
    print(f"Post-integerization total students: {integerization.total_students}")
    return 0 if convergence.converged else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
