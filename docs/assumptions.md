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

## Step 3 finding: equity-group membership alone caps implied AUC at ~0.52

Checked directly rather than assumed, per the rule above: `outcomes.py`'s
retention-probability score, built purely from Section 16's institution x
equity-group rates via `compute_base_logit`, was checked against `sigma`
values spanning two orders of magnitude (1.0 down to 0.02) using
`outcomes.compute_auc`. **The implied AUC stays at ~0.52 (barely above
chance) across the entire range** -- confirming the ceiling comes from the
underlying signal being weak and sparse, not from individual noise
obscuring it: only ~32% of ACU's 2023 commencing students belong to *any*
of the four calibrated equity groups at all, and for three of those four
(`disability` 83.76%, `non_english_speaking_background` 84.32%, `regional`
81.77%) the group-specific retention rate sits close to or even above the
institution's overall 82.91% rate -- only `remote` (66.78%) and
`first_nations` (77.85%) show a meaningful gap, and both are small-N groups.
`sigma=1.0` was kept as `DEFAULT_SIGMA` since it does not materially change
this outcome either way.

**This is a real, disclosed limitation, not a defect to paper over**:
reaching Phase 4's 0.75-0.85 target band from this warehouse's data will
require genuine behavioural/engagement signals (units attempted/passed
performance in the first few weeks, LMS engagement, enrolment intensity --
exactly the "dönemsel sinyaller" the original Phase 3-4 project plan always
intended as *separate* features from demographic equity-group membership),
not a larger correlation or a smaller `sigma` applied to equity-group
membership alone. Demographic membership being a weak individual-level
predictor of retention, even where it tracks a real institutional equity
gap at the aggregate level, is also a well-established finding in the
student-retention literature generally -- consistent with, not contradicted
by, this result.

## Step 3d finding: `first_nations`'s realized retention rate is systematically, not randomly, off-target

Running post-outcome validation (`validate.py`) against the real target set
surfaced one gated check failing consistently: the population subset with
`first_nations=True` realizes a retention rate 4-5 percentage points *above*
its 77.85% target across every seed tried (78.4-83.1% across 5 seeds) --
this is a one-directional bias, not symmetric sampling noise (`remote`, by
contrast, scatters both above and below its target across seeds, consistent
with ordinary small-N variance at n~72).

**Mechanism, traced rather than left unexplained**: `population.py`'s Table
11.9 lift factors (`docs/assumptions.md` above) make `first_nations`
students in the raked population *less* likely than the general population
to also be `low_ses` or `regional`/`remote` (9.3% and 8.8% respectively,
vs. 12.0% and 11.6% overall). But DoE's own published 77.85% first_nations
retention figure is an empirical average over *real* first_nations students,
whatever fraction of them are actually also low_ses/regional in reality.
`outcomes.py`'s additive-in-logit model gives a student who is *only*
`first_nations` exactly the target logit; a student who is also `low_ses` or
`regional` gets an *additional* negative delta stacked on top. If the raked
population under-represents first_nations-and-also-disadvantaged students
relative to reality (which the lift factors say it does), fewer synthetic
first_nations students receive that stacking effect than real first_nations
students do, so the synthetic subgroup's average sits closer to the
"pure-group" logit than the target -- i.e., healthier than intended.

**This is disclosed as a real gap in the current approach, not fixed by
adjusting the lift factors to make this one number match.** Doing that would
be reverse-engineering a single validation check rather than correcting the
actual cause, and would raise exactly the question this whole project is
built around avoiding: is a result real, or was an assumption quietly
reshaped to produce it? The honest scope of the current limitation: Step 2's
seed only encodes *pairwise* lift factors between three attributes
(`low_ses`, `regional`/`remote`, `first_nations`) derived from a national,
not ACU-specific, table; Step 3's additive-logit outcome model then compounds
those same three attributes' effects. Any equity group whose synthetic
co-occurrence with the *other* raked attributes diverges from its true
co-occurrence will show this same directional bias on its own realized rate,
proportional to how large that divergence is -- `first_nations` shows it
most visibly here because it has the largest target-vs-base gap (77.85% vs
82.91%) of any of the three, so compounding errors move it the most. A more
faithful fix would require intersection-level outcome data to calibrate an
actual interaction term (which Section 16 does not publish, only Section
11's enrolment intersectionality does -- see `population.py`), not a change
to this document's lift factors.

## Outcome calibration anchors (fixes the `first_nations` finding above)

The fix implemented is exactly the one the finding above ruled out adjusting
the input for: a new **output-layer** calibration step, kept structurally
separate from Step 2's Table 11.9 lift factors, which remain untouched.
`outcomes.calibrate_anchors` replaces the old single-pass additive-logit
delta (`compute_base_logit`) with one additive logit anchor per equity
group -- including a universal `all_domestic` anchor every student
carries -- solved so that **each group's own realized mean probability**
(accounting for every other group's anchor and the same fixed noise draw)
matches that group's own published target. Because group memberships
overlap (a student can be `first_nations` *and* `low_ses` *and* `regional`
at once), the anchors cannot be solved independently in one pass; they are
solved **cyclically**, exactly the way `raking.rake` cycles across
dimensions -- hold every anchor but one fixed, bisection-solve that one
group's scalar anchor against its own target, move to the next group,
repeat until every anchor stops moving (`ConvergenceReport`, reused
unchanged from the raking module).

This directly implements Step 0's own calibration contract: group rates
were declared as targets with an N-dependent tolerance in
`docs/calibration_targets.md`, and anchors are how that gets enforced at
the outcome layer, rather than left to whatever a fixed correlation
structure happens to imply.

**Verified against the real target set** (`targets_v3_2023ref.json`, 20,000
students, `sigma=1.0`): every retention-rate and success-rate anchor's own
calibrated deviation is now on the order of 0.0001-0.001 percentage points
-- effectively exact, versus `first_nations`'s pre-fix ~5pp systematic
miss. `first_nations`'s *realized* (post-Bernoulli-draw) retention rate
lands at 77.26-77.96% against a 77.85% target across seeds tried, well
inside its ±2pp tolerance tier.

**`remote` still occasionally exceeds its own tolerance in a single
draw, and that is expected, not a regression**: `remote` has only ~72
students in a 20,000-student synthetic cohort (consistent with the ~32-35
underlying published N that put it in the loosest ±8pp tolerance tier to
begin with). The anchor's own calibrated deviation for `remote` is just as
tight as every other group's (~0.001pp against the exact noise draw used to
solve it), but a single Bernoulli realization over only ~72 individuals
still carries a binomial standard error of roughly 5-6 percentage points,
so an 8-11pp swing in either direction on any given seed is ordinary
sampling variance, not miscalibration -- unlike the pre-fix `first_nations`
case, where the *anchor's own calibrated mean* (not just one draw) was
several points off target. `remote` is treated as a documented gate
exemption for this reason, matching the tiny-N tier Step 0 already
anticipated, rather than a check to keep re-running seeds against until it
happens to pass.

## Latent risk propensity linking

The AUC~0.52 finding above diagnosed a real ceiling, but also exposed an
architectural gap: Step 3c's behavioural signals (units attempted/passed)
were generated **independently** of the retention outcome's own noise draw.
Structurally, that means no amount of feeding those signals to a Phase 4
model could ever raise its AUC above what demographic membership alone
already gives -- there was no actual information for the model to find.

The fix: `outcomes.generate_latent_risk` draws one standard-normal value per
student representing their unobserved, shared **risk propensity**.
`outcomes._combined_noise` mixes this shared draw with each outcome's own
idiosyncratic noise as `sqrt(connection_strength) * shared + sqrt(1 -
connection_strength) * idiosyncratic`, a one-factor model where
`connection_strength` in `[0, 1]` is the single parameter controlling how
much of retention's and success's individual variation the two outcomes
actually share. `connection_strength=0.0` (the default) exactly reproduces
the original independent-noise behaviour; increasing it makes a student's
realized academic performance genuinely lead their retention outcome,
rather than being drawn from an unrelated random process that happens to
carry the same equity-group label.

**Measured, not tuned to a target**, against the real target set (20,000
students, group anchors as above):

| `connection_strength` | AUC(`success_rate_realized` -> `retained`) |
| --- | --- |
| 0.0 | 0.50 |
| 0.3 | 0.58 |
| 0.5 | 0.62 |
| 0.6 | 0.65 |
| 0.7 | 0.67 |
| 0.8 | 0.69 |
| 0.9 | 0.72 |
| 1.0 | 0.74 |

**`connection_strength=0.7` is the value carried forward into Phase 4
generation**, chosen on conceptual grounds, not to hit a number: it encodes
"academic performance is a strong, but not deterministic, proxy for the
same underlying propensity that drives attrition" -- leaving room for
retention-specific noise (financial hardship, family circumstances, a
program transfer) that need not show up in first-year unit completion, and
for academic-specific noise (a hard subject, a single bad exam) that need
not predict withdrawal. At `connection_strength=0.7`, the demographic-only
AUC is unchanged at ~0.51-0.52 (confirming the group anchors do not
themselves add discriminative power -- they recentre group means, they do
not spread individuals within a group), while the behavioural-signal AUC
reaches ~0.67.

**Disclosed honestly rather than adjusted to close the gap**: even at
`connection_strength=1.0` -- the most extreme value this one-factor model
allows, meaning success and retention share the *entire* noise draw -- a
single univariate behavioural signal only reaches AUC~0.74, short of Phase
3-4's originally discussed 0.75-0.85 band. That band was always describing
what a *fitted, multivariate* Phase 4 model could reach combining several
real features (this project's single synthetic success-rate signal,
per-period trends, enrolment intensity, engagement data if it becomes
available); it was never a property this generative layer alone was
expected to hit with one feature and a naive rank score. This layer's job
was to make sure a genuine behavioural signal exists at all for Phase 4 to
combine with others -- confirmed by the AUC actually moving with
`connection_strength`, not staying pinned at 0.52 -- not to pre-solve
Phase 4's discrimination target itself.

## Tiny-N gate methodology

The `remote` gate (retention_rate, ±8pp tolerance, N=35 -- the `10<=n<50`
tier Step 0 defined for exactly this reason) still occasionally failed a
*single* population/seed run even after the anchors above made its own
calibrated mean exact: one Bernoulli draw over ~72 synthetic students
(20,000-student cohort x remote's ~0.36% enrolment share) carries a binomial
standard error of roughly 5-6 percentage points, comparable to the
tolerance itself, so a single draw cannot distinguish genuine miscalibration
from ordinary sampling noise.

This was turned from an assertion into evidence rather than left as a
documented shrug: `validate.run_multi_seed_outcome_rates` re-runs outcome
assignment 10 times against the *same* raked population, varying only the
outcome-noise seed, and reports the distribution. Against the real target
set (`targets_v3_2023ref.json`, `connection_strength=0.7`,
`population_seed=42`): `remote`'s 10-seed realized retention rate ranged
63.89%-79.17% (mean 70.69%, std 4.14pp) against a 66.78% target -- a
mean-of-10 deviation of 3.91pp, comfortably inside the ±8pp tolerance,
versus a single unlucky draw that reached 77.78% (11.0pp, outside
tolerance) in the run that originally surfaced this. Repeating the same
check against two other population seeds (7 and 99) landed even closer to
target (deviation 0.72pp and 0.53pp respectively) -- confirming the
single-seed 11pp miss was itself just sampling variance at this N, not a
residual calibration bug like the pre-fix `first_nations` case (where the
anchor's own *calibrated mean*, not just one draw, was off).

**The rule this evidence justifies, and the one `generate_validation_report`
now implements** (`multi_seed_retention_rate`/`multi_seed_success_rate`
parameters, `validate.TINY_N_GATE_THRESHOLD = 50`): any equity group whose
own target N falls below the tier boundary is gated on its multi-seed mean
rather than a single population's single draw; every other group (N>=50)
keeps the original single-seed gate, since regenerating multiple full
20,000-student cohorts to shrink already-small sampling noise on
already-large groups would not change any verdict. This converts `remote`'s
exemption from an accepted, undemonstrated judgment call into a documented,
reproducible methodology rule -- with the underlying single-seed evidence
kept alongside it, not replaced by it, so a future reader can see exactly
what the multi-seed check is correcting for.
