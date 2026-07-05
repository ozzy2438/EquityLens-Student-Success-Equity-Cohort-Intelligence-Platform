"""Synthetic commencing-student population generation.

Two population builders exist side by side deliberately, not just for
history's sake:

- `build_baseline_population` (Step 2a) samples every attribute
  *independently* -- no correlation between Low SES, regional/remote, First
  Nations, and SEIFA decile. This is intentionally wrong: equity attributes
  are known to co-occur far more than independent sampling would produce,
  and comparing this baseline against the raked population (Step 2c) is the
  clearest evidence that raking earns its complexity.
- `build_raked_population` (Step 2c) jointly rakes those four attributes
  against the Section 11/ABS marginals in a calibration target set, via
  `raking.rake`. Weaker or unobserved attributes (disability, NESB, women in
  non-traditional areas, first-in-family) are layered on independently
  afterwards -- see `docs/assumptions.md`, "Independent vs. joint
  attributes," for why those four specifically were not folded into the
  raked table.

Both builders return individual-student rows, not cell weights, so `Step 3`
(outcome assignment) can work with one student per row regardless of which
population it was given.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from equitylens_synthetic.models import ConvergenceReport, IntegerizationReport
from equitylens_synthetic.raking import Margins, integerize, rake

GEOGRAPHY_LEVELS = ("metro", "regional", "remote")
SEIFA_DECILE_LEVELS = tuple(range(1, 11))

# docs/assumptions.md: no DoE table observes first-in-family status, so this
# is a literature-sourced constant, not a warehouse target.
FIRST_IN_FAMILY_SHARE_PCT = 50.0

_INDEPENDENT_EQUITY_GROUPS = {
    "disability": "disability",
    "non_english_speaking_background": "non_english_speaking_background",
    "women_non_traditional_area": "women_non_traditional_area",
}


def load_target_set(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _institution_enrolment_shares(target_set: dict, institution_id: str) -> dict[str, dict]:
    return {
        t["equity_group_id"]: t
        for t in target_set["targets"]["enrolment_share"]
        if t["institution_id"] == institution_id
    }


def _shares_to_exact_counts(shares_pct: dict[str, float], total: int) -> dict[str, int]:
    """Largest-remainder rounding so counts sum exactly to `total` -- the same
    method as `raking.integerize`, applied here to build IPF margin totals
    that are internally consistent across dimensions (a precondition for
    clean convergence, not just a cosmetic choice)."""

    scaled = {level: share / 100 * total for level, share in shares_pct.items()}
    floors = {level: int(value // 1) for level, value in scaled.items()}
    remainder_budget = total - sum(floors.values())
    remainders = sorted(scaled, key=lambda level: scaled[level] - floors[level], reverse=True)
    counts = dict(floors)
    for level in remainders[:remainder_budget]:
        counts[level] += 1
    return counts


def build_geography_margin(target_set: dict, institution_id: str, total: int) -> dict[str, int]:
    shares = _institution_enrolment_shares(target_set, institution_id)
    regional_pct = shares["regional"]["share_pct"]
    remote_pct = shares["remote"]["share_pct"]
    metro_pct = 100.0 - regional_pct - remote_pct
    return _shares_to_exact_counts(
        {"metro": metro_pct, "regional": regional_pct, "remote": remote_pct}, total
    )


def build_binary_margin(
    target_set: dict, institution_id: str, equity_group_id: str, total: int
) -> dict[str, int]:
    shares = _institution_enrolment_shares(target_set, institution_id)
    yes_pct = shares[equity_group_id]["share_pct"]
    return _shares_to_exact_counts({"yes": yes_pct, "no": 100.0 - yes_pct}, total)


def build_seifa_margin(target_set: dict, total: int) -> dict[int, int]:
    shares_pct = {t["decile"]: t["share_pct"] for t in target_set["targets"]["seifa_decile_share"]}
    counts = _shares_to_exact_counts({str(k): v for k, v in shares_pct.items()}, total)
    return {int(level): count for level, count in counts.items()}


# Pairwise co-occurrence lift factors (co-occurrence relative to what
# independence would predict), derived from DoE Section 11 2024 Table 11.9
# ("All Domestic and Domestic Undergraduate Students by Equity Group
# Intersectionality") -- see docs/assumptions.md for the full derivation,
# raw counts, and the caveats on using a national, all-students (not
# commencing-only) table as a proxy for ACU's commencing cohort. All three
# are below 1.0: these equity groups co-occur *less* than chance nationally,
# not more -- a genuinely counter-intuitive finding, kept as found rather
# than adjusted toward an assumed positive correlation.
LIFT_LOW_SES_REGIONAL_REMOTE = 0.82
LIFT_FIRST_NATIONS_REGIONAL_REMOTE = 0.80
LIFT_FIRST_NATIONS_LOW_SES = 0.79


def build_seed_table() -> pd.DataFrame:
    """Cross product of the four jointly-raked dimensions, with cell weights
    shaped by the Table 11.9 lift factors above rather than left uniform.

    A uniform seed has no correlation structure for IPF to preserve: raking
    a flat table to independent 1-D marginals provably converges to the
    pure-independence joint distribution, no matter how correlated the real
    population is. Shaping the seed first means raking instead adjusts
    *totals* to match ACU's marginals while approximately preserving the
    *relative* co-occurrence structure observed nationally.
    """

    rows = [
        {
            "geography": geo,
            "low_ses": low_ses,
            "first_nations": first_nations,
            "seifa_decile": decile,
        }
        for geo in GEOGRAPHY_LEVELS
        for low_ses in ("yes", "no")
        for first_nations in ("yes", "no")
        for decile in SEIFA_DECILE_LEVELS
    ]
    table = pd.DataFrame(rows)

    is_regional_remote = table["geography"].isin(("regional", "remote"))
    is_low_ses = table["low_ses"] == "yes"
    is_first_nations = table["first_nations"] == "yes"

    weight = pd.Series(1.0, index=table.index)
    weight = weight.where(~(is_low_ses & is_regional_remote), weight * LIFT_LOW_SES_REGIONAL_REMOTE)
    weight = weight.where(
        ~(is_first_nations & is_regional_remote), weight * LIFT_FIRST_NATIONS_REGIONAL_REMOTE
    )
    weight = weight.where(~(is_first_nations & is_low_ses), weight * LIFT_FIRST_NATIONS_LOW_SES)
    table["weight"] = weight
    return table


def _apply_independent_attributes(
    population: pd.DataFrame, target_set: dict, institution_id: str, rng: np.random.Generator
) -> pd.DataFrame:
    shares = _institution_enrolment_shares(target_set, institution_id)
    n = len(population)
    for column, equity_group_id in _INDEPENDENT_EQUITY_GROUPS.items():
        share_pct = shares[equity_group_id]["share_pct"]
        population[column] = rng.random(n) < (share_pct / 100)
    population["first_in_family"] = rng.random(n) < (FIRST_IN_FAMILY_SHARE_PCT / 100)
    return population


def build_baseline_population(
    target_set: dict,
    n_students: int,
    *,
    institution_id: str = "acu",
    seed: int = 42,
) -> pd.DataFrame:
    """Step 2a: independent-marginal baseline, deliberately uncorrelated."""

    rng = np.random.default_rng(seed)
    shares = _institution_enrolment_shares(target_set, institution_id)

    regional_pct = shares["regional"]["share_pct"]
    remote_pct = shares["remote"]["share_pct"]
    geography_p = [100.0 - regional_pct - remote_pct, regional_pct, remote_pct]
    geography_p = [p / 100 for p in geography_p]

    seifa_shares = {
        t["decile"]: t["share_pct"] for t in target_set["targets"]["seifa_decile_share"]
    }
    seifa_p = [seifa_shares[d] / 100 for d in SEIFA_DECILE_LEVELS]

    population = pd.DataFrame(
        {
            "student_id": range(1, n_students + 1),
            "institution_id": institution_id,
            "geography": rng.choice(GEOGRAPHY_LEVELS, size=n_students, p=geography_p),
            "low_ses": rng.random(n_students) < (shares["low_ses_sa1"]["share_pct"] / 100),
            "first_nations": rng.random(n_students) < (shares["first_nations"]["share_pct"] / 100),
            "seifa_decile": rng.choice(SEIFA_DECILE_LEVELS, size=n_students, p=seifa_p),
        }
    )
    return _apply_independent_attributes(population, target_set, institution_id, rng)


def _seed_implied_count(seed_table: pd.DataFrame, dimension: str, level: str, total: int) -> float:
    """The count a dimension level would get if raking left it entirely to
    the seed's own relative weight -- used as its target when a publisher
    value is imputed and `include_imputed=False`, so that dimension's
    margin still sums to `total` (required for cross-dimension consistency)
    without forcing the untrusted imputed institution value."""

    share = (
        seed_table.loc[seed_table[dimension] == level, "weight"].sum() / seed_table["weight"].sum()
    )
    return share * total


def build_raked_population(
    target_set: dict,
    n_students: int,
    *,
    institution_id: str = "acu",
    include_imputed: bool = True,
    tolerance: float = 0.001,
    max_iter: int = 50,
    seed: int = 42,
) -> tuple[pd.DataFrame, ConvergenceReport, IntegerizationReport]:
    """Step 2c: jointly rake geography x low_ses x first_nations x
    seifa_decile against the target set, then layer independent attributes
    on top (see module docstring and docs/assumptions.md).

    When `include_imputed=False` and a level's institution target came from
    sector-average imputation (`imputed_target_flag` in
    `docs/calibration_targets.md`), that level's margin is replaced with the
    count the seed table's own relative weight would imply, rather than
    dropped from the margin dict outright. Dropping it entirely would leave
    that level totally unconstrained while every other dimension still
    targets the full `n_students`, an internally inconsistent margin set
    that starves raking of a coherent target and degrades convergence for a
    reason that has nothing to do with the real data -- exactly the kind of
    self-inflicted non-convergence `docs/calibration_targets.md` warns
    against confusing with a genuine conflicting-marginals finding.
    """

    rng = np.random.default_rng(seed)
    shares = _institution_enrolment_shares(target_set, institution_id)
    seed_table = build_seed_table()
    seed_table["seifa_decile"] = seed_table["seifa_decile"].astype(str)

    def _resolved_count(
        dimension: str, level: str, equity_group_id: str, observed_count: float
    ) -> float:
        if not include_imputed and shares[equity_group_id]["imputed_target_flag"]:
            return _seed_implied_count(seed_table, dimension, level, n_students)
        return observed_count

    geography_margin = build_geography_margin(target_set, institution_id, n_students)
    geography_margin["regional"] = _resolved_count(
        "geography", "regional", "regional", geography_margin["regional"]
    )
    geography_margin["remote"] = _resolved_count(
        "geography", "remote", "remote", geography_margin["remote"]
    )
    geography_margin["metro"] = (
        n_students - geography_margin["regional"] - geography_margin["remote"]
    )

    low_ses_margin = build_binary_margin(target_set, institution_id, "low_ses_sa1", n_students)
    low_ses_margin["yes"] = _resolved_count("low_ses", "yes", "low_ses_sa1", low_ses_margin["yes"])
    low_ses_margin["no"] = n_students - low_ses_margin["yes"]

    first_nations_margin = build_binary_margin(
        target_set, institution_id, "first_nations", n_students
    )
    first_nations_margin["yes"] = _resolved_count(
        "first_nations", "yes", "first_nations", first_nations_margin["yes"]
    )
    first_nations_margin["no"] = n_students - first_nations_margin["yes"]

    seifa_margin = build_seifa_margin(target_set, n_students)

    margins: Margins = {
        "geography": {k: float(v) for k, v in geography_margin.items()},
        "low_ses": {k: float(v) for k, v in low_ses_margin.items()},
        "first_nations": {k: float(v) for k, v in first_nations_margin.items()},
        "seifa_decile": {str(k): float(v) for k, v in seifa_margin.items()},
    }

    weights, convergence = rake(seed_table, margins, tolerance=tolerance, max_iter=max_iter)
    counts, integerization = integerize(
        seed_table, weights, total_students=n_students, margins=margins
    )

    exploded_rows = seed_table.loc[seed_table.index.repeat(counts)].reset_index(drop=True)
    exploded_rows["seifa_decile"] = exploded_rows["seifa_decile"].astype(int)
    # Match build_baseline_population's dtypes exactly (bool, not "yes"/"no"
    # strings) so the two population builders are interchangeable for any
    # downstream comparison code -- an earlier version left these as the raw
    # seed-table strings, which crashed the very before/after joint-
    # correlation comparison this population exists to support.
    exploded_rows["low_ses"] = exploded_rows["low_ses"] == "yes"
    exploded_rows["first_nations"] = exploded_rows["first_nations"] == "yes"
    exploded_rows.insert(0, "student_id", range(1, len(exploded_rows) + 1))
    exploded_rows.insert(1, "institution_id", institution_id)
    exploded_rows = exploded_rows.drop(columns="weight")

    population = _apply_independent_attributes(exploded_rows, target_set, institution_id, rng)
    return population, convergence, integerization


def compare_marginals(
    population: pd.DataFrame, target_set: dict, institution_id: str = "acu"
) -> pd.DataFrame:
    """Actual vs. target share per raked attribute -- the before/after table
    for Step 2's validation comparison."""

    shares = _institution_enrolment_shares(target_set, institution_id)
    n = len(population)
    rows = []

    for level in GEOGRAPHY_LEVELS:
        actual_pct = (population["geography"] == level).sum() / n * 100
        if level == "metro":
            target_pct = 100.0 - shares["regional"]["share_pct"] - shares["remote"]["share_pct"]
        else:
            target_pct = shares[level]["share_pct"]
        rows.append(_comparison_row("geography", level, target_pct, actual_pct))

    for column, equity_group_id in (("low_ses", "low_ses_sa1"), ("first_nations", "first_nations")):
        actual_pct = population[column].sum() / n * 100
        rows.append(
            _comparison_row(column, "yes", shares[equity_group_id]["share_pct"], actual_pct)
        )

    seifa_targets = {
        t["decile"]: t["share_pct"] for t in target_set["targets"]["seifa_decile_share"]
    }
    for decile in SEIFA_DECILE_LEVELS:
        actual_pct = (population["seifa_decile"] == decile).sum() / n * 100
        rows.append(_comparison_row("seifa_decile", str(decile), seifa_targets[decile], actual_pct))

    return pd.DataFrame(rows)


def _comparison_row(dimension: str, level: str, target_pct: float, actual_pct: float) -> dict:
    return {
        "dimension": dimension,
        "level": level,
        "target_pct": round(target_pct, 2),
        "actual_pct": round(actual_pct, 2),
        "abs_diff_pp": round(abs(target_pct - actual_pct), 2),
    }
