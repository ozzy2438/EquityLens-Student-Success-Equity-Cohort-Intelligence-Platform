"""Typed error hierarchy for the calibration target layer."""

from __future__ import annotations


class CalibrationError(Exception):
    """Base class for all calibration-layer failures."""


class TargetGenerationError(CalibrationError):
    """Raised when the warehouse does not contain what a target needs."""
