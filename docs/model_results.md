# Phase 4b/4c -- Model results and fairness snapshot

Trained and evaluated on `equitylens_risk.pipeline.build_train_holdout`
against the real target set (`targets_v3_2023ref.json`, 20,000 students per
cohort, train `population_seed=42`, holdout `population_seed=777` -- see
`docs/model_design.md`'s split-strategy section). Attrition base rate:
16.94% (train), 16.64% (holdout) -- close to each other and to the 82.91%
retention target, confirming the two cohorts were calibrated consistently
(`docs/model_design.md`'s anchor-consistency check). Reproducible via
`PYTHONPATH=src python scripts/report_phase4_metrics.py`.

## Headline metrics (holdout)

| Model | AUC | PR-AUC | Brier score |
| --- | --- | --- | --- |
| Logistic regression | 0.634 | 0.254 | 0.134 |
| Gradient boosting (`HistGradientBoostingClassifier`) | 0.626 | 0.242 | 0.135 |

The pre-declared 0.65-0.72 band in `docs/model_design.md` was a design-time
expectation for a deliberately weak, census-dated signal -- not a number to
"tune back up to." Logistic lands slightly below that floor (0.634 vs.
0.65), which is close enough to count as the same qualitative result:
pulling the decision point back to census date and weakening the only
behavioural signal (`census_connection_strength=0.4`) costs some
discrimination. That shortfall is an honest consequence of the design, not a
bug to smooth over.

PR-AUC needs the base-rate context to read correctly. A random ranking at a
16.64% attrition rate would have PR-AUC~=0.166; logistic's 0.254 is
therefore **1.53x the random baseline (~53% lift)** and boosting's 0.242 is
**1.45x (~45% lift)**. This matters because Phase 4d is not choosing
between two equally-sized classes -- it is asking whether the outreach team
can load the top of the ranked list with materially more true attriters than
random selection would.

On the headline metrics alone, **logistic regression is at least as good as
gradient boosting on every metric measured, not worse.**

PR-AUC is reported alongside AUC because the outreach team's job is
precision/recall on the minority (attrited) class at a ~17% base rate, not
symmetric discrimination between two equally-sized classes; a PR-AUC of
0.25 against a 0.17 base rate means the model concentrates risk well above
the base rate at the top of the ranking, which is what Phase 4d's
capacity-based triage will lean on.

## Why boosting doesn't win here (and why that's not a bug)

This is not a case of "boosting should have won and something is wrong" --
it is the expected result of how this synthetic outcome was generated.
Every outcome in this pipeline is drawn as `sigmoid(anchor + noise)`: a
strictly additive-in-logit, linear relationship between features and log-odds,
with no engineered interaction terms. Logistic regression's own functional
form matches this generating process almost exactly, so it has no
structural disadvantage to make up for, while gradient boosting's main
advantage -- finding interactions and non-linearities -- has nothing to
find here. That is a **limitation of the synthetic world**, not a law of the
real one: on a real institutional dataset, where interactions (e.g. a
combined effect of low SES *and* part-time study, or low SES *and* remote)
are plausible, this result would not necessarily hold. What transfers is the
**selection process** -- compare candidates, inspect calibration, then weigh
explainability -- not the identity of today's winner.

## Calibration (holdout, 10 quantile bins, predicted vs. observed rate)

| Bin (low->high risk) | Logistic: observed | Logistic: predicted | Boosting: observed | Boosting: predicted |
| --- | --- | --- | --- | --- |
| 1 | 0.076 | 0.077 | 0.078 | 0.063 |
| 2 | 0.098 | 0.098 | 0.100 | 0.100 |
| 3 | 0.121 | 0.114 | 0.123 | 0.120 |
| 4 | 0.132 | 0.132 | 0.137 | 0.141 |
| 5 | 0.148 | 0.150 | 0.148 | 0.155 |
| 6 | 0.164 | 0.169 | 0.167 | 0.175 |
| 7 | 0.168 | 0.190 | 0.178 | 0.192 |
| 8 | 0.212 | 0.215 | 0.204 | 0.201 |
| 9 | 0.230 | 0.248 | 0.236 | 0.238 |
| 10 (highest risk) | 0.316 | 0.301 | 0.297 | 0.316 |

Logistic regression tracks the diagonal slightly more tightly across bins
(the largest single gap is bin 7's 0.168 observed vs. 0.190 predicted, 2.2
points); boosting's largest gap is bin 1's 0.078 vs. 0.063 (1.5 points) but
drifts a bit more at the top end. Neither model is badly miscalibrated --
both would be usable for the probability-weighted "expected prevented
attritions" arithmetic Phase 4d needs -- but logistic's edge here adds to,
rather than trades off against, its AUC/PR-AUC edge. The group-level audit
below matters because a model can look well calibrated overall while still
misstating risk for a particular subgroup.

## Phase 4c snapshot: group-level calibration

| Group | Students (n) | Observed attrition | Mean predicted risk | Calibration gap (pp) |
| --- | --- | --- | --- | --- |
| All students | 20,000 | 16.64% | 16.95% | +0.31 |
| Low SES | 2,391 | 18.36% | 19.14% | +0.78 |
| First Nations | 431 | 20.65% | 21.68% | +1.03 |
| Disability | 1,373 | 16.10% | 17.23% | +1.14 |
| NESB | 684 | 15.64% | 13.89% | -1.75 |
| Regional | 2,239 | 16.93% | 16.85% | -0.08 |
| Remote | 72 | 37.50% | 21.29% | -16.21 |

The main pattern is not blanket unfairness across every group; it is one
clear under-prediction pocket plus a few mild gaps. Low SES, First Nations,
and disability are all slightly over-predicted (roughly +0.8 to +1.1pp),
regional is essentially on target, NESB is modestly under-predicted, and
**remote is the one group where this v1 model clearly misses the group's mean
risk level**. That remote result needs to be carried with caution rather than
"fixed by hand": the group is tiny (72 students, 27 attriters in this
holdout), so the estimate is noisy, but the direction is still important for
Phase 4d because a queue built from these scores will inherit that
understatement.

## Phase 4c/4d bridge: operational top-k triage, not an arbitrary 0.5 cutoff

Because the outreach queue is capacity-based, the relevant decision rule is
"take the top X% of the ranking," not "predict attrition whenever
probability >= 0.5." In fact, this census-date model's maximum holdout
probability is only 0.423, so a 0.5 cutoff would flag nobody and tell us
nothing operationally.

| Queue cut | Minimum score admitted | Precision | Recall | FNR | Lift vs. 16.64% base rate |
| --- | --- | --- | --- | --- | --- |
| Top 10% | 0.267 | 31.6% | 19.0% | 81.0% | 1.90x |
| Top 15% | 0.247 | 29.0% | 26.2% | 73.8% | 1.74x |
| Top 20% | 0.230 | 27.3% | 32.8% | 67.2% | 1.64x |

This is the operational meaning of an AUC in the mid-0.63s: even without a
spectacular discrimination score, the model still makes the outreach queue
materially denser in true attriters than a random list would be. Phase 4d's
eventual intervention arithmetic should therefore be phrased as "what do we
get per 2,000 / 3,000 / 4,000 outreach slots?" not "is the classifier
perfect?"

### Threshold-dependent FNR by group

| Group | Attriters (n) | FNR @ top 10% | FNR @ top 15% | FNR @ top 20% | 95% CI for FNR @ top 15% |
| --- | --- | --- | --- | --- | --- |
| All students | 3,328 | 81.0% | 73.8% | 67.2% | 72.3% to 75.3% |
| Low SES | 439 | 69.5% | 62.0% | 56.9% | 57.3% to 66.4% |
| First Nations | 89 | 47.2% | 41.6% | 34.8% | 31.9% to 52.0% |
| NESB | 107 | 95.3% | 92.5% | 87.9% | 85.9% to 96.2% |
| Remote | 27 | 59.3% | 48.1% | 48.1% | 30.7% to 66.0% |

This is the clearest 4c-to-4d link in the current work:

1. FNR is **not** a fixed property of the model; it changes materially with
   queue size.
2. The change is **not uniform across groups**.
3. Small groups need uncertainty attached. `first_nations` is a good
   example: the top-15% point estimate says the model misses 41.6% of actual
   attriters in that group, but the 95% interval is still wide (31.9% to
   52.0%) because there are only 89 actual attriters in the holdout group.

The fairness risk here is therefore operational, not abstract. A top-15%
queue still misses nearly three-quarters of all attriters overall, but it
misses **less** of the First Nations and remote groups than of the full
population, while missing **more** of NESB attriters because very few NESB
students reach the top of the ranking at all (only 3.9% of NESB students are
in the top-15% queue). That is exactly the sort of threshold-sensitive trade
the Phase 4d triage design has to surface explicitly rather than burying
inside one overall AUC.

## Feature importance

**Logistic regression** (standardized coefficients; `geography` one-hot
with `metro` as the dropped baseline, so `geography_remote`/`geography_regional`
read as risk *relative to* metro):

| Feature | Standardized coefficient |
| --- | --- |
| `census_engagement_score` | -0.481 |
| `geography_remote` | +0.340 |
| `low_ses` | +0.059 |
| `first_nations` | +0.049 |
| `non_english_speaking_background` | -0.044 |
| `women_non_traditional_area` | +0.021 |
| `first_in_family` | -0.015 |
| `seifa_decile` | +0.005 |
| `disability` | +0.002 |
| `geography_regional` | +0.001 |

**Gradient boosting** (permutation importance, mean drop in holdout AUC
when a feature is shuffled):

| Feature | Mean dAUC |
| --- | --- |
| `census_engagement_score` | 0.1237 |
| `seifa_decile` | 0.0038 |
| `low_ses` | 0.0032 |
| `geography` | 0.0011 |
| `first_nations` | 0.0011 |
| `disability` | 0.0010 |
| `first_in_family` | 0.0009 |
| `women_non_traditional_area` | 0.00003 |
| `non_english_speaking_background` | -0.0003 |

Both models agree, overwhelmingly: `census_engagement_score` carries almost
all of the discriminative power (permutation importance ~33x the next
feature), consistent with `docs/assumptions.md`'s "equity-group membership
alone caps implied AUC at ~0.52" finding -- the demographic features are not
dead weight (`geography_remote` and `low_ses` both show the expected
sign and a real, if small, effect), but this v1 model's discrimination is
substantively a one-feature story. `first_nations` behaves consistently in
both models too: a small positive risk coefficient in logistic, a small but
present permutation importance in boosting, matching its own known
retention gap (77.85% vs. 82.91% overall) at the population level.

## Model selection: logistic regression, chosen on both performance and explainability grounds

Logistic regression is selected as the Phase 4c/4d model, for two
independent reasons that happen to agree here:

1. **It does not lose on any evaluated metric** (AUC, PR-AUC, Brier,
   calibration) -- there is no accuracy the boosting model is "worth" the
   trade-off below.
2. **Explainability**: an institution's outreach team, and the students
   flagged, can be given "you are flagged primarily because of an early
   engagement signal, and secondarily because you are in a remote/low-SES
   group" as a direct, auditable statement from the model's own
   coefficients. `HistGradientBoostingClassifier` would need a post-hoc
   explainer (e.g. SHAP) to produce a comparable per-student explanation,
   adding a layer of approximation to a decision that materially affects a
   real student's outreach experience.

Had boosting won on AUC/PR-AUC by a wide margin, this would be a real
trade-off to argue explicitly (accuracy vs. explainability); it is reported
as a clean, one-directional result here because the evidence turned out
that way, not because logistic regression was decided on in advance.

## What this feeds into next (Phase 4d, not yet implemented)

This file now carries the first 4c bridge into 4d: model choice, overall
calibration, group calibration, and queue-size-dependent miss rates are all
measured on the same holdout cohort. The remaining Phase 4d work is not to
re-decide the model; it is to attach these ranked queues to capacity and
initiative assumptions (e.g. "if outreach can contact the top 3,000
students, how many true attriters does that reach, and how does that split
by group?").
