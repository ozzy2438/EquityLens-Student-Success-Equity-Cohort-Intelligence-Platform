from __future__ import annotations

import pandas as pd
import pytest

from equitylens_normalization.normalizers._shared import (
    is_aggregate_row,
    iter_institution_rows,
    parse_value,
    parse_year_vintage,
    slugify,
    strip_footnote_markers,
)


@pytest.mark.parametrize(
    ("raw", "expected_value", "expected_suppressed"),
    [
        ("< 5", None, True),
        ("np", None, True),
        (None, None, False),
        (float("nan"), None, False),
        ("1,234", 1234.0, False),
        (42.5, 42.5, False),
        ("not a number", None, False),
    ],
)
def test_parse_value(raw, expected_value, expected_suppressed) -> None:
    value, suppressed = parse_value(raw)
    assert value == expected_value
    assert suppressed is expected_suppressed


def test_strip_footnote_markers_removes_trailing_reference_codes() -> None:
    assert (
        strip_footnote_markers("Federation University Australia(f)")
        == "Federation University Australia"
    )
    assert strip_footnote_markers("Avondale University(1.08)") == "Avondale University"
    assert strip_footnote_markers("Curtin University") == "Curtin University"


def test_strip_footnote_markers_keeps_seifa_vintage_qualifiers() -> None:
    # A parenthetical containing a space is meaningful data, not footnote noise.
    assert strip_footnote_markers("2021 (2016 SEIFA)") == "2021 (2016 SEIFA)"


def test_slugify_normalises_labels() -> None:
    assert slugify("All Domestic(2.05)(4.02)") == "all_domestic"
    assert slugify("Low SES by SA1(5.09)") == "low_ses_by_sa1"


@pytest.mark.parametrize(
    ("raw", "expected_year", "expected_vintage"),
    [
        ("2021", 2021, None),
        (2021.0, 2021, None),
        ("2021 (2016 SEIFA)", 2021, "2016 SEIFA"),
        ("2016 (2016 ASGS)", 2016, "2016 ASGS"),
    ],
)
def test_parse_year_vintage(raw, expected_year, expected_vintage) -> None:
    assert parse_year_vintage(raw) == (expected_year, expected_vintage)


def test_parse_year_vintage_rejects_unparseable_header() -> None:
    with pytest.raises(ValueError, match="Cannot parse year header"):
        parse_year_vintage("Total 2020")


def test_is_aggregate_row_matches_known_labels() -> None:
    assert is_aggregate_row("Non-University Higher Education Institutions")
    assert is_aggregate_row("Table A Providers")
    assert not is_aggregate_row("Charles Sturt University")


def test_is_aggregate_row_accepts_extra_labels() -> None:
    assert is_aggregate_row("Domestic Students", extra_labels=("Domestic Students",))


def test_iter_institution_rows_pseudo_header_layout() -> None:
    grid = pd.DataFrame(
        [
            ["New South Wales", None],
            ["Charles Sturt University", 100],
            ["Macquarie University", 200],
            ["Victoria", None],
            ["Deakin University", 300],
            ["TOTAL", 600],
        ]
    )
    rows = list(
        iter_institution_rows(
            grid,
            layout="pseudo_header",
            name_col=0,
            value_columns=(1,),
            data_start_row=0,
        )
    )
    assert rows == [
        ("New South Wales", "Charles Sturt University", 1),
        ("New South Wales", "Macquarie University", 2),
        ("Victoria", "Deakin University", 4),
    ]


def test_iter_institution_rows_two_column_layout_blank_fills_state() -> None:
    grid = pd.DataFrame(
        [
            ["New South Wales", "Charles Sturt University", 100],
            [None, "Macquarie University", 200],
            ["Victoria", "Deakin University", 300],
        ]
    )
    rows = list(
        iter_institution_rows(
            grid,
            layout="two_column",
            name_col=1,
            state_col=0,
            data_start_row=0,
        )
    )
    assert rows == [
        ("New South Wales", "Charles Sturt University", 0),
        ("New South Wales", "Macquarie University", 1),
        ("Victoria", "Deakin University", 2),
    ]


def test_iter_institution_rows_stops_at_total_marker() -> None:
    grid = pd.DataFrame(
        [
            ["Charles Sturt University", 100],
            ["TOTAL", 100],
            ["Total 2017", 100],
            ["Ignored University", 999],
        ]
    )
    rows = list(
        iter_institution_rows(
            grid,
            layout="pseudo_header",
            name_col=0,
            value_columns=(1,),
            data_start_row=0,
        )
    )
    assert rows == [(None, "Charles Sturt University", 0)]
