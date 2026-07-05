"""Build the versioned calibration target set defined in
`docs/calibration_targets.md`.

Every number here is a pure function of the warehouse plus this module's
code -- no target is hand-edited after generation. `build_target_set`
assembles the full set; `save_target_set` writes it as a content-addressed,
timestamped JSON file so that a later "which target set did the synthetic
cohort calibrate against" question always has a concrete answer (see the
docstring on `save_target_set`).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from equitylens_calibration.models import (
    EnrolmentShareTarget,
    RateTarget,
    SeifaDecileTarget,
    ToleranceTier,
)

TARGET_VERSION = "v1"
REFERENCE_YEAR = 2023

# N-dependent tolerance tiers for Section 16 retention/success rate targets
# (docs/calibration_targets.md, target family 2). A flat tolerance is not
# meaningful when the underlying commencing count is a handful of students --
# see that document for the reasoning.
_TOLERANCE_TIERS = (
    ToleranceTier("n>=200", 2.0),
    ToleranceTier("50<=n<200", 4.0),
    ToleranceTier("10<=n<50", 8.0),
    ToleranceTier("n<10_or_suppressed", None),
)

ENROLMENT_SHARE_TOLERANCE_PP = 1.0
SEIFA_TOLERANCE_PP = 2.0


def assign_tolerance_tier(n: float | None, *, suppressed: bool) -> ToleranceTier:
    """Return the tolerance tier for a given commencing-count denominator."""

    if suppressed or n is None or n < 10:
        return _TOLERANCE_TIERS[3]
    if n < 50:
        return _TOLERANCE_TIERS[2]
    if n < 200:
        return _TOLERANCE_TIERS[1]
    return _TOLERANCE_TIERS[0]


def compute_enrolment_share_targets(
    connection: duckdb.DuckDBPyConnection, reference_year: int
) -> list[EnrolmentShareTarget]:
    """Section 11 equity-group enrolment share, one target per
    institution x equity_group, imputed from the sector average share when a
    cell is suppressed."""

    base_rows = connection.execute(
        """
        SELECT institution_id, value FROM fact_enrolment_equity
        WHERE year_value = ? AND equity_group_id = 'all_students' AND value IS NOT NULL
        """,
        [reference_year],
    ).fetchall()
    all_students_by_institution = dict(base_rows)

    rows = connection.execute(
        """
        SELECT institution_id, equity_group_id, value, suppressed_flag
        FROM fact_enrolment_equity
        WHERE year_value = ? AND equity_group_id != 'all_students'
        """,
        [reference_year],
    ).fetchall()

    shares: dict[tuple[str, str], float] = {}
    for institution_id, equity_group_id, value, _suppressed in rows:
        all_students = all_students_by_institution.get(institution_id)
        if value is None or all_students in (None, 0):
            continue
        shares[(institution_id, equity_group_id)] = value / all_students * 100

    sector_average_share: dict[str, float] = {}
    by_group: dict[str, list[float]] = {}
    for (_institution_id, equity_group_id), share_pct in shares.items():
        by_group.setdefault(equity_group_id, []).append(share_pct)
    for equity_group_id, values in by_group.items():
        sector_average_share[equity_group_id] = sum(values) / len(values)

    targets: list[EnrolmentShareTarget] = []
    for institution_id, equity_group_id, value, suppressed in rows:
        all_students = all_students_by_institution.get(institution_id)
        if all_students in (None, 0):
            continue
        key = (institution_id, equity_group_id)
        imputed = value is None or suppressed
        if imputed:
            share_pct = sector_average_share.get(equity_group_id)
            imputation_source = f"sector_average_share_{reference_year}"
            if share_pct is None:
                continue
            count = round(share_pct / 100 * all_students, 1)
        else:
            share_pct = shares[key]
            count = value
            imputation_source = None
        targets.append(
            EnrolmentShareTarget(
                institution_id=institution_id,
                equity_group_id=equity_group_id,
                count=count,
                all_students=all_students,
                share_pct=round(share_pct, 2),
                tolerance_pp=ENROLMENT_SHARE_TOLERANCE_PP,
                imputed_target_flag=imputed,
                imputation_source=imputation_source,
            )
        )
    return targets


def compute_rate_targets(
    connection: duckdb.DuckDBPyConnection, reference_year: int, metric: str
) -> list[RateTarget]:
    """Section 16 retention_rate/success_rate target, one per
    institution x equity_group, with N-dependent tolerance and sector-average
    imputation for suppressed cells."""

    rows = connection.execute(
        """
        SELECT
            r.institution_id, r.equity_group_id, r.value, r.suppressed_flag,
            n.value AS n_count, n.suppressed_flag AS n_suppressed
        FROM fact_equity_performance r
        LEFT JOIN fact_equity_performance n
          ON n.institution_id = r.institution_id
         AND n.year_value = r.year_value
         AND n.equity_group_id = r.equity_group_id
         AND n.metric = 'access_numbers'
        WHERE r.year_value = ? AND r.metric = ? AND r.equity_group_id != 'all_domestic'
        """,
        [reference_year, metric],
    ).fetchall()

    sector_average: dict[str, float] = {}
    by_group: dict[str, list[float]] = {}
    for _institution_id, equity_group_id, value, suppressed, _n, _n_suppressed in rows:
        if value is not None and not suppressed:
            by_group.setdefault(equity_group_id, []).append(value)
    for equity_group_id, values in by_group.items():
        sector_average[equity_group_id] = sum(values) / len(values)

    targets: list[RateTarget] = []
    for institution_id, equity_group_id, value, suppressed, n_count, n_suppressed in rows:
        imputed = value is None or suppressed
        n_known = None if (n_count is None or n_suppressed) else n_count
        tier = assign_tolerance_tier(n_known, suppressed=(n_count is None or bool(n_suppressed)))

        if imputed:
            resolved_value = sector_average.get(equity_group_id)
            imputation_source = f"sector_average_{metric}_{reference_year}"
            if resolved_value is None:
                continue
        else:
            resolved_value = value
            imputation_source = None

        targets.append(
            RateTarget(
                institution_id=institution_id,
                equity_group_id=equity_group_id,
                metric=metric,
                value=round(resolved_value, 2),
                n=n_known,
                tolerance_tier=tier.name,
                tolerance_pp=tier.tolerance_pp,
                imputed_target_flag=imputed,
                imputation_source=imputation_source,
            )
        )
    return targets


def compute_seifa_targets(connection: duckdb.DuckDBPyConnection) -> list[SeifaDecileTarget]:
    """National, population-weighted SEIFA (IEO) decile share -- the
    geographic/socioeconomic calibration layer, independent of institution
    or reference year (SEIFA is quinquennial)."""

    rows = connection.execute(
        """
        SELECT decile, SUM(usual_resident_population) AS population
        FROM fact_seifa
        WHERE geo_level = 'poa' AND is_low_ses_calibration_target = TRUE AND decile IS NOT NULL
        GROUP BY decile
        ORDER BY decile
        """
    ).fetchall()
    total_population = sum(population for _decile, population in rows)
    return [
        SeifaDecileTarget(
            decile=decile,
            population=int(population),
            share_pct=round(population / total_population * 100, 2),
            tolerance_pp=SEIFA_TOLERANCE_PP,
        )
        for decile, population in rows
    ]


def _warehouse_sha256(warehouse_path: Path) -> str:
    digest = hashlib.sha256()
    with warehouse_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def build_target_set(
    warehouse_path: Path,
    *,
    reference_year: int = REFERENCE_YEAR,
    project_root: Path | None = None,
) -> dict:
    """Query the warehouse and assemble the full versioned target set."""

    connection = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        enrolment_share = compute_enrolment_share_targets(connection, reference_year)
        retention = compute_rate_targets(connection, reference_year, "retention_rate")
        success = compute_rate_targets(connection, reference_year, "success_rate")
        seifa = compute_seifa_targets(connection)
    finally:
        connection.close()

    root = project_root or warehouse_path.parent.parent.parent
    return {
        "target_version": TARGET_VERSION,
        "reference_year": reference_year,
        "generated_at": datetime.now(UTC).isoformat(),
        "warehouse_path": str(warehouse_path),
        "warehouse_sha256": _warehouse_sha256(warehouse_path),
        "git_commit": _current_git_commit(root),
        "targets": {
            "enrolment_share": [t.to_dict() for t in enrolment_share],
            "retention_rate": [t.to_dict() for t in retention],
            "success_rate": [t.to_dict() for t in success],
            "seifa_decile_share": [t.to_dict() for t in seifa],
        },
    }


def save_target_set(target_set: dict, output_dir: Path) -> Path:
    """Write the target set as an immutable, versioned JSON file.

    The filename encodes the target version and reference year
    (`targets_v1_2023ref.json`); the file content additionally embeds a
    generation timestamp, the warehouse's own SHA-256, and the git commit of
    the code that produced it. This is the full chain a later "what did the
    synthetic cohort calibrate against" question needs: the warehouse hash
    proves which data snapshot was used, the git commit proves which
    extraction/target logic was used, and the timestamp orders repeated runs
    against the same warehouse. A previous run is never overwritten silently:
    if a file with the same name already exists and its content differs, a
    numeric suffix is added rather than replacing it.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"targets_{target_set['target_version']}_{target_set['reference_year']}ref.json"
    candidate = output_dir / base_name
    serialized = json.dumps(target_set, indent=2, sort_keys=True)

    suffix = 0
    while candidate.exists():
        if candidate.read_text(encoding="utf-8") == serialized:
            return candidate  # identical content already saved, nothing to do
        suffix += 1
        candidate = output_dir / base_name.replace(".json", f".{suffix}.json")

    candidate.write_text(serialized, encoding="utf-8")
    return candidate
