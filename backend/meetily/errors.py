"""Exception hierarchy for Meetily Automation API interactions."""


class MeetilyError(Exception):
    """Base exception for all Meetily client errors."""

    def __init__(self, message: str, status_code: int = 500, details: str = ""):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class MeetilyConnectionError(MeetilyError):
    """Raised when connection to Meetily gateway fails or times out."""

    def __init__(self, message: str = "Failed to connect to Meetily gateway", details: str = ""):
        super().__init__(message, status_code=503, details=details)


class MeetilyAuthError(MeetilyError):
    """Raised on 401 or 403 responses indicating invalid or missing token."""

    def __init__(self, message: str = "Meetily authentication failed", status_code: int = 401, details: str = ""):
        super().__init__(message, status_code=status_code, details=details)


class MeetilyNotFound(MeetilyError):
    """Raised on 404 response when a requested resource is not found."""

    def __init__(self, message: str = "Requested Meetily resource not found", details: str = ""):
        super().__init__(message, status_code=404, details=details)


class MeetilyInvalidResponse(MeetilyError):
    """Raised when Meetily returns invalid JSON or unexpected schema."""

    def __init__(self, message: str = "Invalid response schema received from Meetily", details: str = ""):
        super().__init__(message, status_code=502, details=details)


class MeetilyServerError(MeetilyError):
    """Raised on 5xx server errors from Meetily gateway."""

    def __init__(self, message: str = "Meetily gateway server error", status_code: int = 500, details: str = ""):
        super().__init__(message, status_code=status_code, details=details)
