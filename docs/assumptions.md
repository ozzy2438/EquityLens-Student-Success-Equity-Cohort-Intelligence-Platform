# Phase 3, Step 2c -- Literature-sourced assumptions

## Purpose

`docs/calibration_targets.md` defines every target pulled directly from a
published DoE/ABS/QILT marginal. This document is the opposite: every value
here is **not** observable in this project's warehouse and had to come from
an external source instead. It exists so that "which assumption drove this
synthetic-cohort result" always has a traceable answer, and so that a wrong
or superseded assumption can be found and revised without re-deriving the
whole calibration.

Format: assumption | value | source | scope | sensitivity note.

## Assumptions

| Assumption | Value | Source | Scope | Sensitivity note |
| --- | --- | --- | --- | --- |
| First-in-family (FiF) share of commencing domestic students | **50%** (working value; literature range found is 50-70%) | Converging estimates from two independent sources: ACSES, *Investigating the relationships between First-in-Family status, equity groups, and university access* (Zajac et al., 2025) -- FiF constitute "over two-thirds" of the broader population but are ~23 percentage points less likely to enrol than non-FiF, implying a materially lower enrolled/commencing share than two-thirds; and general Australian higher-education literature (O'Shea et al., 2023, as cited in secondary reporting) putting FiF at "over 50%" of higher education students nationally, with some institutions anecdotally reporting up to ~70%. No DoE Selected Higher Education Statistics table reports first-in-family status -- it is not an official Australian equity group, unlike Low SES, First Nations, disability, regional/remote, and NESB, all of which are observed directly in Sections 11/16. | Applied as an **independent** Bernoulli draw per synthetic student (not raked jointly with geography/low-SES/first-nations -- see "Independent vs. joint attributes" below), institution-agnostic (no ACU-specific FiF figure exists in the literature found). | If Phase 4's risk model finds FiF status carrying disproportionate predictive weight, this is the single assumption most likely to need revisiting -- the true value could plausibly be anywhere in the cited 50-70% range, a 20-point spread, and no ACU-specific or DoE-published figure exists to narrow it further. Revisit by searching for an ACU-specific FiF figure (student equity plans, TEQSA equity data) before trusting a Phase 4 finding that leans heavily on this feature. |
| Pairwise equity-group correlation (Low SES x Regional/Remote x First Nations) used to shape the IPF seed table | Lift factors (co-occurrence relative to independence): Low SES x Regional/Remote = **0.82**, First Nations x Regional/Remote = **0.80**, First Nations x Low SES = **0.79** (all three below 1.0 -- see sensitivity note) | Directly computed from DoE Section 11 2024, **Table 11.9: All Domestic and Domestic Undergraduate Students by Equity Group Intersectionality**: diagonal (single-group) counts First Nations=24,561, Low SES by SA1=165,883, Regional and Remote=193,669; pairwise counts First Nations x Low SES=8,491, First Nations x Regional/Remote=10,051, Low SES x Regional/Remote=69,850; national denominator N=378,395 (sum of 2024 commencing-domestic counts across the 43 Table A/B institutions in this warehouse). Lift = (pairwise count / N) / ((count_A / N) x (count_B / N)). | Used only to shape the *seed table's* relative cell weights before raking (`population.build_seed_table`) -- a uniform seed would make IPF converge to the pure-independence solution regardless of how correlated the real population actually is, which would make the raked population statistically indistinguishable from the deliberately-wrong Step 2a baseline. This is a national, all-domestic-students (not commencing-only, not ACU-specific) figure applied as an approximation for ACU's commencing cohort. | **This finding is counter-intuitive and disclosed as such, not smoothed over**: lift factors below 1.0 mean these three equity groups co-occur *less* than chance would predict nationally, not more, contradicting the naive assumption that equity disadvantage compounds. Three caveats limit how far to trust this for calibration: (1) Table 11.9 mixes all currently-enrolled students, not just commencing students, and captures pairwise (not three-way) intersections only, per its own footnote (5.12); (2) "Regional and Remote" here is DoE's national classification and is not decomposed into ACU's separate `regional`/`remote` geography levels, so the same lift is applied to both; (3) **the sub-1.0 lift may be partly or wholly a definitional artifact, not a real sociological pattern, and this data cannot distinguish the two**: Low SES is measured by postcode/SA1 residential geocoding while Regional/Remote is measured by first-address ASGS remoteness -- these use different geographic units built from different boundary systems, and Australia's outer-metropolitan Low SES concentration (large, denser, lower-SEIFA-decile postcodes ringing capital cities) mechanically dilutes overlap with the Regional/Remote classification regardless of any true underlying correlation between socioeconomic disadvantage and geographic remoteness. If a future DoE release publishes a genuine three-way or commencing-specific intersectionality table, replace these derived lifts rather than adjust them by hand. |

No other assumption was needed for this phase: every other attribute in the
synthetic population (equity-group membership, geography, SEIFA decile) has
a directly observed DoE/ABS marginal in `docs/calibration_targets.md`, and
part-time status was deliberately excluded from scope entirely (same
document) rather than assumed.

## Independent vs. joint (raked) attributes

Not every attribute in the synthetic population goes through the same
correlation treatment, and which path an attribute takes is a modelling
decision made once, here, rather than re-litigated per attribute in code:

- **Jointly raked** (`raking.rake()`, IPF against Section 11/ABS marginals):
  `geography` (metro/regional/remote), `low_ses_sa1`, `first_nations`,
  `seifa_decile`. These four are raked together because the calibration
  target contract calls out their correlation as something to preserve, and
  all four have directly observed national/institution marginals to rake
  against. Critically, the **seed table these are raked from is not
  uniform** -- a uniform seed has no correlation structure to preserve, and
  IPF from a flat seed provably converges to the pure-independence solution
  regardless of how correlated the real population is, which would make
  this population statistically indistinguishable from the deliberately
  wrong Step 2a baseline despite the extra machinery. The seed is instead
  shaped by the Table 11.9 lift factors immediately below, so raking adjusts
  *totals* to match ACU's marginals while approximately preserving the
  *shape* of the real, nationally-observed correlation between these
  attributes (IPF's minimum-discrimination-information property).
- **Independent Bernoulli draws, applied after raking**: `disability`,
  `non_english_speaking_background`, `women_non_traditional_area`,
  `first_in_family`. These are drawn independently of the raked joint
  distribution and of each other. This is a disclosed scope simplification,
  not an oversight: including all seven-plus binary/categorical attributes
  in one joint raking table would multiply the cell count into the
  thousands for a ~20K-student population (many cells with expected count
  under 1), risking exactly the sparse-cell convergence problems
  `docs/calibration_targets.md`'s N-dependent tolerance tiers were designed
  to guard against, for attributes the target contract's own worked example
  does not name as a correlation to preserve. If Phase 4 modelling finds a
  materially wrong joint distribution for one of these four (e.g. disability
  x low-SES), promoting it into the raked table is a config change to
  `population.py`'s dimension list, not a redesign.

## A rule this document exists to enforce

Per Step 2's plan: the correlation layer here is calibrated to be
**realistic**, not to hit any particular downstream discriminative-power
target. Signal strength for Phase 4's risk model (targeted AUC ~0.75-0.85)
is a Step 3 (outcome assignment) concern, tuned there, separately, once
outcomes are attached to students. Mixing the two -- reverse-engineering
this correlation layer to produce a specific AUC -- would make it impossible
to tell, later, whether a Phase 4 result reflects the real equity-gap
structure in the data or an assumption quietly reshaped to produce it.
