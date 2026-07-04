"""Load `config/institution_map.yml` and resolve raw publisher institution
strings to canonical institution identities.

Institution names in DoE/QILT workbooks carry trailing footnote markers (e.g.
``"Federation University Australia(f)"``, ``"Avondale University(1.08)"``) and
drift across years (renames, wording changes). Resolution always goes through
this module rather than ad-hoc string matching in normalizers, so every
alias is documented in one place and an unmatched name is a hard, named
failure instead of a silent gap.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from equitylens_normalization.errors import InstitutionMapError
from equitylens_normalization.models import InstitutionAlias
from equitylens_normalization.normalizers._shared import strip_footnote_markers


def normalize_name(raw: str) -> str:
    """Strip trailing footnote markers (repeatedly) and fold case/whitespace."""

    return strip_footnote_markers(raw).casefold()


class InstitutionResolver:
    """Alias index built once from `institution_map.yml` and reused per build."""

    def __init__(self, institutions: list[InstitutionAlias]) -> None:
        self._institutions = {inst.canonical_id: inst for inst in institutions}
        self._alias_index: dict[str, str] = {}
        for inst in institutions:
            for alias in (inst.canonical_name, *inst.aliases):
                key = normalize_name(alias)
                existing = self._alias_index.get(key)
                if existing is not None and existing != inst.canonical_id:
                    raise InstitutionMapError(
                        f"Alias {alias!r} maps to both {existing!r} and {inst.canonical_id!r}"
                    )
                self._alias_index[key] = inst.canonical_id

    def resolve(self, raw_name: str, *, context: str = "") -> InstitutionAlias:
        """Return the canonical institution for a raw publisher string.

        Raises `InstitutionMapError` naming the offending string; institution
        coverage gaps must surface as build failures, not silent drops, since
        Phase 3 calibration depends on complete institution coverage.
        """

        key = normalize_name(raw_name)
        canonical_id = self._alias_index.get(key)
        if canonical_id is None:
            suffix = f" ({context})" if context else ""
            raise InstitutionMapError(
                f"Unrecognised institution name {raw_name!r}{suffix}. "
                "Add it as an alias in config/institution_map.yml."
            )
        return self._institutions[canonical_id]

    def get(self, canonical_id: str) -> InstitutionAlias:
        return self._institutions[canonical_id]

    def all(self) -> list[InstitutionAlias]:
        return list(self._institutions.values())


def _required(item: dict[str, object], key: str, *, canonical_id: str) -> object:
    value = item.get(key)
    if value is None or value == "":
        raise InstitutionMapError(f"Institution {canonical_id!r} is missing required field: {key}")
    return value


def load_institution_map(path: Path) -> InstitutionResolver:
    """Parse, validate, and index the institution alias registry."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InstitutionMapError(f"Cannot read institution map {path}: {exc}") from exc

    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise InstitutionMapError("institution_map.yml must declare schema_version: 1")
    raw_institutions = document.get("institutions")
    if not isinstance(raw_institutions, list) or not raw_institutions:
        raise InstitutionMapError("institution_map.yml must contain a non-empty institutions list")

    seen_ids: set[str] = set()
    institutions: list[InstitutionAlias] = []
    for item in raw_institutions:
        if not isinstance(item, dict):
            raise InstitutionMapError("Every institution entry must be a mapping")
        canonical_id = str(_required(item, "canonical_id", canonical_id="<unknown>"))
        if canonical_id in seen_ids:
            raise InstitutionMapError(f"Duplicate canonical_id: {canonical_id}")
        seen_ids.add(canonical_id)

        institution_type = str(_required(item, "type", canonical_id=canonical_id))
        if institution_type not in {"university", "nuhei"}:
            raise InstitutionMapError(
                f"Institution {canonical_id!r} has invalid type: {institution_type!r}"
            )
        aliases = tuple(str(alias) for alias in item.get("aliases", []))
        institutions.append(
            InstitutionAlias(
                canonical_id=canonical_id,
                canonical_name=str(_required(item, "canonical_name", canonical_id=canonical_id)),
                institution_type=institution_type,
                state=str(_required(item, "state", canonical_id=canonical_id)),
                peer_group_id=(
                    str(item["peer_group_id"]) if item.get("peer_group_id") is not None else None
                ),
                aliases=aliases,
                is_multi_state=bool(item.get("is_multi_state", False)),
                notes=(str(item["notes"]) if item.get("notes") is not None else None),
            )
        )
    return InstitutionResolver(institutions)
