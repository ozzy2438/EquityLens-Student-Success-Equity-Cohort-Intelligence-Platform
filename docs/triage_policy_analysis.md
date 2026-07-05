# Phase 4d -- Triage policy analysis

This document turns the selected Phase 4 logistic model into an outreach
queue design problem. It is not trying to decide policy unilaterally. Its
job is to make the trade-offs visible enough that a policy owner could
choose between them.

Inputs:

- model: the Phase 4 logistic regression selected in
  [`docs/model_results.md`](model_results.md)
- fairness signal carried in from
  [`docs/fairness_assessment.md`](fairness_assessment.md)
- cohort: holdout population from `targets_v3_2023ref.json`, 20,000 students

Two guardrails matter here:

1. The queue is **capacity-constrained**, so the real decision is "how many
   students can outreach contact?" not "who scores above 0.5?"
2. The fairness concern is **policy-sensitive**, not just model-sensitive.
   A single global queue, a quota floor, and a group-specific percentile cut
   can all be fed by the same risk score but create very different miss-rate
   patterns.

## Tier 1 / 2 / 3 capacity scenarios

The simplest 4d question is: if outreach can contact the top 2,000, 3,000,
or 4,000 students, what does the queue look like?

Expected prevented attritions below are simple sensitivity scenarios, not
claims about proven intervention efficacy. They mean: *if outreach
successfully prevents attrition for 5%, 10%, or 15% of the true attriters it
reaches*, how many attritions would that avert?

| Tier | Queue cut | Slots | Minimum score admitted | Precision | Recall | FNR | True attriters reached | Expected prevented @ 5% | Expected prevented @ 10% | Expected prevented @ 15% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tier 1 | Top 10% | 2,000 | 0.2675 | 31.6% | 19.0% | 81.0% | 631 | 31.6 | 63.1 | 94.6 |
| Tier 2 | Top 15% | 3,000 | 0.2474 | 29.0% | 26.2% | 73.8% | 871 | 43.6 | 87.1 | 130.7 |
| Tier 3 | Top 20% | 4,000 | 0.2303 | 27.3% | 32.8% | 67.2% | 1,091 | 54.6 | 109.1 | 163.7 |

Interpretation:

- Larger queues reach more true attriters, but the marginal students are
  weaker bets: precision declines from **31.6%** at Tier 1 to **27.3%** at
  Tier 3.
- Tier 2 is a plausible planning middle point: it reaches **871** true
  attriters while keeping the queue materially denser than random
  selection (**1.74x** base-rate lift).
- Even Tier 3 still misses most attriters (**67.2% FNR**), so 4d should be
  treated as prioritization support, not as a full attrition-safety net.

## Why the NESB finding changes the queue design conversation

Phase 4c's most stable threshold-based fairness concern was not First
Nations or remote; it was `nesb`. Under the plain global top-15% queue:

- only **27** NESB students are admitted
- that is only **3.9%** of the NESB group
- the queue reaches only **8** true NESB attriters
- NESB FNR stays at **92.5%**

That is not automatically "the model is broken." It is the structural
outcome of a single risk-ranked queue when one group enters the ranking in
very small numbers. The right 4d question is therefore: what do alternative
queue rules buy or cost?

## Tier 2 policy alternatives (3,000 slots)

To keep the comparison legible, the counterfactuals below target the
specific issue discovered in 4c: NESB under-capture at the top-15% cut.
They do **not** try to solve every overlapping equity group at once. That
multi-group policy design is a real next step, but it would bury the
single-trade-off lesson under too many simultaneous rules.

| Policy | Rule | Overall precision | Overall recall | Overall true attriters reached | Expected prevented @ 10% | NESB slots | NESB flagged share | NESB attriters reached | NESB FNR | Delta overall true attriters vs global | Delta NESB attriters reached vs global |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Global top-15% | One queue, pure score ranking | 29.0% | 26.2% | 871 | 87.1 | 27 | 3.9% | 8 | 92.5% | 0 | 0 |
| B. NESB floor at 15% within group | Guarantee at least 15% of NESB students reach the queue, then fill remaining slots globally | 29.0% | 26.2% | 871 | 87.1 | 102 | 14.9% | 24 | 77.6% | 0 | +16 |
| C. NESB FNR-parity floor | Raise the NESB floor just enough to bring NESB FNR down to the whole-cohort FNR level | 28.9% | 26.1% | 868 | 86.8 | 132 | 19.3% | 29 | 72.9% | -3 | +21 |

### What these alternatives mean

**A. Global top-15%**

- maximizes simplicity
- leaves the 4c fairness concern untouched
- is the cleanest "efficiency-first" baseline

**B. NESB floor at 15% within group**

- is the smallest group-aware intervention in this set
- reaches **16 additional NESB attriters**
- on this holdout, costs **nothing** on overall precision or recall

That last point is notable. In this synthetic holdout, the plain global
queue is **not** Pareto-optimal: a mild group floor improves NESB capture
without reducing overall queue efficiency.

**C. NESB FNR-parity floor**

- is a stronger fairness intervention
- reaches **21 additional NESB attriters**
- loses only **3** true attriters overall relative to the baseline queue
  (about **0.3** expected prevented attritions at 10% efficacy)

This is the most literal version of the position from 4c: if a policy owner
decides that "one group should not have a materially worse miss rate than
the cohort as a whole," the cost of that principle can be stated
quantitatively rather than argued abstractly.

## Decision framing: this is a policy choice, not a hidden model setting

The three designs above are fed by the **same** fitted model. What changes
is the queue rule. That distinction matters:

- if ACU wants the highest-efficiency single list, Policy A is defensible
- if ACU wants a modest equity-aware adjustment with no observed efficiency
  loss in this holdout, Policy B is attractive
- if ACU wants to actively limit disproportionate NESB miss rates, Policy C
  makes the price of that stance explicit

The analyst's role here is not to declare one morally correct answer. It is
to prevent a hidden policy choice from masquerading as a neutral technical
default.

## Limits

- This is still a synthetic holdout, not a real outreach trial.
- The counterfactuals above target **NESB specifically** because that is
  where the Phase 4c fairness audit found the strongest stable threshold
  problem. They are illustrations of policy mechanics, not a complete
  multi-group fairness constitution.
- `remote` remains too small for direct quota design here; its persistent
  under-prediction signal is documented in
  [`docs/fairness_assessment.md`](fairness_assessment.md), but not converted
  into a queue rule until the small-group mechanism is better understood.

## Reproducibility

All numbers in this document are regenerated by:

```bash
PYTHONPATH=src python scripts/report_phase4d_triage.py
```
