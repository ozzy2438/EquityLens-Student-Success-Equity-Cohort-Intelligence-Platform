from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from equitylens_normalization.errors import ExtractionMapError
from equitylens_normalization.extraction_map import load_extraction_map, rules_for_source


def _write_rules(tmp_path: Path, rules: list[dict]) -> Path:
    path = tmp_path / "extraction_map.yml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "rules": rules}), encoding="utf-8")
    return path


def _rule(**overrides) -> dict:
    base = {
        "source_id": "doe_s11_2024",
        "sheet": "11.5",
        "target_fact": "fact_enrolment_equity",
        "header_style": "state_institution_columns",
        "options": {"layout": "two_column"},
    }
    base.update(overrides)
    return base


def test_loads_valid_rules(tmp_path: Path) -> None:
    rules = load_extraction_map(_write_rules(tmp_path, [_rule()]))
    assert len(rules) == 1
    assert rules[0].source_id == "doe_s11_2024"
    assert rules_for_source(rules, "doe_s11_2024") == rules


def test_rejects_unknown_target_fact(tmp_path: Path) -> None:
    with pytest.raises(ExtractionMapError, match="target_fact"):
        load_extraction_map(_write_rules(tmp_path, [_rule(target_fact="not_a_fact")]))


def test_rejects_unknown_header_style(tmp_path: Path) -> None:
    with pytest.raises(ExtractionMapError, match="header_style"):
        load_extraction_map(_write_rules(tmp_path, [_rule(header_style="not_a_style")]))


def test_rejects_duplicate_rule_key(tmp_path: Path) -> None:
    with pytest.raises(ExtractionMapError, match="Duplicate"):
        load_extraction_map(_write_rules(tmp_path, [_rule(), _rule()]))


def test_rejects_rule_without_sheet_or_pattern(tmp_path: Path) -> None:
    rule = _rule()
    del rule["sheet"]
    with pytest.raises(ExtractionMapError, match="sheet_pattern"):
        load_extraction_map(_write_rules(tmp_path, [rule]))


def test_rejects_missing_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "extraction_map.yml"
    path.write_text(yaml.safe_dump({"rules": [_rule()]}), encoding="utf-8")
    with pytest.raises(ExtractionMapError, match="schema_version"):
        load_extraction_map(path)


def test_sheet_pattern_rule_is_accepted(tmp_path: Path) -> None:
    rule = _rule(
        source_id="qilt_ses_2024",
        sheet_pattern="FOCUS_(UG|PGC)_UNI_1Y_INST_CI",
        workbook_member="SES_2024_National_Report_Tables.xlsx",
        target_fact="fact_ses_experience",
        header_style="focus_area_columns",
    )
    del rule["sheet"]
    rules = load_extraction_map(_write_rules(tmp_path, [rule]))
    assert rules[0].sheet_pattern == "FOCUS_(UG|PGC)_UNI_1Y_INST_CI"
