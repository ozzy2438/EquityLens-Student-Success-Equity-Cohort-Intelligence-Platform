"""Domain exceptions raised by the ingestion gateway."""


class IngestionError(Exception):
    """Base class for expected ingestion failures."""


class ConfigurationError(IngestionError):
    """The source registry is invalid or unsafe."""


class DownloadError(IngestionError):
    """A remote file could not be downloaded safely."""


class ValidationError(IngestionError):
    """Downloaded bytes do not match the declared data format."""
