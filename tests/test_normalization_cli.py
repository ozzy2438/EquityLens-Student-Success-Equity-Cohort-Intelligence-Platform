from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest
import yaml

from equitylens_normalization.cli import main


@pytest.fixture
def project(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    (data_root / "manifests").mkdir(parents=True)
    (data_root / "raw").mkdir(parents=True)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "1"
    sheet.append(["State", "Institution", "NESB", "All Students"])
    sheet.append(["New South Wales", "Charles Sturt University", 100, 500])
    raw_path = data_root / "raw" / "doe_s11_2024.xlsx"
    workbook.save(raw_path)

    manifest_path = data_root / "manifests" / "file_manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "doe_s11_2024",
                "year": 2024,
                "raw_path": str(raw_path.relative_to(tmp_path)),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    institution_map = tmp_path / "institution_map.yml"
    institution_map.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "csu",
                        "canonical_name": "Charles Sturt University",
                        "type": "university",
                        "state": "nsw",
                        "aliases": ["Charles Sturt University"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    extraction_map = tmp_path / "extraction_map.yml"
    extraction_map.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "source_id": "doe_s11_2024",
                        "sheet": "1",
                        "target_fact": "fact_enrolment_equity",
                        "header_style": "state_institution_columns",
                        "options": {
                            "layout": "two_column",
                            "name_col": 1,
                            "state_col": 0,
                            "data_start_row": 1,
                            "metric": "commencing_domestic_students",
                            "equity_columns": [
                                {"column": 2, "equity_group": "non_english_speaking_background"},
                                {"column": 3, "equity_group": "all_students"},
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_build_then_reconcile_end_to_end(project: Path, capsys) -> None:
    warehouse = project / "warehouse.duckdb"
    exit_code = main(
        [
            "--project-root",
            str(project),
            "--data-root",
            str(project / "data"),
            "--extraction-map",
            str(project / "extraction_map.yml"),
            "--institution-map",
            str(project / "institution_map.yml"),
            "--warehouse",
            str(warehouse),
            "build",
        ]
    )
    assert exit_code == 0
    assert warehouse.exists()
    build_output = capsys.readouterr().out
    assert "Normalized 2 records" in build_output

    exit_code = main(
        [
            "--project-root",
            str(project),
            "--warehouse",
            str(warehouse),
            "reconcile",
        ]
    )
    assert exit_code == 0
    reconcile_output = capsys.readouterr().out
    assert "reconciliation findings" in reconcile_output


def test_build_fails_for_unresolved_institution(project: Path, capsys) -> None:
    bad_map = project / "institution_map.yml"
    bad_map.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "someone_else",
                        "canonical_name": "Someone Else University",
                        "type": "university",
                        "state": "nsw",
                        "aliases": ["Someone Else University"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "--project-root",
            str(project),
            "--data-root",
            str(project / "data"),
            "--extraction-map",
            str(project / "extraction_map.yml"),
            "--institution-map",
            str(bad_map),
            "--warehouse",
            str(project / "warehouse.duckdb"),
            "build",
        ]
    )
    assert exit_code == 2
    assert "Charles Sturt University" in capsys.readouterr().err
