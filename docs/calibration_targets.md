# Phase 3, Step 0 -- Calibration target contract

## Purpose

This document defines, before any synthetic-cohort code is written, exactly
which published marginals the ~20K-student synthetic commencing cohort must
match, at what tolerance, and what counts as pass/fail. Written after the
target is defined, a calibration always "succeeds" -- that is methodologically
worthless. This contract is the thing `calibration/validate.py` (Step 4) is
checked against; if a target changes, it changes here first, with a reason.

## Reference year: 2023

2023 is the only year in the warehouse where the three required marginal
families are **simultaneously** available at full institution coverage:

| Fact | Metric | Max year | Coverage at 2023 |
| --- | --- | --- | --- |
| `fact_enrolment_equity` (S11) | `commencing_domestic_students` | 2024 | 43 institutions |
| `fact_equity_performance` (S16) | `retention_rate` | **2023** | 43 institutions |
| `fact_equity_performance` (S16) | `success_rate` | 2024 | 43 institutions |
| `fact_seifa` (ABS) | `score`/`decile` (IEO) | 2021 (no more recent release) | 2,628 postal areas |

`retention_rate` caps at 2023 because DoE's retention calculation needs the
following year's re-enrolment data to compute -- the 2024 publication cannot
yet report 2024 commencing-cohort retention. Calibrating the synthetic
cohort's commencing year to 2023 (not 2024) is a direct consequence of this,
not an arbitrary choice: any later reference year would leave first-year
retention un-targetable at all, silently degrading the single most
important outcome signal for Phase 4's risk model. SEIFA (2021, quinquennial)
is the geography/socioeconomic layer and does not need to match the
commencing-cohort year.

## Target marginals and tolerances

Every target below was checked against the built warehouse (not assumed) as
part of writing this document; two of the numbers cited during that check
led to fixing a real bug (see "What checking this contract against real data
already caught," below) rather than being taken at face value.

### 1. Equity-group enrolment share (Section 11), tolerance ±1.0 percentage point

Grain: `equity_group x institution`, one target per equity group as a share
of that institution's `all_students`. ACU 2023, verified:

| Equity group | Count | Share of commencing domestic |
| --- | --- | --- |
| low_ses_sa1_first_address | 1,228 | 12.24% |
| regional_first_address | 1,206 | 12.02% |
| low_ses_sa1 | 1,200 | 11.96% |
| regional | 1,125 | 11.21% |
| disability | 704 | 7.02% |
| women_non_traditional_area | 379 | 3.78% |
| non_english_speaking_background | 342 | 3.41% |
| first_nations | 219 | 2.18% |
| remote | 35 | 0.35% |
| remote_first_address | 32 | 0.32% |

±1.0pp is tight relative to ACU's own year-to-year share drift (its Low-SES
SA1 share ranges 11.4-13.2% across 2018-2024, i.e. ~1.8pp of natural
variation across seven years) but appropriate here because the synthetic
cohort is calibrated to a single fixed year, not asked to reproduce a trend.

### 2. First-year attrition/retention, institution-type x equity-group intersection (Section 16), tolerance N-dependent

Grain: `equity_group x institution` (S16's `retention_rate`/`success_rate`
tables carry no separate `institution_type` axis beyond
university-vs-NUHEI, and NUHEI coverage is a hard data gap -- see below --
so in practice this target family is university-only). ACU 2023, verified:

| Equity group | Retention rate | Success rate |
| --- | --- | --- |
| all_domestic (base) | 82.91% | 90.51% |
| non_english_speaking_background | 84.32% | 88.17% |
| disability | 83.76% | 88.57% |
| regional | 81.77% | 92.10% |
| first_address_regional | 82.80% | 92.43% |
| low_ses_by_sa1 | 80.84% | 87.80% |
| first_address_low_ses_by_sa1 | 80.47% | 88.01% |
| first_nations | 77.85% | 85.68% |
| remote | 66.78% | 86.12% |
| first_address_remote | 68.91% | 83.62% |

**Tolerance is N-dependent, not a flat ±2pp**, because the underlying
publisher counts behind these rates vary enormously by equity group --
sector-wide 2023 average commencing counts range from 8,406 (`all_students`)
down to 83 (`remote`) and 90 (`remote_first_address`), with some
institutions reporting as few as 5 students in the smallest groups. A flat
tolerance is not meaningful when the target itself is a rate over a handful
of students. Bucket by the underlying Section 11 commencing count for that
institution x equity_group pair (`n`):

| `n` (commencing count) | Tolerance |
| --- | --- |
| n >= 200 | ±2.0pp (as originally proposed) |
| 50 <= n < 200 | ±4.0pp |
| 10 <= n < 50 | ±8.0pp |
| n < 10, or value suppressed (`< 5`) | **excluded from the pass/fail gate**; reported separately in the validation output, never silently dropped |

This mirrors the reconciliation layer's own finding in Phase 2: small
commencing cohorts (Divinity, Batchelor Institute) showed >15pp natural
year-over-year swings for exactly this reason -- a handful of students moves
a rate by double digits, and holding that to the same tolerance as a
200+-student intersection would either force the calibration to overfit
noise or fail the gate on a target that was never estimable to that
precision in the first place.

### 3. SEIFA (IEO) decile/quintile distribution, tolerance ±2.0 percentage points

Grain: national, population-weighted, from `fact_seifa` where
`is_low_ses_calibration_target = true` (the Index of Education and
Occupation family specifically -- see `docs/schema.md`). Target is the
population share falling in each SEIFA decile (or quintile, decile/2 rounded
up), used to calibrate the geographic/socioeconomic layer of each synthetic
student's assigned postcode, independent of institution. Verified
population-weighted decile distribution (POA level, 2021 SEIFA):

| Decile | Population | Share |
| --- | --- | --- |
| 1 (most disadvantaged) | 1,511,977 | 6.4% |
| 2 | 2,085,627 | 8.9% |
| 3 | 1,958,447 | 8.4% |
| 4 | 1,908,503 | 8.2% |
| 5 | 2,662,644 | 11.4% |
| 6 | 2,740,960 | 11.7% |
| 7 | 2,380,222 | 10.2% |
| 8 | 2,931,725 | 12.5% |
| 9 | 3,272,295 | 14.0% |
| 10 (least disadvantaged) | 3,914,636 | 16.7% |

Deciles are area-based (equal number of postal areas per decile by
construction), not population-based, which is exactly why the population
share per decile is uneven above -- this is expected and is the correct
distribution to calibrate against, not a defect.

### 4. Part-time enrolment ratio -- excluded from this contract

**Decision: dropped, not proxied.** No institution-level part-time/full-time
attendance split exists anywhere in Sections 11, 15, 16, or 17 -- the only
occurrence of a "Mode of Attendance" breakdown found in the full 31-file
corpus is Section 17 2024's national-level demographic tables (`17.1`),
which were already out of scope in Phase 2 because they carry no
institution axis at all. Getting this target would require ingesting a new
DoE section (likely Section 2 or 3, general enrolment characteristics),
which is outside this repository's current source registry
(`config/sources.yml`). Rather than proxy it with an unsourced national
constant, it is simply not a calibration target for this phase. If Phase 4
or later needs part-time status as a student-level feature, it should be
assigned from a documented literature assumption in `docs/assumptions.md`
(ACSES or similar), explicitly labelled as unvalidated against any published
institution-level marginal.

## Suppressed and small-N target handling

Where a Section 11/16 cell is suppressed (`< 5`) or absent for a specific
institution x equity_group x year combination needed as a target, Step 1
(`calibration/targets.py`) must not silently skip it or treat it as zero.
Policy:

1. If the equity group's institution-level value is suppressed but a
   higher-level marginal exists (e.g. the sector-wide or institution-type
   average for that equity group), impute from that marginal and set
   `imputed_target_flag = true` on the resulting target record.
2. The imputation source (which marginal, which year) is recorded alongside
   the flag, not just the boolean -- so `docs/calibration_targets.md` and the
   validation report can both point to where an imputed number actually came
   from.
3. Imputed targets are held to the *loosest* tolerance tier in the N-dependent
   table above regardless of what the (unknown, suppressed) true `n` might
   be, since imputation is itself an admission that the true small-N figure
   is not observable.
4. `calibration/validate.py`'s report (Step 4) must show `imputed_target_flag`
   as its own visible column -- a validation pass that quietly matched an
   imputed target is a materially weaker claim than matching an observed
   one, and the report should not obscure that difference.

## `institution_type` coverage limit (confirmed, not assumed)

Checked directly against the warehouse before writing this contract: only
one NUHEI (Batchelor Institute of Indigenous Tertiary Education) ever
appears as an individually identified institution in Sections 11/16, and its
own coverage is extremely sparse (most equity-group x year cells are
`NULL`). **No `institution_type = 'nuhei'` calibration target in this
contract can be estimated from this warehouse's per-institution facts.**
Phase 3's synthetic cohort should therefore be scoped to university-type
institutions (or ACU specifically), consistent with the whole project's
ACU-benchmarking framing; if a NUHEI comparison point is ever needed, it
would have to come from the sector-level NUHEI rollup row that Phase 2's
normalizers currently discard (see `docs/schema.md`, "Deliberate scope
cuts"), not from a per-institution breakdown DoE does not publish.

## What checking this contract against real data already caught

Writing this document required querying the warehouse for the exact numbers
above, and that process caught two real defects before any calibration code
was written:

1. **A missing S16 table.** Phase 2 had only extracted Section 16's headcount
   table (`access_numbers`); the equity-specific retention/success rate
   tables (16.6/16.8 pre-2024, 16.8/16.10 in 2024) were never loaded, so
   target family 2 above did not exist in the warehouse at all until they
   were added (see `docs/schema.md`, "Cross-era metric- and
   equity-group-naming drift"). Adding them reused the existing
   `s16_institution_block` normalizer and layout with no new code, and
   surfaced a second reconciliation-query bug (`enrolment_vs_performance_base_counts`
   briefly comparing headcounts against percentage rates because the new
   tables share the `all_domestic` equity-group label) that is now fixed and
   covered by a regression test.
2. **A column-index bug in the 2023 Section 11 rule.** ACU's 2023
   `remote_first_address` enrolment count came back as ~10,000 -- larger
   than the institution's entire commencing cohort -- while writing target
   family 1 above. The postcode-based Low SES column had actually been
   dropped from Section 11 starting in **2023**, one year earlier than
   assumed when that extraction rule was copy-templated from 2020-2022,
   silently shifting every later equity column over by one. Fixing it also
   resolved 10 reconciliation findings that had previously been (incorrectly)
   attributed to a DoE footnote about unique-student-count methodology --
   see `docs/schema.md` for the corrected explanation. Neither defect was
   caught by an automated check; both were caught by an implausible number
   surfacing while grounding this contract in real data, which is the whole
   reason Step 0 comes before Step 1's code.
