# Source resolution register

Resolution was performed from authoritative publisher publication pages on
3 July 2026. Direct URLs were copied from those pages; year substitution was
not used as evidence.

## Department of Education

Sections 11, 15, and 16 have verified annual publication pages and download
links for 2018–2024. The publisher used legacy `.xls` workbooks through 2020
and `.xlsx` from 2021 onward. Annual Section 17 exists for 2023 and 2024.

The Department states that pre-2023 completion rates live in cumulative cohort
analysis publications. Mapping a cumulative publication to a single annual
Section 17 reference year would be misleading, so 2018–2022 entries are present
as `manual_resolution_required`. They do not run in the default active batch.

The source notes preserve the Department's warning that disability enrolments
and related 2020 indicators were affected by under-reporting during the TCSI
transition.

## QILT

QILT's official resource page exposes public reports, but resolution did not
identify a stable public institution-level SES data-table workbook. The 2024
SES entry is therefore `manual_resolution_required`. A maintainer must verify
an official download and review its dissemination conditions before activating
it. A report PDF or third-party reconstruction is not substituted for the
requested data resource.

## Australian Bureau of Statistics

The official SEIFA 2021 release provides index workbooks for multiple
geographies. Postal Area and Statistical Area Level 2 workbooks are active
because they support the planned postcode/SA2 calibration use case. SEIFA is a
2021 Census product rather than an annual 2018–2024 series.

## Activation checklist

To change an unresolved source to `active`:

1. Open its authoritative publication page.
2. Confirm licensing/access conditions and the resource's intended data type.
3. Copy the direct HTTPS download URL without constructing it from a pattern.
4. Add creation/modification date and file reference when supplied.
5. Add every legitimate redirect destination to `allowed_hosts`; do not use a
   wildcard.
6. Run targeted ingestion twice and verify the second result is `unchanged`.
7. Commit the registry change and provenance evidence through a pull request.
