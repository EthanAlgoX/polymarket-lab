class ScannerError(Exception):
    """Base scanner exception."""


class ExternalAPIError(ScannerError):
    """A public upstream endpoint failed."""


class InvalidMarketError(ScannerError):
    """Market is not a scannable standard binary market."""


class FeeUnknownError(ScannerError):
    """Fee information was not verified and cannot be treated as zero."""
