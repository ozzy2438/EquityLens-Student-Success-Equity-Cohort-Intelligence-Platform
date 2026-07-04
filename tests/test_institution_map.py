from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from equitylens_normalization.errors import InstitutionMapError
from equitylens_normalization.institution_map import load_institution_map


def _write_map(tmp_path: Path, institutions: list[dict]) -> Path:
    path = tmp_path / "institution_map.yml"
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "institutions": institutions}), encoding="utf-8"
    )
    return path


@pytest.fixture
def base_institutions() -> list[dict]:
    return [
        {
            "canonical_id": "acu",
            "canonical_name": "Australian Catholic University",
            "type": "university",
            "state": "multi_state",
            "is_multi_state": True,
            "peer_group_id": "acu_peer_regional",
            "aliases": ["Australian Catholic University", "ACU"],
        },
        {
            "canonical_id": "federation_university_australia",
            "canonical_name": "Federation University Australia",
            "type": "university",
            "state": "vic",
            "aliases": ["Federation University Australia", "University of Ballarat"],
        },
    ]


def test_resolves_footnote_marked_names(tmp_path: Path, base_institutions: list[dict]) -> None:
    resolver = load_institution_map(_write_map(tmp_path, base_institutions))
    assert resolver.resolve("Australian Catholic University(f)").canonical_id == "acu"
    assert resolver.resolve("federation university australia").canonical_id == (
        "federation_university_australia"
    )


def test_resolves_pre_rename_alias(tmp_path: Path, base_institutions: list[dict]) -> None:
    resolver = load_institution_map(_write_map(tmp_path, base_institutions))
    assert (
        resolver.resolve("University of Ballarat").canonical_id == "federation_university_australia"
    )


def test_unrecognised_name_raises_with_offending_string(
    tmp_path: Path, base_institutions: list[dict]
) -> None:
    resolver = load_institution_map(_write_map(tmp_path, base_institutions))
    with pytest.raises(InstitutionMapError, match="Not A Real University"):
        resolver.resolve("Not A Real University")


def test_conflicting_alias_across_institutions_rejected(tmp_path: Path) -> None:
    institutions = [
        {
            "canonical_id": "a",
            "canonical_name": "University A",
            "type": "university",
            "state": "nsw",
            "aliases": ["Shared Name"],
        },
        {
            "canonical_id": "b",
            "canonical_name": "University B",
            "type": "university",
            "state": "vic",
            "aliases": ["Shared Name"],
        },
    ]
    with pytest.raises(InstitutionMapError, match="Shared Name"):
        load_institution_map(_write_map(tmp_path, institutions))


def test_duplicate_canonical_id_rejected(tmp_path: Path, base_institutions: list[dict]) -> None:
    duplicated = [*base_institutions, dict(base_institutions[0])]
    with pytest.raises(InstitutionMapError, match="Duplicate canonical_id"):
        load_institution_map(_write_map(tmp_path, duplicated))


def test_missing_schema_version_rejected(tmp_path: Path) -> None:
    path = tmp_path / "institution_map.yml"
    path.write_text(yaml.safe_dump({"institutions": []}), encoding="utf-8")
    with pytest.raises(InstitutionMapError, match="schema_version"):
        load_institution_map(path)
