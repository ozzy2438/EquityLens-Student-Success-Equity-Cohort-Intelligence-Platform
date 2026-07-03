# Source resolution register

Resolution was performed from authoritative publisher publication pages on
3 July 2026. Direct URLs were copied from those pages; year substitution was
not used as evidence.

## Department of Education

Sections 11, 15, and 16 have verified annual publication pages and download
links for 2018–2024. The publisher used legacy `.xls` workbooks through 2020
and `.xlsx` from 2021 onward. Annual Section 17 exists for 2023 and 2024.

The Department's archive confirms that completion rates moved into annual
Section 17 from 2023. For 2018–2022, it published separate cumulative cohort
analysis workbooks. Each configured `year` is the final reference year in the
official workbook title, not a claim that the historical file was originally
labelled Section 17.

| Registry year | Official publication | Published | Reference |
| --- | --- | --- | --- |
| 2018 | [Cohort Analysis, 2005–2018](https://www.education.gov.au/higher-education-statistics/resources/completion-rates-higher-education-students-cohort-analysis-2005-2018) | 28 August 2019 | D19/1363980 |
| 2019 | [Cohort Analysis, 2005–2019](https://www.education.gov.au/higher-education-statistics/resources/completion-rates-higher-education-students-cohort-analysis-2005-2019) | 8 September 2020 | D20/978562 |
| 2020 | [Cohort Analysis, 2005–2020](https://www.education.gov.au/higher-education-statistics/resources/completion-rates-higher-education-students-cohort-analysis-20052020) | 14 February 2022 | D22/70121 |
| 2021 | [Cohort Analysis, 2005–2021](https://www.education.gov.au/higher-education-statistics/resources/completion-rates-higher-education-students-cohort-analysis-20052021) | 9 February 2023 | Not supplied |
| 2022 | [Cohort Analysis, 2005–2022](https://www.education.gov.au/higher-education-statistics/resources/completion-rates-higher-education-students-cohort-analysis-20052022) | 18 December 2023 | D23/4870105 |

All five direct XLSX links were copied from their respective official pages,
activated, ingested, inventoried, and then verified as `unchanged` on rerun.

The source notes preserve the Department's warning that disability enrolments
and related 2020 indicators were affected by under-reporting during the TCSI
transition.

## QILT

The official [Student Experience Survey page](https://www.qilt.edu.au/surveys/student-experience-survey-%28ses%29)
publishes the 2024 SES National Report Tables as a 7.81 MB ZIP. The downloaded
archive contains `SES_2024_National_Report_Tables.xlsx` and an ODS equivalent.
The XLSX has institution-level confidence-interval worksheets such as
`FOCUS_UG_UNI_1Y_INST_CI`; inventory observed that sheet as 64 rows by 8
columns. The official ZIP is active and retained byte-for-byte as raw data.

This resolves the requested public institution-level aggregate tables. It does
not grant access to respondent-level survey records or institution data
packages described in the methodology; those are governed separately and are
outside the public Day 1 scope.

## Australian Bureau of Statistics

The official SEIFA 2021 release provides index workbooks for multiple
geographies. Postal Area and Statistical Area Level 2 workbooks are active
because they support the planned postcode/SA2 calibration use case. SEIFA is a
2021 Census product rather than an annual 2018–2024 series.

## Resolution outcome

The initial run downloaded 25 artifacts. Final resolution added five Department
completion workbooks and one QILT archive, bringing the governed raw set to 31
artifacts: 28 Department, two ABS, and one QILT. No configured source remains
`manual_resolution_required`.

“Resolved” applies only to the authoritative public aggregate artifacts named
above. Missing respondent-level or access-controlled data is not reconstructed,
mirrored, scraped from ComparED, or represented as public source coverage.

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
