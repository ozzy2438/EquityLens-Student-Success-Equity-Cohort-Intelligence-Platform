"""Shared cell-parsing and row-grouping helpers reused across normalizers."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pandas as pd

DEFAULT_SUPPRESSED_TOKENS = ("< 5", "np")
DEFAULT_STOP_MARKERS = ("TOTAL",)
_STOP_PREFIXES = ("Total ", "% change")

# Per-state/per-sector subtotal rows that appear inline among institution rows
# in DoE grid tables. These are aggregates, not institutions, and must be
# skipped before institution-alias resolution rather than raising an
# unrecognised-name error.
DEFAULT_AGGREGATE_ROW_LABELS = (
    "State Total",
    "National Total",
    "Table A Providers",
    "Table B Providers",
    "Table A institutions",
    "Table B institutions",
    "Table A and B Providers",
    "Non-University Higher Education Institutions",
    "Private Universities (Table C) and Non-University Higher Education Institutions",
    "All Universities",
    "NUHEIs",
    "All institutions",
)


def is_aggregate_row(name_text: str, extra_labels: tuple[str, ...] = ()) -> bool:
    return name_text in DEFAULT_AGGREGATE_ROW_LABELS or name_text in extra_labels


# Matches trailing footnote-reference markers, including comma-separated
# multi-letter references like "(d,e)" (confirmed in S16 headers, e.g.
# "First Address Regional(d,e)" -- an earlier version of this regex only
# matched a single token with no internal punctuation, so "(d,e)" survived
# unstripped and produced a spurious distinct equity_group_id,
# "first_address_regional_d_e", alongside the real "first_address_regional"
# from years whose footnote lettering happened to strip cleanly). Deliberately
# does NOT match parenthetical content containing a space with no comma, such
# as "(2016 SEIFA)", which is meaningful data (a SEIFA-vintage qualifier), not
# publisher footnote noise.
_FOOTNOTE_MARKER = re.compile(r"\(\s*[\w.]+(?:\s*,\s*[\w.]+)*\s*\)\s*$")
_WHITESPACE = re.compile(r"\s+")
_YEAR_VINTAGE = re.compile(r"^(?P<year>\d{4})(?:\.\d+)?\s*(?:\((?P<vintage>[^()]+)\))?$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_footnote_markers(text: str) -> str:
    """Repeatedly strip trailing footnote-reference markers like `(f)`/`(2.05)`."""

    result = str(text).strip()
    while True:
        stripped = _FOOTNOTE_MARKER.sub("", result).strip()
        if stripped == result:
            return _WHITESPACE.sub(" ", result)
        result = stripped


def slugify(text: str) -> str:
    """Turn a human-readable label into a stable `snake_case` identifier."""

    folded = _WHITESPACE.sub("_", strip_footnote_markers(text).strip().casefold())
    return _NON_ALNUM.sub("_", folded).strip("_")


def parse_year_vintage(raw: object) -> tuple[int, str | None]:
    """Split a year header cell into `(year, vintage)`.

    Handles plain years (`"2021"`, `2021.0`) and SEIFA/ASGS-vintage-qualified
    years (`"2021 (2016 SEIFA)"`), which must stay distinguishable rather than
    collapsing into one column during the 2016->2021 SEIFA transition.
    """

    text = str(raw).strip()
    match = _YEAR_VINTAGE.match(text)
    if not match:
        raise ValueError(f"Cannot parse year header cell: {raw!r}")
    return int(match.group("year")), match.group("vintage")


def parse_value(
    raw: object, suppressed_tokens: tuple[str, ...] = DEFAULT_SUPPRESSED_TOKENS
) -> tuple[float | None, bool]:
    """Return `(value, suppressed_flag)` for one publisher cell.

    A genuinely empty cell is `(None, False)`. A cell holding a literal
    suppression token (`"< 5"`, `"np"`) is `(None, True)` -- distinct from an
    empty cell, since publisher suppression is a meaningful data point, not a
    missing one.
    """

    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, False
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, False
        if text in suppressed_tokens:
            return None, True
        try:
            return float(text.replace(",", "")), False
        except ValueError:
            return None, False
    return float(raw), False


def is_stop_row(name_text: str, stop_markers: tuple[str, ...]) -> bool:
    if name_text in stop_markers:
        return True
    return any(name_text.startswith(prefix) for prefix in _STOP_PREFIXES)


def iter_institution_rows(
    grid: pd.DataFrame,
    *,
    layout: str,
    name_col: int,
    data_start_row: int,
    value_columns: tuple[int, ...] = (),
    state_col: int | None = None,
    stop_markers: tuple[str, ...] = DEFAULT_STOP_MARKERS,
) -> Iterator[tuple[str | None, str, int]]:
    """Yield `(state_raw, institution_raw, row_index)` for each data row.

    `layout="pseudo_header"` (2018-2020 DoE era): a row where every column in
    `value_columns` is null marks a new state label rather than an
    institution row -- forward-filled as `state_raw` for subsequent rows.
    `layout="two_column"` (2021+ DoE era): `state_col` holds the state on the
    institution's first row only and is blank-filled down.
    """

    current_state: str | None = None
    for row_index in range(data_start_row, len(grid)):
        row = grid.iloc[row_index]
        name_cell = row[name_col]
        if pd.isna(name_cell):
            continue
        name_text = str(name_cell).strip()
        if is_stop_row(name_text, stop_markers):
            break

        if layout == "pseudo_header":
            all_values_null = all(pd.isna(row[column]) for column in value_columns)
            if all_values_null:
                current_state = name_text
                continue
            yield current_state, name_text, row_index
        elif layout == "two_column":
            if state_col is None:
                raise ValueError("two_column layout requires state_col")
            state_cell = row[state_col]
            if not pd.isna(state_cell):
                current_state = str(state_cell).strip()
            yield current_state, name_text, row_index
        else:
            raise ValueError(f"Unknown layout: {layout!r}")
