class GMPError(Exception):
    """Base GMP exception."""

class GMPAuthError(GMPError):
    """Authentication failed."""

class GMPConnectionError(GMPError):
    """Connection failed."""
