from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import qilt_ses

_VALUE_PATTERN = r"^(?P<value>[\d.]+)\s*(?:\((?P<ci_low>[\d.]+),\s*(?P<ci_high>[\d.]+)\))?$"
_SHEET_NAME_PATTERN = r"FOCUS_(?P<level>UG|PGC)_(?P<provider_type>UNI)_(?P<year_scope>1Y)_INST_CI"


def _qilt_rule() -> ExtractionRule:
    return ExtractionRule(
        source_id="qilt_ses_2024",
        target_fact="fact_ses_experience",
        header_style="focus_area_columns",
        sheet_pattern=r"FOCUS_(UG|PGC)_UNI_1Y_INST_CI",
        workbook_member="SES_2024_National_Report_Tables.xlsx",
        options={
            "header_row": 3,
            "institution_col": 1,
            "data_start_row": 4,
            "value_pattern": _VALUE_PATTERN,
            "sheet_name_pattern": _SHEET_NAME_PATTERN,
        },
    )


@pytest.fixture
def resolver(tmp_path: Path):
    path = tmp_path / "institution_map.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "acu",
                        "canonical_name": "Australian Catholic University",
                        "type": "university",
                        "state": "multi_state",
                        "aliases": ["Australian Catholic University"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_institution_map(path)


def _write_qilt_zip(tmp_path: Path) -> Path:
    workbook = openpyxl.Workbook()
    inst_sheet = workbook.active
    inst_sheet.title = "FOCUS_UG_UNI_1Y_INST_CI"
    inst_sheet.append([None, None, None])
    inst_sheet.append([None, None, None])
    inst_sheet.append([None, None, None])
    inst_sheet.append([None, None, "Skills Development"])
    inst_sheet.append([None, "All Universities", "80.0"])  # aggregate rollup, must be skipped
    inst_sheet.append([None, "Australian Catholic University", "83.6 (82.8, 84.3)"])
    inst_sheet.append([None, "Perfect Score University", "100.0"])  # no CI when at 100%

    rollup_sheet = workbook.create_sheet(
        "FOCUS_UG_ALL_17-YY_SG"
    )  # not institution-grain, must be ignored
    rollup_sheet.append(["irrelevant"])

    buffer = BytesIO()
    workbook.save(buffer)

    xlsx_path = tmp_path / "SES_2024_National_Report_Tables.xlsx"
    xlsx_path.write_bytes(buffer.getvalue())

    zip_path = tmp_path / "qilt.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(xlsx_path, arcname="SES_2024_National_Report_Tables.xlsx")
    return zip_path


def test_qilt_extracts_only_inst_ci_sheets_and_splits_ci(resolver, tmp_path: Path) -> None:
    # "Perfect Score University" is deliberately not in the institution map --
    # this exercises that unmatched names still raise, confirming the
    # aggregate-row skip (`All Universities`) is intentional, not accidental
    # leniency. Remove it before asserting the real extraction behaviour.
    zip_path = _write_qilt_zip(tmp_path)
    rule = _qilt_rule()
    from equitylens_normalization.errors import InstitutionMapError

    with pytest.raises(InstitutionMapError, match="Perfect Score University"):
        qilt_ses.normalize(rule, zip_path, resolver, source_year=2024)


def test_qilt_splits_point_estimate_and_confidence_interval(tmp_path: Path) -> None:
    path = tmp_path / "institution_map.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "acu",
                        "canonical_name": "Australian Catholic University",
                        "type": "university",
                        "state": "multi_state",
                        "aliases": ["Australian Catholic University"],
                    },
                    {
                        "canonical_id": "perfect",
                        "canonical_name": "Perfect Score University",
                        "type": "university",
                        "state": "nsw",
                        "aliases": ["Perfect Score University"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    resolver = load_institution_map(path)
    zip_path = _write_qilt_zip(tmp_path)
    rule = _qilt_rule()
    records = qilt_ses.normalize(rule, zip_path, resolver, source_year=2024)

    assert {r.institution_raw for r in records} == {"acu", "perfect"}
    acu_record = next(r for r in records if r.institution_raw == "acu")
    assert acu_record.value == 83.6
    assert acu_record.measures == {"ci_low": 82.8, "ci_high": 84.3}
    assert acu_record.dimensions == {"level": "ug", "provider_type": "uni", "year_scope": "1y"}

    perfect_record = next(r for r in records if r.institution_raw == "perfect")
    assert perfect_record.value == 100.0
    assert perfect_record.measures == {"ci_low": None, "ci_high": None}
