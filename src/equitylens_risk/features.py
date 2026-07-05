"""Phase 4a: leakage-safe feature construction for the Semester-1-census
risk model (`docs/model_design.md`).

Two responsibilities live here, both existing *because* of the leakage risk
`docs/model_design.md` documents: generating a genuinely census-dated
behavioural signal (Step 3c only ever produced a full first-year aggregate,
which is not available at census date for a student who has already left),
and selecting, by an explicit allow-list rather than an exclude-list, only
the columns that are legitimately known at the census-date decision point.
An allow-list is deliberate: a new column added to the synthetic population
later (e.g. a future full-year signal) must be explicitly reviewed and added
here to become a feature, rather than silently flowing into the model the
way an exclude-list would let it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_CENSUS_CONNECTION_STRENGTH = 0.4
DEFAULT_CENSUS_SIGMA = 1.0

# Columns known at Semester-1 census date (docs/model_design.md's feature
# inventory table): fixed-at-enrolment demographic/equity attributes plus
# the census-dated behavioural signal generated below. Anything derived from
# the outcome-generating process itself (`retention_probability`) or from a
# full first-year aggregate (`success_rate_realized`, `units_passed_eftsl`)
# is deliberately not in this list.
CENSUS_FEATURE_COLUMNS = (
    "geography",
    "low_ses",
    "first_nations",
    "disability",
    "non_english_speaking_background",
    "women_non_traditional_area",
    "first_in_family",
    "seifa_decile",
    "census_engagement_score",
)


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1 / (1 + np.exp(-x))


def generate_census_engagement_signal(
    population: pd.DataFrame,
    shared_latent_risk: np.ndarray,
    *,
    connection_strength: float = DEFAULT_CENSUS_CONNECTION_STRENGTH,
    sigma: float = DEFAULT_CENSUS_SIGMA,
    seed: int = 900,
) -> pd.Series:
    """A census-date behavioural proxy (e.g. attendance / an early formative
    assessment), sharing `shared_latent_risk` with the retention and success
    outcomes -- the same one-factor mechanism as
    `outcomes._combined_noise` -- but through a deliberately weaker
    `connection_strength` than the full-year success signal's, and its own
    independent idiosyncratic noise draw. A few weeks of census-date
    information is real but structurally noisier and less complete than a
    full year's academic record; this signal is built to reflect that,
    rather than reusing the full-year signal's own connection strength.

    Returned as a [0, 1] continuous score (not thresholded), matching
    `success_rate_realized`'s convention, via the standard logit/sigmoid
    link so it stays population-mean-neutral rather than favouring a
    particular class by construction.
    """

    n = len(population)
    rng = np.random.default_rng(seed)
    idiosyncratic = rng.standard_normal(n)
    combined = (
        np.sqrt(connection_strength) * shared_latent_risk
        + np.sqrt(1 - connection_strength) * idiosyncratic
    ) * sigma
    return pd.Series(_sigmoid(combined), index=population.index, name="census_engagement_score")


def build_census_feature_table(population: pd.DataFrame) -> pd.DataFrame:
    """Select the census-date-safe feature columns by explicit allow-list
    (`CENSUS_FEATURE_COLUMNS`) -- raises if a required column is missing
    rather than silently producing a smaller feature set, since a Phase 4
    model silently trained on fewer features than intended is a worse
    failure mode than a loud one.
    """

    missing = [column for column in CENSUS_FEATURE_COLUMNS if column not in population.columns]
    if missing:
        raise ValueError(
            f"population is missing required census feature columns: {missing}. "
            "Call generate_census_engagement_signal first if 'census_engagement_score' "
            "is the one missing."
        )
    return population[list(CENSUS_FEATURE_COLUMNS)].copy()
