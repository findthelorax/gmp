class GMPError(Exception):
    """Base GMP exception."""

class GMPAuthError(GMPError):
    """Authentication failed."""

class GMPConnectionError(GMPError):
    """Connection failed."""


class GMPNoUsageDataError(GMPError):
    """Usage data was not available for the requested dates."""
