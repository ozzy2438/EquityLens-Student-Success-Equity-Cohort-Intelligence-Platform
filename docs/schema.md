# Normalisation and warehouse schema

## Scope

Phase 2 turns the 31 immutable raw workbooks from Phase 1 into a tested
`institution x year x equity_group x metric` DuckDB warehouse. It normalises
Department of Education Sections 11, 15, 16, and 17, QILT's Student Experience
Survey, and ABS SEIFA into a common long/tidy shape, resolves institution
identity across renames and footnote-marked names, and runs cross-source
reconciliation checks as the phase's actual quality gate. It does not perform
synthetic cohort generation, calibration, or analysis -- that begins in Phase 3
once this warehouse is stable (see "Phase 3 gate" below).

## Package layout

`src/equitylens_normalization/` is a sibling package to `equitylens_ingestion`,
not an extension of it: ingestion acquires bytes and never interprets them;
normalisation's whole job is interpretation, with a different dependency
footprint (pandas/duckdb) and failure mode (a bad institution alias should
fail the *normalize* build, never the *ingest* one).

- `extraction_map.py` / `institution_map.py`: strict loaders for
  `config/extraction_map.yml` and `config/institution_map.yml`, mirroring
  `equitylens_ingestion.registry`'s validation style.
- `readers/grid_reader.py`: a thin `pandas.read_excel(..., header=None,
  dtype=object)` wrapper shared by `.xls`, `.xlsx`, and zip-contained
  workbooks (QILT). Reads raw cell grids; does no interpretation.
- `normalizers/`: one module per source family (`doe_s11`, `doe_s15`,
  `doe_s16`, `doe_s17`, `qilt_ses`, `abs_seifa`), plus `_shared.py` for
  suppression parsing, footnote stripping, row-grouping, and SEIFA-vintage
  parsing reused across them.
- `warehouse.py`: the DuckDB DDL and a full `CREATE OR REPLACE` rebuild loader
  (normalisation is a pure function of immutable raw files + versioned
  config, so a full rebuild is simpler and safer than incremental upsert).
- `reconciliation.py`: cross-source semantic checks, the actual quality gate
  of this phase.
- `cli.py`: `equitylens-normalize build` / `equitylens-normalize reconcile`.

## The three DoE sheet-naming/layout eras (confirmed, not assumed)

Verified against the real 31 workbooks -- table numbers and sheet names do
**not** stay stable across years, and the boundary years differ per section:

| Section | Pseudo-header, single column (`.xls`) | Explicit State\|Institution columns | 2024 restructure |
| --- | --- | --- | --- |
| 11 (enrolment equity) | 2018-2019 | 2020-2023 | Institution table moves 11.3 -> 11.5; drops the postcode-based Low SES measure in favour of SA1-only; "Indigenous" relabelled "First Nations" |
| 15 (attrition/retention/success) | 2018-2019 | 2020-2024 | At 2023, DoE **swaps** the position of the Retention and Success tables within the section (retention 15.7->15.4, success 15.4->15.7) -- table *number* is not a stable identity |
| 16 (equity performance) | 2018-2022 (bare `1a` sheet names, even after S11/S15 had already moved to `.xlsx`) | 2023-2024 (`16.1a` in 2023, `16.1` in 2024) | Flat `Group`/`Category` columns replace the single-column pseudo-header layout starting 2023 |
| 17 (completion cohort) | 2018-2022 historical "Completion Rates Cohort Analyses" publications use sheet names `T1`-`T12` (a *third*, independent naming convention); 2023 uses `17.1`-`17.12` with the same grid shape | -- | 2024 restructures entirely to an already-tidy per-row layout (`17.3`) consolidating all three tracking windows (4/6/9-year) into one sheet; `17.1`/`17.2` are national demographic breakdowns with no per-institution rows |

Section 16 institution rows carry **no per-row state column at all** in either
era -- a `Group` column stacks `Australia` / `State and Territory` / `Higher
Education Institution` pseudo-header blocks; `state` for S16 facts is resolved
via `dim_institution`, never read from the sheet.

New publication years are a pure `config/extraction_map.yml` data addition as
long as the new year reuses an already-modelled `header_style`; a genuine
structural change (like 2024's S17 restructure) needs one new `header_style`
value plus one new normalizer branch.

## Deliberate scope cuts (disclosed, not silent)

- **QILT**: only university-level, single-latest-year (`_1Y_INST_CI`) sheets
  are loaded into `fact_ses_experience`. QILT's NUHEI-level sheets list ~100
  small colleges with no DoE counterpart and no bearing on ACU peer
  benchmarking; multi-year trend sheets (`17-YY`, `2YD`, `2YP`) are a
  different grain than this fact's single-year rows.
- **Section 17, 2024**: only the tidy `17.3` (State|Institution-level) sheet
  is loaded. `17.1`/`17.2` are national demographic/NUHEI breakdowns with no
  per-institution rows.
- **Institution alias coverage** is scoped to Table A/B universities (the 44
  entries in `config/institution_map.yml`, including one now-merged
  institution, Australian Maritime College, and one genuine publisher typo,
  "Curtin Universityy", both confirmed empirically). DoE institution tables
  never break out individual NUHEIs -- they appear only as an aggregate
  "Non-University Higher Education Institutions" rollup row, which
  normalizers exclude from per-institution facts rather than resolving.

## Cross-era metric- and equity-group-naming drift (found and fixed)

Four real naming inconsistencies were found and fixed while building the
warehouse. All four are the same underlying failure mode -- the same fact
published under two different labels across years, silently splitting one
time series into two incomplete ones -- and none were visible from reading
the code; each was only caught by directly querying the warehouse for a
specific institution across years and noticing either duplicate rows
(dedup-key drift) or a time series that inexplicably stopped or started
mid-history (label drift):

- Section 16's first table is "access_numbers" in every year's title, but was
  initially mislabelled `commencing_domestic_students` for 2024 while
  extracting -- fixed by standardising the `metric` value across all years.
- Section 17's `is_annual_release` flag is *publication* metadata (whether a
  file was the true annual release or a historical cumulative republication),
  not a *fact-identity* dimension -- it was initially stored in
  `LongRecord.dimensions`, which participates in the deduplication key,
  so it silently prevented deduplication between the 2022 historical and 2023
  annual publications of the same 2013-2015 cohort figures. It now lives in
  a separate `LongRecord.metadata` dict that is *not* part of the dedup key.
- Section 16's equity-group column headers changed wording twice:
  `"Indigenous"` (pre-2020) vs `"First Nations"` (2020+), and
  `"Domestic National Total"` (pre-2023) vs `"All Domestic"` (2023+).
  Confirmed as the same underlying series, not a definitional change, by
  checking ACU's overlapping years directly: 2015-2019 access numbers under
  `"Indigenous"` (170, 223, 203, 189, 158) are byte-identical to the same
  years reported under `"First Nations"` in later publications. Before the
  fix (`doe_s16._EQUITY_GROUP_ALIASES`), querying `first_nations` alone
  returned no data before 2020 even though the numbers existed under
  `indigenous` -- exactly the kind of gap that would have silently starved a
  Phase 3 calibration target of eight years of history.
- Section 16 headers with a **comma-separated** footnote reference, e.g.
  `"First Address Regional(d,e)"`, were not being stripped at all: the
  original `strip_footnote_markers` regex only matched a single token with
  no internal punctuation, so `"(d,e)"` survived into the slug and produced
  a spurious `first_address_regional_d_e` sitting alongside the real
  `first_address_regional` from years whose footnote lettering happened to
  strip cleanly. Fixed by extending the regex to accept comma-separated
  tokens inside the parentheses.

Both label-drift bugs are now covered by regression tests
(`tests/test_doe_s16.py::test_legacy_equity_group_labels_are_canonicalised`,
`::test_comma_separated_footnote_markers_are_stripped_from_equity_labels`).

## Deduplication across overlapping publications

DoE's wide-year tables are cumulative: every publication re-reports the
entire history back to a fixed base year (e.g. `doe_s15_2024`'s attrition
sheet reports 2005-2023, not just 2024). Naively loading every source file
would multiply most fact rows by however many years' publications cover that
row. `warehouse.deduplicate_overlapping_publications` collapses records to
one row per natural key (`target_fact`, `institution_id`, `year`,
`equity_group`, `metric`, `metric_definition`, plus whatever `dimensions`
distinguish that fact family), keeping the version from the highest
publication year each time (parsed from the trailing 4 digits of `source_id`).
This is why `equitylens-normalize build` reports both a "normalized" and a
smaller "loaded after deduplication" count.

## Star schema

`data/warehouse/equitylens.duckdb`, git-ignored like everything else under
`data/`, rebuilt from scratch on every `equitylens-normalize build`.

### Dimensions

- **`dim_institution`**: one row per canonical institution (44 rows: Table
  A/B universities + one merged historical institution). `peer_group_id`
  is a plain config tag (`config/institution_map.yml`), not a code
  concept -- trivial to revise without touching normalizer logic. See the
  "peer group" caveat below.
- **`dim_equity_group`**: one row per equity metric category observed across
  all loaded facts.
- **`dim_year`**: one row per reference year; `is_completion_cohort_only`
  flags years that only ever appear as the *final* year of a historical
  cumulative cohort-analysis publication (2018-2022 S17), not as a genuine
  annual snapshot year.

### Facts

- **`fact_enrolment_equity`** (Section 11) -- grain: institution x year x
  equity_group x metric x metric_definition.
- **`fact_retention_attrition`** (Section 15) -- grain: institution x year x
  metric x metric_definition. `equity_group_id` is fixed at
  `'not_disaggregated'`: S15 institution tables carry no equity split.
- **`fact_equity_performance`** (Section 16) -- grain: institution x year x
  equity_group x metric x metric_definition. No `state` column (see above).
  Three metrics are loaded: `access_numbers` (headcount by equity group,
  Table 16.1/16.1a), `retention_rate` (Table 16.6/16.8, "New Normal Retention
  Rate" pre-2023 and "Provider Retention Rate" 2023+ -- confirmed the same
  calculation via identical overlapping-year values, harmonised to one
  metric name), and `success_rate` (Table 16.8/16.10, same pattern). These
  two rate tables were added after Phase 2's initial cut, which had only
  loaded the headcount table -- Phase 3's calibration target contract needed
  equity-disaggregated outcome rates, not just enrolment counts, and their
  absence was caught by checking the target contract against the warehouse
  before writing it rather than assuming coverage.
- **`fact_completion_cohort`** (Section 17) -- grain: institution x
  cohort_end_year x tracking_window_years x metric x metric_definition.
  `is_annual_release` distinguishes the true 2023/2024 annual releases from
  the 2018-2022 cumulative cohort-analysis publications feeding the same
  rows.
- **`fact_seifa`** (ABS SEIFA) -- grain: geo_level x geo_code x year x
  index_family. `is_low_ses_calibration_target` flags the **Index of
  Education and Occupation** family specifically -- DoE's own Section 11
  footnote defines "Low SES" as the bottom 25% of that index, and only that
  index, not the other three (IRSD, IRSAD, IER) reported in the same sheet.
- **`fact_ses_experience`** (QILT) -- grain: institution x year x level x
  provider_type x year_scope x focus_area, with `value`/`ci_low`/`ci_high`
  split from QILT's packed `"83.6 (82.8, 84.3)"` cell strings.

All facts carry `source_id`/`source_sheet` for provenance back to
`data/manifests/file_manifest.jsonl`.

## ACU peer group -- an open question, not a settled design

`config/institution_map.yml` seeds `peer_group_id: acu_peer_regional` for ACU
plus Charles Sturt, University of Southern Queensland, University of New
England, Avondale, and Federation University -- a reasonable-looking
"regional/mission-aligned" set chosen before the data was queried. Query 2 in
`queries/sanity_checks.sql` shows this set does not actually cluster on the
axis that matters for equity benchmarking (Low-SES enrolment share): ACU sits
well below all five of its assigned peers on that measure. This is disclosed
here deliberately rather than fixed silently -- picking a peer set is a real
analytical decision that Phase 3 should revisit using the equity-share data
itself, not sector reputation. The tag is plain YAML, so revising it touches
no code.

## Coverage check for Phase 3: `equity_group x institution_type x year`

Before Phase 3 calibration starts, its actual query shape --
`equity_group x institution_type x year` -- was checked directly against the
built warehouse rather than assumed from the scope-cut list above. Two things
came out of that check, one confirming the scope cuts are safe and one real
gap the scope cuts did **not** cause:

- **The disclosed scope cuts (QILT NUHEI/trend sheets, S17 2024 national
  breakdowns) do not touch this intersection.** Every scope cut removes rows
  that were never institution x equity_group x year in the first place
  (QILT NUHEI rows have no DoE counterpart to calibrate against; S17's
  national breakdowns have no institution axis at all). None of them reduce
  coverage for `university`-type institutions across any equity group or
  year that DoE actually published.
- **`institution_type = 'nuhei'` coverage is a genuine, unfixable gap, but it
  is a gap in what DoE publishes, not in what this phase extracted.** Only
  one NUHEI (Batchelor Institute of Indigenous Tertiary Education) ever
  appears as an individually-identified institution in Section 11/16 --
  every other NUHEI is folded into the "Non-University Higher Education
  Institutions" rollup row that normalizers deliberately exclude from
  per-institution facts (see "Deliberate scope cuts" above). Batchelor
  Institute's own row is extremely sparse once it is there: most
  equity-group x year cells are `NULL` or `0` rather than a real reported
  count (verified directly: of Batchelor's ~90 enrolment-equity cells across
  2018-2024, the large majority are `NaN`). **Practical implication for
  Phase 3: any calibration target sliced by `institution_type = 'nuhei'`
  cannot be estimated from this warehouse's per-institution facts.** If
  Phase 3 needs an equity profile for NUHEIs at all, it will need either a
  sector-level NUHEI aggregate (available in the S11/S16 rollup rows this
  phase currently discards) or a different data source -- not a per-NUHEI
  breakdown, which DoE simply does not publish at this grain.

## Section 11 <-> Section 16 base-count reconciliation, confirmed by year

Since Phase 3's calibration targets (equity ratios, attrition probabilities)
are pulled directly from Sections 11 and 16, the base-count agreement between
them was re-verified per year, not just as an aggregate warning count, before
treating the warehouse as calibration-ready:

| Year | Institutions compared | Flagged (>10% diff) | Avg. disagreement |
| --- | --- | --- | --- |
| 2018 | 42 | 0 | 0.0% |
| 2019 | 42 | 0 | 0.0% |
| 2020 | 42 | 0 | 0.0% |
| 2021 | 42 | 0 | 0.0% |
| 2022 | 42 | 0 | 0.0% |
| 2023 | 43 | 0 | 0.0% |
| 2024 | 43 | 0 | 0.0% |

**All seven years now agree exactly.** This table originally showed 10
flagged institutions and 7.7% average disagreement in 2023, attributed at
the time to a DoE footnote about unique-student-count methodology. That
explanation turned out to be wrong: the real cause was a column-index bug in
the 2023 Section 11 extraction rule (see "Current findings" below), and once
fixed the 2023 column agrees with every other year. This is the actual
evidence that Section 11 and Section 16 are safe to draw calibration targets
from -- not just that the reconciliation check exists, but that it passes
cleanly across all seven years once the underlying extraction is correct.

## Reconciliation: the actual quality gate

`data/raw/` is git-ignored and absent in CI, so the semantic reconciliation
checks that gate every PR run against small fixture workbooks built in-memory
with `openpyxl` (`tests/test_doe_*.py`, `tests/test_qilt_ses.py`,
`tests/test_abs_seifa.py`) and a fixture DuckDB (`tests/test_reconciliation.py`)
-- mirroring the existing "live smoke tests are operational, not a merge
gate" split already documented in `docs/ingestion_foundation.md`. Running
`equitylens-normalize build && equitylens-normalize reconcile` against the
real 31-file corpus is a separate, non-gating operational check; that is
where the findings recorded in `queries/sanity_checks.sql` were produced.

Four checks run via `reconciliation.run_all_checks`:

1. **`rate_bounds`** (error severity): flags any retention/attrition/success/
   completion value outside [0, 100].
2. **`year_over_year_jump`** (warning): flags an institution x metric series
   with a >15 percentage-point swing between consecutive years.
3. **`retention_vs_completion_plausibility`** (warning): flags a commencing
   cohort with >=85% retention alongside a <=25% four-year completion rate
   for the same cohort -- filtered to `metric = 'completion_rate'`
   specifically (an earlier version of this query omitted that filter and
   was accidentally comparing retention against the `never_came_back` /
   `re_enrolled_dropped_out` outcome columns instead, which produced ~80
   false-positive findings for nearly every institution; caught by
   `tests/test_reconciliation.py::test_check_retention_vs_completion_ignores_other_metrics`,
   a regression test written specifically for this bug).
4. **`enrolment_vs_performance_base_counts`** (warning): flags institution x
   year pairs where Section 11's commencing domestic count and Section 16's
   base count disagree by more than 10% -- filtered to `p.metric =
   'access_numbers'` specifically. The same failure mode as check 3 recurred
   here when `retention_rate`/`success_rate` were added to
   `fact_equity_performance`: both also carry a row under
   `equity_group_id = 'all_domestic'` (their own base for computing a rate,
   e.g. 86.85), and without the metric filter the check briefly compared
   Section 11 headcounts (e.g. 1000 students) against those percentages as
   if they were the same kind of quantity, producing 546 findings instead of
   10. Caught immediately by rerunning reconciliation after adding the new
   tables rather than assuming the existing check still applied cleanly; the
   fix is covered by
   `tests/test_reconciliation.py::test_check_enrolment_vs_performance_base_counts_ignores_rate_metrics`.

### Current findings against the real corpus (2026-07-04 build)

14 warnings, 0 errors:

- 14 year-over-year jumps, all attributable to genuine publisher events
  already documented elsewhere in this repo or in the source data itself:
  Torrens University's 2015/2016 volatility (small Table B cohort in its
  early years as a Table B provider), Avondale's 2022->2023 jump (DoE S16
  2023 footnote (h): "Avondale University became a Table B provider in 2023.
  Prior to this, Avondale was counted in the NUHEI data" -- so its
  institution-level series genuinely starts in 2023, this is not a data
  error), Notre Dame's 2005/2006 zero-then-real-value pattern (an early
  reporting-coverage gap), Australian Maritime College's 2007 jump (matches
  the "merged into University of Tasmania from 2008" footnote already in
  `config/institution_map.yml`), and University of Divinity's 2006 swing (a
  very small commencing cohort, where a handful of students moves the rate
  by double digits).
- `enrolment_vs_performance_base_counts` now produces **zero** findings in
  every year. An earlier version of this document recorded 10 findings, all
  in 2023, and attributed them to DoE S16 2023 footnote (g) ("totals
  represent the unique student count ... may be less than the sum of all
  equity groups"). **That explanation was wrong and has been corrected.**
  While grounding the Phase 3 calibration target contract in real numbers
  (see `docs/calibration_targets.md`), ACU's 2023 `remote_first_address`
  enrolment count came back as ~10,000 -- larger than the institution's
  entire commencing cohort, an impossible value for a "first address in a
  remote area" subgroup. The actual cause was a column-index bug in
  `config/extraction_map.yml`'s `doe_s11_2023` rule: the postcode-based Low
  SES column was dropped from Section 11's table starting in **2023**, not
  2024 as originally assumed when that rule was copy-templated from
  2020-2022, silently shifting every subsequent equity column (including
  `all_students`) over by one. Once fixed, both the implausible value and
  all 10 reconciliation findings disappeared together -- strong evidence the
  footnote (g) explanation had been a plausible-sounding but incorrect
  post-hoc story for what was actually a parsing defect. The footnote (g)
  effect may still exist in the data at a level below the check's 10%
  threshold; it just was not the cause of these particular findings. This is
  recorded here deliberately as a caution: a reconciliation check passing or
  a citable-sounding footnote is not proof of correctness by itself -- the
  bug was only caught by independently cross-checking a specific number
  against plausibility, not by any automated check in this repository.

## Phase 3 gate

Phase 3 (synthetic cohort calibration) should not start until:

1. `pytest` is green, including the reconciliation fixture tests
   (`ruff check .`, `ruff format --check .`, `pytest` all pass locally and in
   CI).
2. `equitylens-normalize build` completes against the real 31-file corpus
   with zero institution-alias failures.
3. `equitylens-normalize reconcile` against the real warehouse produces only
   findings explicitly documented above as known, explained anomalies --
   never an unexplained `error`-severity finding.
4. This document's grain definitions are treated as stable: Phase 3's
   calibration queries should be written against the grains above, not
   against a schema still expected to change shape.

All four conditions hold as of this document.
