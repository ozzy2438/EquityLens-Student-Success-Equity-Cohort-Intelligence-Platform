# EquityLens

EquityLens is a student-success and equity cohort intelligence platform. This
repository currently implements the governed ingestion foundation (Day 1),
the normalisation/warehouse layer (Phase 2), calibration target generation
through synthetic outcome assignment (Phase 3), and a first leakage-safe
risk model plus its initial fairness/threshold audit (Phase 4a-4c bridge):
full triage workflow, initiative evaluation (Phase 4d-4e), and dashboards
are the remaining scope.

## Phase 4 (Steps 4a-4b) status

`docs/model_design.md` fixes the prediction point -- Semester 1 census
date, predicting year-1 attrition -- **before** any model was fit, because
the obvious behavioural feature (`success_rate_realized`, Phase 3c's
full-year aggregate) shares its generator with the label itself and is not
actually known at census date: using it would reproduce Phase 3's own
AUC~0.67 finding under a different name, with the timing quietly wrong.
`equitylens_risk.features.generate_census_engagement_signal` builds a
feature that genuinely is available at census date instead, sharing
`shared_latent_risk` but through a deliberately weaker connection than the
full-year signal's -- measured at AUC=0.631 alone, and shown to move
smoothly from ~0.59 to ~0.67 as that connection strengthens
(`docs/images/auc_vs_decision_point.png`), the direct evidence that
discrimination trades against how early the decision is made.

`equitylens_risk.pipeline` builds train/holdout as two separate simulated
cohorts (different seeds) rather than a row split -- and its own tests
caught and disclosed a subtlety worth knowing before trusting the split:
the raked demographic columns (`geography`, `low_ses`, `first_nations`,
`seifa_decile`) come out identical between any two cohorts calibrated to
the same targets (expected -- that is what calibration means), while every
independently-assigned attribute and outcome signal varies as intended.

`docs/model_results.md`: logistic regression and gradient boosting were
compared on AUC, PR-AUC, Brier score, and calibration on the holdout
cohort. Logistic regression wins or ties on every metric -- an expected
result, not a surprise, since every synthetic outcome here is generated as
a strictly additive-in-logit function with no interaction terms, exactly
logistic regression's own functional form. It was selected for Phase
4c-4d on that basis plus its direct per-student explainability, not decided
in advance. The same results file now carries the first 4c/4d bridge too:
group-level calibration, top-10%/15%/20% queue quality, and
threshold-dependent group FNR with confidence intervals for small groups,
so fairness is tied to the outreach queue the institution would actually
run rather than to an arbitrary 0.5 cutoff.

## Phase 3 (Steps 3a-3d) status

`outcomes.py` assigns each synthetic student a year-1 retention outcome,
a Section 15-style success rate (EFTSL passed/attempted), and 4/6/9-year
completion **conditioned on** their retention outcome (so the synthetic data
cannot reproduce the retention-vs-completion contradiction Phase 2's
reconciliation check guards against in the real warehouse). Outcomes are
calibrated through two mechanisms, both fully documented in
[`docs/assumptions.md`](docs/assumptions.md):

- **Group-level logit anchors** (`outcomes.calibrate_anchors`) replace a
  fixed additive-logit delta with one anchor per equity group -- including
  the institution-wide `all_domestic` anchor -- solved cyclically (the same
  idea as `raking.rake`, applied to a scalar per group) so every group's own
  realized rate matches its own published target, fixing an earlier
  systematic ~5pp miss on `first_nations` without touching Step 2's lift
  factors.
- **Shared latent risk propensity** (`outcomes.generate_latent_risk`,
  `connection_strength`) links the Step 3c behavioural signal
  (`success_rate_realized`) to the retention outcome through one shared
  noise factor, rather than generating them independently. Measured (not
  tuned): at `connection_strength=0.0` the behavioural signal carries no
  information about retention (AUC~0.50); at the project's chosen
  `connection_strength=0.7` it reaches AUC~0.67, still short of the
  0.75-0.85 band a fitted, multi-feature Phase 4 model was always expected
  to need several real signals (not one synthetic proxy scored by rank) to
  reach -- disclosed honestly rather than pushed to `connection_strength=1.0`
  to chase the number.

Demographic-group membership alone still caps discrimination at an implied
AUC of ~0.52 regardless of anchors or `connection_strength` (checked across
a sigma range spanning two orders of magnitude) -- the anchors recentre each
group's mean, they do not add within-group spread for a model to find.

`equitylens_synthetic.validate.generate_validation_report`'s gate is fully
green against the real target set: the one remaining tiny-N group
(`remote`, N=35) is evaluated on its 10-seed mean realized rate rather than
a single population's single draw (`validate.run_multi_seed_outcome_rates`,
`docs/assumptions.md` "tiny-N gate methodology") -- a single Bernoulli
realization over ~72 synthetic students carries sampling variance
comparable to the group's own tolerance, so one draw cannot tell genuine
miscalibration apart from ordinary noise, and the multi-seed check makes
that distinction with evidence instead of an unsupported exemption.

`equitylens_synthetic.validate.generate_validation_report` re-checks
population marginals, outcome rates, and completion rates after outcomes are
assigned, and reports both the demographic-only and behavioural-signal
implied AUC alongside.

## Phase 3 (Steps 2a-2c) status

`equitylens-synthesize baseline` (Step 2a) and `equitylens-synthesize raked`
(Step 2c) both generate a ~20K-student synthetic commencing cohort against
`docs/calibration_targets.md`'s targets, but only one is trustworthy: the
baseline samples every equity attribute independently (deliberately wrong,
kept as a comparison point), while the raked population uses a from-scratch
Iterative Proportional Fitting implementation
([`raking.py`](src/equitylens_synthetic/raking.py)) seeded with real
pairwise correlation structure from DoE Section 11's equity-group
intersectionality table, then adjusted to match ACU's own marginals. Every
target matches within 0.03 percentage points at 20,000 students, 3
iterations. See [`docs/assumptions.md`](docs/assumptions.md) for every
literature-sourced (non-warehouse) value the population depends on,
including a disclosed counter-intuitive finding: these equity groups
co-occur *less* than chance nationally, not more.

## Phase 3 (Step 0) status

`equitylens-calibrate targets` builds the versioned calibration target set
defined in [`docs/calibration_targets.md`](docs/calibration_targets.md) --
Section 11 equity-group enrolment shares (±1.0pp), Section 16 equity-specific
retention/success rates (N-dependent tolerance, ±2.0pp down to excluded for
n<10), and the national SEIFA decile distribution (±2.0pp) -- and writes it
to `data/calibration/targets_v1_2023ref.json` (git-ignored), embedding the
warehouse's own SHA-256 and the generating commit so any later run can prove
which data and code produced a given target set. Suppressed cells are
imputed from the sector average and flagged with `imputed_target_flag`
rather than silently dropped or zeroed.

## Phase 2 completion status

`equitylens-normalize build` turns the 31 raw workbooks into a tested
`institution x year x equity_group x metric` DuckDB warehouse
(`data/warehouse/equitylens.duckdb`, git-ignored). Sheet-level extraction
rules live in [`config/extraction_map.yml`](config/extraction_map.yml);
institution identity (renames, footnote-marked names, a genuine publisher
typo) is resolved via [`config/institution_map.yml`](config/institution_map.yml).
`equitylens-normalize reconcile` runs four cross-source semantic checks
against the warehouse; the current production build produces 14 warnings and
zero errors, all explained as known publisher anomalies. See
[`docs/schema.md`](docs/schema.md) for the star schema, the three DoE
sheet-naming/layout eras discovered while building the extraction map, and
[`queries/sanity_checks.sql`](queries/sanity_checks.sql) for the discovery
queries and their findings.

## Day 1 completion status

The production ingestion run on 3 July 2026 first acquired 25 verified raw
artifacts: 23 Department of Education workbooks and two ABS SEIFA workbooks.
Final source resolution added five official Department completion cohort
workbooks for reference years 2018–2022 and the official QILT 2024 SES National
Report Tables archive. The completed Day 1 registry therefore contains 31
active sources and no `manual_resolution_required` entries.

The five pre-2023 completion files are cumulative cohort-analysis publications
ending in each stated reference year; they were not labelled annual Section 17
at publication time. QILT coverage is the public aggregate National Report
Tables archive, including institution-level confidence-interval worksheets. It
does not include respondent-level records or provider-portal data packages.

The completed ingestion was immediately rerun: all 31 sources returned
`unchanged`, the file and inventory manifests remained at 31 records, checksum
reconciliation found no mismatch, and no `.part` file remained.

## Ingestion guarantees

- Sources are allow-listed in [`config/sources.yml`](config/sources.yml) and
  must use HTTPS and authoritative publisher hosts.
- Downloads stream to a unique `.part` file and are validated before promotion.
- HTML error pages, empty files, format mismatches, corrupt XLSX containers,
  and oversized responses are rejected.
- Raw artifacts are content-addressed, made read-only, and never overwritten.
- SHA-256 deduplication makes repeat runs idempotent.
- Changed publisher content creates a new version linked to its predecessor.
- Source metadata, HTTP evidence, file provenance, and workbook structure are
  recorded separately.

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

# Inspect governed sources
equitylens-ingest list --include-inactive

# Ingest all active sources
equitylens-ingest ingest --all

# Target a publisher, section, year, or combination
equitylens-ingest ingest --publisher "Department of Education" --section 15 --year 2024

# Build the DuckDB warehouse from the raw corpus
equitylens-normalize build

# Run cross-source reconciliation checks against the warehouse
equitylens-normalize reconcile

# Build the versioned calibration target set
equitylens-calibrate targets

# Generate the synthetic commencing cohort (baseline vs. raked)
equitylens-synthesize --targets data/calibration/targets_v1_2023ref.json baseline
equitylens-synthesize --targets data/calibration/targets_v1_2023ref.json raked

# Quality gate
ruff check .
ruff format --check .
pytest
```

Runtime outputs are written beneath `data/` and excluded from Git. The source
registry, code, tests, config, and empty directory markers remain version
controlled.

## Runtime outputs

```text
data/
├── raw/<publisher>/<dataset>/<year>/<source_id>/<sha256>__<source_id>.<ext>
├── manifests/source_manifest.json
├── manifests/file_manifest.jsonl
├── inventory/workbook_inventory.jsonl
└── warehouse/equitylens.duckdb
```

See [the ingestion design](docs/ingestion_foundation.md), [source resolution
notes](docs/source_resolution.md), [the normalisation/warehouse
schema](docs/schema.md), and [contribution workflow](CONTRIBUTING.md).

Phase 2 stops at a tested, reconciled warehouse. It does not perform synthetic
cohort generation, calibration, risk scoring, evaluation, or Power BI
development.
