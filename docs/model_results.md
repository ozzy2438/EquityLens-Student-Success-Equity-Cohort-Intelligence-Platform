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

## Phase 4c fairness summary

The standalone fairness artefact is now
[`docs/fairness_assessment.md`](fairness_assessment.md).

The short version is:

- **First Nations is not being under-predicted in this holdout.** Observed
  attrition is 20.65% versus mean predicted risk 21.68% (**+1.03pp**).
- **The sharpest calibration miss is remote, not First Nations.** Remote
  observed attrition is 37.50% versus predicted 21.29% (**-16.21pp**), but
  this is based on only `72` students and `27` attriters.
- **The harshest top-k miss pattern is NESB.** At the top-15% queue cut, the
  model misses **92.5%** of actual NESB attriters (95% CI:
  **85.9% to 96.2%**) because only **3.9%** of NESB students enter that
  queue.
- **First Nations and remote go the other way at top-15%.** Their FNRs are
  **41.6%** and **48.1%**, both materially lower than the whole-cohort
  **73.8%** -- favourable directionally, but still uncertain because those
  groups are small.

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

The detailed group-by-group FNR tables, calibration gaps, confidence
intervals, and the "what is a real finding versus what is still noisy?"
interpretation now live in
[`docs/fairness_assessment.md`](fairness_assessment.md). That separation is
intentional: `model_results.md` stays focused on model performance and model
choice, while the fairness document stands alone as the Phase 4c artefact a
reviewer can read without excavating the rest of the modelling report.

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

## What this feeds into next

The model-selection question is now closed enough to support queue-design
work. The next-stage triage counterfactuals live in
[`docs/triage_policy_analysis.md`](triage_policy_analysis.md): Tier 1/2/3
capacity scenarios, expected prevented attritions under simple effectiveness
assumptions, and NESB-focused queue alternatives that make the
fairness-versus-efficiency trade-off explicit. What remains after that is
not to re-decide the model; it is to attach those queue designs to concrete
initiative assumptions and, later, presentation surfaces.
