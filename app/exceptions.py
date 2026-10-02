class ScannerError(Exception):
    """Base scanner exception."""


class ExternalAPIError(ScannerError):
    """A public upstream endpoint failed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        attempts: int = 1,
        kind: str = "upstream",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.attempts = attempts
        self.kind = kind


class InvalidMarketError(ScannerError):
    """Market is not a scannable standard binary market."""


class FeeUnknownError(ScannerError):
    """Fee information was not verified and cannot be treated as zero."""
