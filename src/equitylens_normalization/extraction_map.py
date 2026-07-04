"""Load and validate `config/extraction_map.yml`.

Each rule is one `(source_id, sheet)` (or `(source_id, sheet_pattern)` for
workbooks like QILT's whose sheet set is matched by name convention rather
than listed individually) extraction instruction. Validation is deliberately
strict, mirroring `equitylens_ingestion.registry.load_registry`: unknown
`target_fact`/`header_style` values and duplicate rule keys are rejected at
load time rather than surfacing as confusing failures deep in a normalizer.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from equitylens_normalization.errors import ExtractionMapError
from equitylens_normalization.models import ExtractionRule

_TARGET_FACTS = {
    "fact_enrolment_equity",
    "fact_retention_attrition",
    "fact_equity_performance",
    "fact_completion_cohort",
    "fact_seifa",
    "fact_ses_experience",
}

_HEADER_STYLES = {
    "inline_state_pseudo_header",  # 2018-2020 DoE .xls: state as a pseudo-header row
    "state_institution_columns",  # 2021+ DoE .xlsx S11/S15: explicit State|Institution columns
    "s16_institution_block",  # DoE S16: flat "Higher Education Institution" block, no state column
    "s17_cohort_table",  # DoE S17: tracking-window cohort tables (T1-T12 or 17.1-17.12)
    "focus_area_columns",  # QILT *_INST_CI sheets
    "two_row_merged_seifa",  # ABS SEIFA index-family/score-decile header
}


def _required(item: dict[str, object], key: str, *, index: int) -> object:
    value = item.get(key)
    if value is None or value == "":
        raise ExtractionMapError(f"Rule #{index} is missing required field: {key}")
    return value


def load_extraction_map(path: Path) -> list[ExtractionRule]:
    """Parse and validate the sheet-level extraction map."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ExtractionMapError(f"Cannot read extraction map {path}: {exc}") from exc

    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ExtractionMapError("extraction_map.yml must declare schema_version: 1")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ExtractionMapError("extraction_map.yml must contain a non-empty rules list")

    rules: list[ExtractionRule] = []
    seen_keys: set[tuple[str, str | None, str | None]] = set()
    for index, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise ExtractionMapError(f"Rule #{index} must be a mapping")

        source_id = str(_required(item, "source_id", index=index))
        target_fact = str(_required(item, "target_fact", index=index))
        header_style = str(_required(item, "header_style", index=index))
        if target_fact not in _TARGET_FACTS:
            raise ExtractionMapError(
                f"Rule for {source_id!r} has unknown target_fact: {target_fact!r}"
            )
        if header_style not in _HEADER_STYLES:
            raise ExtractionMapError(
                f"Rule for {source_id!r} has unknown header_style: {header_style!r}"
            )

        sheet = item.get("sheet")
        sheet_pattern = item.get("sheet_pattern")
        if sheet is None and sheet_pattern is None:
            raise ExtractionMapError(f"Rule for {source_id!r} needs either sheet or sheet_pattern")
        sheet = str(sheet) if sheet is not None else None
        sheet_pattern = str(sheet_pattern) if sheet_pattern is not None else None

        key = (source_id, sheet, sheet_pattern)
        if key in seen_keys:
            raise ExtractionMapError(f"Duplicate extraction rule for {key!r}")
        seen_keys.add(key)

        options = item.get("options", {})
        if not isinstance(options, dict):
            raise ExtractionMapError(f"Rule for {source_id!r} options must be a mapping")

        rules.append(
            ExtractionRule(
                source_id=source_id,
                target_fact=target_fact,
                header_style=header_style,
                sheet=sheet,
                sheet_pattern=sheet_pattern,
                workbook_member=(
                    str(item["workbook_member"])
                    if item.get("workbook_member") is not None
                    else None
                ),
                table_number=(
                    str(item["table_number"]) if item.get("table_number") is not None else None
                ),
                options=options,
                notes=(str(item["notes"]) if item.get("notes") is not None else None),
            )
        )
    return rules


def rules_for_source(rules: list[ExtractionRule], source_id: str) -> list[ExtractionRule]:
    return [rule for rule in rules if rule.source_id == source_id]
