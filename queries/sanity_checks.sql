-- Phase 2 discovery queries, run against data/warehouse/equitylens.duckdb after
-- `equitylens-normalize build`. Each query is followed by the real finding
-- observed against the 31-file production corpus (recorded here so it survives
-- warehouse rebuilds and becomes Phase 3 calibration input / interview material).
-- See docs/schema.md for grain definitions.

-- =============================================================================
-- Q1: ACU's Low-SES commencing-student share vs its own history (Section 11)
-- =============================================================================
select
    year_value,
    max(case when equity_group_id = 'low_ses_sa1' then value end) as low_ses_count,
    max(case when equity_group_id = 'all_students' then value end) as all_students,
    round(
        100.0 * max(case when equity_group_id = 'low_ses_sa1' then value end)
        / nullif(max(case when equity_group_id = 'all_students' then value end), 0),
        1
    ) as low_ses_share_pct
from fact_enrolment_equity
where institution_id = 'acu'
group by year_value
order by year_value;

-- FINDING: ACU's Low-SES (SA1) share of commencing domestic students sits in a
-- narrow 11.4-13.2% band from 2018-2024 (13.2% in 2018, dipping to 11.4% in
-- 2022, back to 12.1% in 2024) -- essentially flat, no clear trend either way
-- across the period covered.

-- =============================================================================
-- Q2: Sector-wide Low-SES share ranking, 2024 -- where does ACU actually sit?
-- =============================================================================
select
    institution_id,
    round(
        100.0 * max(case when equity_group_id = 'low_ses_sa1' then value end)
        / nullif(max(case when equity_group_id = 'all_students' then value end), 0),
        1
    ) as low_ses_share_pct
from fact_enrolment_equity
where year_value = 2024
group by institution_id
order by low_ses_share_pct desc
limit 10;

-- FINDING (interview-relevant): the 2024 leaders are CQUniversity (45.0%),
-- University of Southern Queensland (36.7%), James Cook (29.4%), and several
-- other regional Queensland/WA institutions -- ACU is NOT among the top-10
-- Low-SES-share institutions nationally, despite superficially resembling a
-- "regional/equity-mission" university. Its multi-campus metro footprint
-- (Sydney, Melbourne, Brisbane, Canberra, Ballarat) means its Low-SES share
-- (~12%) is closer to the sector middle than to CSU (25.3%) or UNE (25.9%),
-- both of which sit in `acu_peer_regional`. This is worth revisiting before
-- Phase 3: the interim peer group in institution_map.yml conflates "mission
-- similarity" with "equity-cohort composition similarity" -- they are not the
-- same axis, and a peer set built for benchmarking equity gaps should
-- probably be chosen by Low-SES/First-Nations/regional *share*, not by
-- sector reputation.

-- =============================================================================
-- Q3: SEIFA vintage transition, 2021 -- how much does the 2016->2021 SEIFA
-- revision move an institution's reported Low-SES count for the *same* year?
-- =============================================================================
select institution_id, year_value, equity_group_id, metric_definition, value
from fact_equity_performance
where institution_id = 'acu' and year_value = 2021 and equity_group_id like 'low_ses%'
order by metric_definition;

-- FINDING: ACU's 2021 Low-SES-by-SA1 count is reported as 1,411 under the
-- 2016 SEIFA boundaries and 1,241 under the 2021 SEIFA boundaries -- a 12%
-- swing from the geography revision alone, for the exact same students in
-- the exact same year. Any Phase 3 calibration target pulled from S16 must
-- pin a SEIFA vintage explicitly (this project standardises on 2021 SEIFA
-- wherever both are available) rather than silently mixing vintages across
-- years, which would look like a real equity trend but would actually be a
-- boundary-definition artifact.

-- =============================================================================
-- Q4: ACU completion rate by tracking window -- does the 4/6/9-year ordering
-- make logical sense (longer window => higher cumulative completion)?
-- =============================================================================
select cohort_end_year, tracking_window_years, value
from fact_completion_cohort
where institution_id = 'acu' and metric = 'completion_rate'
order by cohort_end_year, tracking_window_years;

-- FINDING: for every cohort year with all three windows available, 9-year
-- completion > 6-year > 4-year, as expected (e.g. the 2015-ending cohort:
-- 47.6% at 4 years, 68.3% at 6 years, 77.5% at 9 years) -- the star schema's
-- separate `tracking_window_years` grain is validated by this check, and the
-- retention_vs_completion_plausibility reconciliation check (docs/schema.md)
-- confirms no institution's high early retention pairs with an implausibly
-- low four-year completion once compared like-for-like.

-- =============================================================================
-- Q5: ACU vs its interim peer group on QILT overall student experience, 2024
-- =============================================================================
select i.institution_name, f.value, f.ci_low, f.ci_high
from fact_ses_experience f
join dim_institution i on i.institution_id = f.institution_id
where f.level = 'ug'
  and f.focus_area = 'quality_of_entire_educational_experience'
  and f.institution_id in ('acu', 'csu', 'une', 'usq', 'federation_university_australia', 'avondale_university')
order by f.value desc;

-- FINDING: ACU (80.5%, CI 79.7-81.3) sits second among its interim peer set,
-- behind Avondale (88.8%, a much smaller specialist institution with a
-- correspondingly wide CI) and ahead of UNE (79.5%), Federation (78.9%), and
-- USQ (72.3%). This is a plausible complement to the retention/completion
-- facts for a "does student experience track retention" cross-check in
-- Phase 3, since QILT is the only source in this warehouse with a genuine
-- experience/engagement signal rather than an outcome signal.

-- =============================================================================
-- Q6: ABS SEIFA structural sanity -- deciles must run cleanly 1-10
-- =============================================================================
select
    index_family,
    min(decile) as min_decile,
    max(decile) as max_decile,
    count(distinct decile) as distinct_deciles
from fact_seifa
where geo_level = 'poa'
group by index_family;

-- FINDING: all four index families (IRSD, IRSAD, IER, IEO) run cleanly from
-- decile 1 to 10 across all 2,628 postal areas with no gaps -- confirms the
-- two-row merged header was parsed correctly and no index family's
-- score/decile columns were swapped or misaligned.
