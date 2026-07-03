# Governed ingestion foundation

## Scope

Day 1 establishes a reproducible acquisition boundary for Department of
Education Selected Higher Education Statistics, QILT Student Experience Survey
data, and ABS SEIFA. It does not clean, normalize, join, or analyse source data.
Keeping acquisition separate from transformation preserves publisher evidence
and makes later findings reproducible.

The final Day 1 registry has 31 active public artifacts. The first production
run acquired 25 files; source finalisation added five historical Department
completion cohort workbooks and one QILT SES report-table archive. There are no
unresolved registry entries, but access-controlled or respondent-level QILT
data remains outside scope.

## Control flow

1. Parse and validate `config/sources.yml`.
2. Select active sources, optionally filtering publisher, section, and year.
3. Stream each response into `data/raw/.staging/*.part` while calculating SHA-256.
4. Enforce status, redirect-host, byte-limit, MIME/sniff, and container checks.
5. Inspect workbook sheets without changing workbook bytes. For a governed ZIP,
   validate safe member paths and inventory contained XLSX workbooks in memory.
6. Under an inter-process lock, compare the checksum with prior versions.
7. Atomically promote new bytes to a content-addressed path and set mode `0444`.
8. Append one file event and one workbook-inventory event. Identical reruns append
   nothing.

Batch failures are isolated: one failed source does not hide outcomes for other
sources, but the command exits non-zero if any selected source fails.

## Manifest semantics

`source_manifest.json` is a replaceable snapshot of the governed registry. Its
`registry_sha256` fingerprints the canonical source list.

`file_manifest.jsonl` is append-only. Each record captures:

- source identity, publisher, dataset, section, and reference year;
- authoritative publication and resolved download URLs;
- publisher creation/modification metadata when published;
- ingestion timestamp, SHA-256, size, format, and immutable relative path;
- response content type, ETag, Last-Modified, and resolved URL;
- predecessor record/checksum when publisher bytes change.

`workbook_inventory.jsonl` shares the file record ID and checksum, and records
sheet order, name, visibility, row count, and column count. It is structural
evidence, not a transformed dataset.

## Production ingestion evidence

The final local production run on 3 July 2026 recorded:

- 31 immutable raw artifacts: 28 Department, two ABS, and one QILT;
- 31 unique file-manifest records and 31 inventory records;
- five newly resolved historical completion XLSX workbooks;
- one QILT ZIP containing XLSX and ODS report tables, with 172 XLSX sheets
  inventoried;
- zero checksum mismatches, missing manifest paths, permission failures, or
  residual `.part` files;
- 31 `unchanged` outcomes on the immediate full rerun.

These operational files remain under `data/` and are Git-ignored by design.
The repository tracks the registry, controls, tests, and documentation rather
than committing publisher data into source control.

## Threat and failure controls

| Risk | Control |
| --- | --- |
| Guessed or third-party source | Explicit publication/download URLs and host allow-list |
| Partial download exposed as raw | Unique `.part` file plus atomic promotion |
| Error page saved as Excel | MIME and byte-prefix HTML rejection |
| Extension/content mismatch | XLS OLE signature or XLSX ZIP/member/integrity checks |
| Unsafe or irrelevant archive | ZIP traversal rejection, integrity test, and required tabular member |
| Memory/disk exhaustion | Declared and streamed 150 MiB limits |
| Silent publisher correction | Content-addressing plus predecessor link |
| Duplicate rerun | Per-source SHA-256 lookup under a file lock |
| Concurrent writers | `flock`, exclusive staging creation, atomic rename, fsync |
| Accidental raw mutation | Content-addressed name, mode `0444`, no overwrite path |

File permissions are a guardrail, not a complete write-once storage control.
Production deployment should additionally use object-storage versioning,
retention policies, restricted service identities, encryption, and centralized
audit logs.

## Testing strategy

Unit tests use generated workbooks and mocked HTTP responses; CI never depends
on publisher availability. Tests cover registry safety, filtering, HTML and
format rejection, redirect control, size limits, hashing, cleanup, inventory,
deduplication, version lineage, immutable paths, manifests, logging, and CLI
exit behaviour. Live publisher smoke tests are operational checks and are not a
merge gate.

## Day 1 boundary

Completion means authoritative acquisition, immutable storage, provenance,
checksum verification, structural inventory, automated tests, and repeat-run
evidence. Normalisation, cleaning, schema harmonisation, DuckDB, analytical
models, synthetic cohorts, Power BI, and outcome interpretation begin after
Day 1 and are intentionally absent here.
