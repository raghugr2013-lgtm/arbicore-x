class ConnectorError(Exception):
    """Base for all connector failures."""


class ConnectorUnavailable(ConnectorError):
    """Network failure, 5xx, timeout."""


class SymbolNotListed(ConnectorError):
    """Trading pair does not exist on this exchange."""


class RateLimited(ConnectorError):
    """429 / exchange rate-limit code."""


class CapabilityNotEnabled(ConnectorError):
    """Phase-gated method called before its phase shipped."""


class MalformedResponse(ConnectorError):
    """Response schema drift / parse failure."""
