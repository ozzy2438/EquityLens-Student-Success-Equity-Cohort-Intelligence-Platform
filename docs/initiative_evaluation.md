# Phase 4e -- Initiative evaluation

This is the initiative layer that sits on top of the risk model and the
Phase 4d queue-policy analysis.

Phase 4d answered two questions:

- how dense is each queue cut in true attriters?
- what fairness-efficiency trade-offs appear if the queue rule changes?

Phase 4e adds the next question:

> If a given queue or queue band receives a specific kind of intervention,
> how many attritions might that plausibly prevent?

This is still **scenario analysis**, not evidence that a real ACU program
will achieve the same effect. The role of this document is to make the
initiative assumptions explicit enough that they can be challenged or
replaced later.

## Planning assumptions used here

The intervention names below are generic operating models, not claims about
ACU's current program catalog:

| Tier | Queue band | Initiative archetype | Assumed effect on reached true attriters |
| --- | --- | --- | --- |
| Tier 1 | Top 0-10% | High-touch case management | 15% |
| Tier 2 | Top 10-15% | Advisor outreach | 10% |
| Tier 3 | Top 15-20% | Digital nudge / referral | 5% |

These are deliberately simple planning rates:

- they are **not** literature-backed effect estimates
- they are **not** being written into `docs/assumptions.md` as if they were
  source-grounded facts
- they exist only to translate queue density into a comparable program
  impact surface

## A three-tier intervention ladder

The 4d queue table used cumulative cuts (top 10%, top 15%, top 20%). For an
actual intervention stack, the more useful lens is the **marginal** band:
the first 2,000 students, then the next 1,000, then the next 1,000.

| Initiative | Band | Slots | Precision | True attriters reached | Assumed effect | Expected prevented attritions | Prevented per 100 slots | Share of blended-program impact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tier 1 - case management | Top 0-10% | 2,000 | 31.6% | 631 | 15% | 94.6 | 4.7 | 73.0% |
| Tier 2 - advisor outreach | Top 10-15% | 1,000 | 24.0% | 240 | 10% | 24.0 | 2.4 | 18.5% |
| Tier 3 - digital nudge | Top 15-20% | 1,000 | 22.0% | 220 | 5% | 11.0 | 1.1 | 8.5% |

If all three bands are run as one ladder, the blended program's expected
prevented attritions sum to **129.6**.

What this says:

- the **first 2,000 students dominate the impact story**: under these
  simple planning rates, Tier 1 contributes about **73%** of the blended
  program's expected prevented attritions
- the next two bands still add value, but the yield decays quickly
- this is the operational version of the ranking story: later queue bands
  contain more students but fewer strong bets per slot

So if staffing is tight, the real question is not "should we run all three
tiers?" but "which lower-yield bands are still worth activating once the
high-yield top band is covered?"

## Policy sensitivity: the same initiative under different Tier-2 queue rules

Phase 4d found that the most stable queue-design fairness concern was
NESB under-capture at the top-15% cut. The natural 4e follow-up is:

> If the intervention itself stays the same, how much expected impact shifts
> when the queue rule changes?

Using a common **10% effect rate** for the Tier-2 intervention:

| Policy | Overall precision | Overall true attriters reached | Overall expected prevented | NESB flagged share | NESB true attriters reached | NESB expected prevented | Delta overall prevented vs global | Delta NESB prevented vs global |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Global top-15% | 29.0% | 871 | 87.1 | 3.9% | 8 | 0.8 | 0.0 | 0.0 |
| B. NESB floor at 15% within group | 29.0% | 871 | 87.1 | 14.9% | 24 | 2.4 | 0.0 | +1.6 |
| C. NESB FNR-parity floor | 28.9% | 868 | 86.8 | 19.3% | 29 | 2.9 | -0.3 | +2.1 |

This is the most important 4e result:

- **Policy B weakly dominates Policy A on this holdout.** It keeps overall
  expected prevented attritions flat at **87.1**, while tripling NESB-
  specific expected prevented attritions from **0.8** to **2.4**.
- **Policy C buys more NESB impact again**, but now the trade-off becomes
  visible: NESB expected prevented attritions rise to **2.9**, while
  overall expected prevented attritions fall slightly from **87.1** to
  **86.8**.

That is exactly the kind of policy trade-off that should be documented, not
hidden behind a single "best" queue.

## What this means for a decision-maker

The initiative decision and the queue-rule decision are related, but they
are not the same decision.

- If the priority is **maximum simplicity**, Policy A plus a Tier-1-first
  program ladder is coherent.
- If the priority is **a modest equity-aware adjustment with no observed
  efficiency loss**, Policy B is the strongest planning default in this
  synthetic holdout.
- If the priority is **explicitly narrowing NESB miss rates**, Policy C
  makes the cost of that stance transparent rather than pretending it is
  free.

The point of 4e is not to pick one of those values unilaterally. It is to
show that they are policy values, and to quantify what each one buys.

## Limits

- These effect rates are planning parameters, not validated treatment
  effects.
- They are applied uniformly to every reached true attriter within a band;
  no heterogeneity by subgroup, initiative fit, or service capacity is
  modeled yet.
- The NESB comparison is a single-group policy example because that was the
  strongest threshold-sensitive fairness issue from 4c/4d; it is not a full
  multi-group optimization framework.

## Reproducibility

All numbers in this document are regenerated by:

```bash
PYTHONPATH=src python scripts/report_phase4e_initiatives.py
```
