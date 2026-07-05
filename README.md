# EquityLens

EquityLens is a student-success and equity cohort intelligence platform. This
repository currently implements the governed ingestion foundation (Day 1),
the normalisation/warehouse layer (Phase 2), and the calibration target
contract plus synthetic population generation (Phase 3, Steps 0-2c) only:
outcome assignment, risk scoring, evaluation, and dashboards are
intentionally out of scope.

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
