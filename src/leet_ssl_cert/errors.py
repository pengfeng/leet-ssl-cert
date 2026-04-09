"""Project-specific exception types."""


class LeetSSLCertError(Exception):
    """Base exception for the project."""


class ConfigError(LeetSSLCertError):
    """Raised when the configuration file is invalid."""


class ACMEError(LeetSSLCertError):
    """Raised when ACME issuance or revocation fails."""


class DNSError(LeetSSLCertError):
    """Raised when DNS challenge operations fail."""


class DeployError(LeetSSLCertError):
    """Raised when certificate upload or binding fails."""
