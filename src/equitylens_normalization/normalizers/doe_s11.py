"""Section 11 (equity group enrolments) normalizer.

Covers both DoE sheet eras: `inline_state_pseudo_header` (2018-2020 `.xls`,
one reference year per sheet, equity groups as columns, state given by an
inline pseudo-header row) and `state_institution_columns` (2021+ `.xlsx`,
explicit `State | Institution` columns). Column semantics (equity-group
columns) are identical across eras; only the row-grouping mechanism differs,
handled by `_shared.iter_institution_rows`.
"""

from __future__ import annotations

import pandas as pd

from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import ExtractionRule, LongRecord
from equitylens_normalization.normalizers._shared import (
    DEFAULT_STOP_MARKERS,
    DEFAULT_SUPPRESSED_TOKENS,
    is_aggregate_row,
    iter_institution_rows,
    parse_value,
)

ROLLUP_INSTITUTION_ID = "__nuhei_rollup__"


def normalize(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    options = rule.options
    equity_columns = options["equity_columns"]
    value_columns = tuple(entry["column"] for entry in equity_columns)
    suppressed_tokens = tuple(options.get("suppressed_tokens", DEFAULT_SUPPRESSED_TOKENS))
    stop_markers = tuple(options.get("stop_markers", DEFAULT_STOP_MARKERS))

    records: list[LongRecord] = []
    for state_raw, institution_raw, row_index in iter_institution_rows(
        grid,
        layout=options["layout"],
        name_col=options["name_col"],
        value_columns=value_columns,
        state_col=options.get("state_col"),
        data_start_row=options["data_start_row"],
        stop_markers=stop_markers,
    ):
        if is_aggregate_row(institution_raw, tuple(options.get("skip_institution_labels", ()))):
            continue
        institution = resolver.resolve(institution_raw, context=f"{rule.source_id}:{rule.sheet}")
        if institution.canonical_id == ROLLUP_INSTITUTION_ID:
            continue

        for entry in equity_columns:
            raw_value = grid.iloc[row_index, entry["column"]]
            value, suppressed = parse_value(raw_value, suppressed_tokens)
            records.append(
                LongRecord(
                    source_id=rule.source_id,
                    source_sheet=rule.sheet or "",
                    target_fact=rule.target_fact,
                    year=source_year,
                    metric=options["metric"],
                    value=value,
                    suppressed_flag=suppressed,
                    institution_raw=institution.canonical_id,
                    state_raw=state_raw,
                    equity_group=entry["equity_group"],
                    metric_definition=entry.get("metric_definition"),
                )
            )
    return records
