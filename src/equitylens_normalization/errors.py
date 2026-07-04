"""Typed error hierarchy for the normalization and warehouse layer."""

from __future__ import annotations


class NormalizationError(Exception):
    """Base class for all normalization-layer failures."""


class ExtractionMapError(NormalizationError):
    """Raised when `config/extraction_map.yml` is malformed or inconsistent."""


class InstitutionMapError(NormalizationError):
    """Raised when `config/institution_map.yml` is malformed or an institution
    name cannot be resolved to a canonical entry."""


class ReconciliationError(NormalizationError):
    """Raised when cross-source reconciliation cannot be completed."""
