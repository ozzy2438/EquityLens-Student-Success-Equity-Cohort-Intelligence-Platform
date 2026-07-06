# Phase 4c -- Fairness assessment (holdout snapshot)

This is the standalone fairness artefact for the current Phase 4 logistic
regression model, evaluated on the same holdout cohort documented in
`docs/model_results.md` (`targets_v3_2023ref.json`, 20,000 students,
train `population_seed=42`, holdout `population_seed=777`).

Its job is narrower than "prove the model is fair." It surfaces the
specific equity trade-offs the current ranked outreach queue would create,
using two views:

- **Group-level calibration**: within each group, is predicted risk close to
  observed attrition?
- **Threshold-dependent miss rates**: at realistic queue cuts, which groups'
  true attriters are still being missed?

Because this is still a synthetic world, these results are not a final claim
about real ACU students. They are the fairness behaviour of the current
design under the current generator, made explicit rather than assumed.

## Headline findings

1. **First Nations is not being under-predicted in this holdout.** The model
   slightly over-predicts that group's mean risk: observed attrition 20.65%
   versus mean predicted risk 21.68% (**+1.03 percentage points**).
2. **The sharpest calibration miss is remote students, not First Nations.**
   Remote observed attrition is 37.50% versus mean predicted risk 21.29%
   (**-16.21 points**), but the group is tiny (`n=72`, `27` attriters), so
   this is directionally important but statistically noisy.
3. **The harshest threshold-based miss rate is NESB.** At a top-15% queue
   cut, the model misses **92.5%** of actual NESB attriters
   (95% CI: **85.9% to 96.2%**) because very few NESB students enter the
   queue at all (flagged share **3.9%**).
4. **First Nations and remote are reached more aggressively than the overall
   population at top-15%.** Overall FNR is **73.8%**; First Nations is
   **41.6%** and remote is **48.1%**. That is a favourable direction, but
   both estimates carry wide intervals because the groups are small.
5. **The main fairness tension for Phase 4d is threshold choice, not one
   universal bias sign.** Some groups are over-predicted, some
   under-predicted, and queue size changes these miss rates materially.

## Group-level calibration

| Group | Students (n) | Attriters (n) | Observed attrition | Mean predicted risk | Calibration gap (pp) |
| --- | --- | --- | --- | --- | --- |
| All students | 20,000 | 3,328 | 16.64% | 16.95% | +0.31 |
| Low SES | 2,391 | 439 | 18.36% | 19.14% | +0.78 |
| First Nations | 431 | 89 | 20.65% | 21.68% | +1.03 |
| Disability | 1,373 | 221 | 16.10% | 17.23% | +1.14 |
| NESB | 684 | 107 | 15.64% | 13.89% | -1.75 |
| Women in non-traditional area | 720 | 134 | 18.61% | 18.54% | -0.07 |
| First in family | 9,968 | 1,627 | 16.32% | 16.78% | +0.45 |
| Regional | 2,239 | 379 | 16.93% | 16.85% | -0.08 |
| Remote | 72 | 27 | 37.50% | 21.29% | -16.21 |
| Metro | 17,689 | 2,922 | 16.52% | 16.94% | +0.43 |

Interpretation:

- Most groups sit within roughly **±1 point** of observed attrition, which is
  a reasonable v1 calibration story for this synthetic holdout.
- `first_nations`, `low_ses`, and `disability` are all **slightly
  over-predicted**, not under-predicted.
- That is operationally less harmful than systematic under-prediction -- it
  creates some extra outreach rather than silently missing risk -- but it is
  not costless. Persistent over-flagging of one group can still create
  intervention fatigue and a labeling effect, so "not under-predicted" is
  not the same thing as "done."
- `nesb` is **modestly under-predicted** on mean risk.
- `remote` is the one group with a clearly material calibration gap, but the
  sample is too small to treat the point estimate as a stable magnitude.

### Remote tiny-N stability check

The remote result should be held to the same standard as the project's
earlier tiny-N gate methodology rather than trusted off one holdout draw.
Using the current fitted logistic model and **10 independent holdout
cohorts** (same target set, fresh outcome/noise draws), the remote
calibration gap stays negative in every run:

| Check | Value |
| --- | --- |
| Holdouts evaluated | 10 |
| Remote students per holdout | 72 |
| Mean calibration gap | -10.56pp |
| Median calibration gap | -10.31pp |
| Range | -17.70pp to -4.59pp |

This strengthens the directional claim: the current synthetic world
systematically under-predicts remote risk, not just in one lucky/unlucky
draw. But it does **not** prove the mechanism is "model bias" in isolation.
Because every one of those holdouts still comes from the same synthetic
generator, the stable negative gap may be a property of the data-generating
process for a tiny subgroup as much as of the fitted model. That is exactly
why this belongs in Phase 4's fairness documentation rather than being
"fixed" inside the scorecard without explanation.

## Threshold-dependent FNR at operational queue cuts

The relevant question for Phase 4d is not "what happens at probability
0.5?" The model never reaches 0.5 on this holdout. The real question is:
if the outreach team can only work the top slice of the ranking, which
groups' true attriters are still being missed?

### Overall queue quality

| Queue cut | Precision | Recall | FNR | Lift vs. 16.64% base rate |
| --- | --- | --- | --- | --- |
| Top 10% | 31.6% | 19.0% | 81.0% | 1.90x |
| Top 15% | 29.0% | 26.2% | 73.8% | 1.74x |
| Top 20% | 27.3% | 32.8% | 67.2% | 1.64x |

### Group miss rates

| Group | Attriters (n) | FNR @ top 10% | FNR @ top 15% | FNR @ top 20% | 95% CI for FNR @ top 15% | Flagged share @ top 15% |
| --- | --- | --- | --- | --- | --- | --- |
| All students | 3,328 | 81.0% | 73.8% | 67.2% | 72.3% to 75.3% | 15.0% |
| Low SES | 439 | 69.5% | 62.0% | 56.9% | 57.3% to 66.4% | 23.7% |
| First Nations | 89 | 47.2% | 41.6% | 34.8% | 31.9% to 52.0% | 35.3% |
| Disability | 221 | 79.2% | 73.8% | 68.8% | 67.6% to 79.1% | 16.0% |
| NESB | 107 | 95.3% | 92.5% | 87.9% | 85.9% to 96.2% | 3.9% |
| Women in non-traditional area | 134 | 73.9% | 63.4% | 54.5% | 55.0% to 71.1% | 22.5% |
| First in family | 1,627 | 82.3% | 74.9% | 68.1% | 72.7% to 76.9% | 14.4% |
| Regional | 379 | 81.8% | 76.3% | 70.4% | 71.7% to 80.3% | 14.6% |
| Remote | 27 | 59.3% | 48.1% | 48.1% | 30.7% to 66.0% | 34.7% |
| Metro | 2,922 | 81.1% | 73.8% | 67.0% | 72.1% to 75.3% | 15.0% |

Interpretation:

- **NESB is the clearest operational fairness concern.** Its mean-risk
  calibration gap is only -1.75 points, but the top-15% queue still misses
  **92.5%** of actual NESB attriters because almost none of that group
  enters the queue.
- **First Nations is the opposite pattern.** It is slightly over-predicted on
  mean risk, and the queue captures that group relatively aggressively:
  `35.3%` of First Nations students appear in the top-15% queue, and the
  group FNR falls to **41.6%**, materially below the overall **73.8%**.
- **Remote also enters the queue at a high rate** (`34.7%` flagged at the
  top-15% cut), which offsets some of its calibration miss. But the interval
  is wide enough that this should be treated as "promising but uncertain,"
  not as a settled fairness success.
- **Low SES and women in non-traditional areas** are also reached more
  aggressively than the overall population at top-15%.
- **Disability, first-in-family, regional, and metro** are closer to the
  overall miss-rate pattern; none is as extreme as NESB.

## What is a real finding versus what is still uncertain?

Reasonably firm, given this holdout size:

- overall queue quality is real enough to plan with
- NESB under-capture at top-k is real enough to flag as a policy concern
- First Nations is **not** currently a case of obvious under-prediction

Directionally important but still uncertain because of small `n`:

- remote under-prediction on calibration
- remote's apparently favourable top-k capture rate
- the exact magnitude of First Nations FNR, even though its direction is
  clearly better than the whole-cohort average

## Implication for Phase 4d

This is the quantitative trade-off table Phase 4d should inherit. If a
future tier structure picks its cutoffs by maximizing overall precision
alone, it risks accepting a queue that misses NESB attriters at a much
higher rate than the rest of the population. If it instead tries to protect
against disproportionate group miss rates, overall queue efficiency may
drop. That is not a bug to "solve away" inside the model report; it is a
policy trade-off to document so the intervention design can choose
explicitly. The actual counterfactual queue designs now live in
[`docs/triage_policy_analysis.md`](triage_policy_analysis.md).
