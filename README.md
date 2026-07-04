# EquityLens

EquityLens is a student-success and equity cohort intelligence platform. This
repository currently implements the governed ingestion foundation (Day 1) and
the normalisation/warehouse layer (Phase 2) only: synthetic cohort
calibration, risk scoring, evaluation, and dashboards are intentionally out of
scope.

## Phase 2 completion status

`equitylens-normalize build` turns the 31 raw workbooks into a tested
`institution x year x equity_group x metric` DuckDB warehouse
(`data/warehouse/equitylens.duckdb`, git-ignored). Sheet-level extraction
rules live in [`config/extraction_map.yml`](config/extraction_map.yml);
institution identity (renames, footnote-marked names, a genuine publisher
typo) is resolved via [`config/institution_map.yml`](config/institution_map.yml).
`equitylens-normalize reconcile` runs four cross-source semantic checks
against the warehouse; the current production build produces 24 warnings and
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
