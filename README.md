# EquityLens

EquityLens is a student-success and equity cohort intelligence platform. This
repository currently implements the Day 1 governed ingestion foundation only:
analysis, student-level modelling, and dashboards are intentionally out of
scope.

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

# Quality gate
ruff check .
ruff format --check .
pytest
```

Runtime outputs are written beneath `data/` and excluded from Git. The source
registry, code, tests, and empty directory markers remain version controlled.

## Runtime outputs

```text
data/
├── raw/<publisher>/<dataset>/<year>/<source_id>/<sha256>__<source_id>.<ext>
├── manifests/source_manifest.json
├── manifests/file_manifest.jsonl
└── inventory/workbook_inventory.jsonl
```

See [the ingestion design](docs/ingestion_foundation.md), [source resolution
notes](docs/source_resolution.md), and [contribution workflow](CONTRIBUTING.md).

Day 1 stops at governed raw acquisition and structural inventory. It does not
perform normalization, cleaning, DuckDB modelling, risk scoring, evaluation,
or Power BI development.
