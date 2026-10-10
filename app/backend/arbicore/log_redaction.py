"""Credential-bearing URL redaction for process logs.

httpx logs every request at INFO with the full ``request.url``. For Alchemy
(and similar RPC providers) the API key lives in the path
(``/v2/<key>``), so the default log line leaks production credentials.

This module provides URL-aware redaction and a logging ``Filter`` that
rewrites log records before handlers emit them. It never raises; on parse
failure it applies a conservative regex fallback.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Path segments that typically hold opaque API credentials.
_CREDENTIAL_PATH_PREFIXES = (
    "/v2/",
    "/v3/",  # Infura-style
)

# Query parameter names whose values must never appear in logs.
_SENSITIVE_QUERY_KEYS = {
    "apikey",
    "api_key",
    "api-key",
    "key",
    "token",
    "access_token",
    "auth",
    "authorization",
    "secret",
}

# Fallback when URL parsing fails: redact /v2/<token> style paths.
# Schemes: http(s) and ws(s) — RPC providers may appear on either.
_V2_PATH_RE = re.compile(
    r"(?i)((?:https?|wss?)://[^\s\"']+?)/(v[23])/([A-Za-z0-9_\-]{8,})"
)
_USERINFO_RE = re.compile(r"(?i)((?:https?|wss?)://)([^/\s\"']+?)@")


def redact_credential_url(value: Any) -> Any:
    """Return ``value`` with credential-bearing URL material replaced.

    Non-string values are returned unchanged (except httpx ``URL``-like
    objects that stringify to a URL).
    """
    if value is None:
        return value
    if not isinstance(value, str):
        # httpx.URL and similar — redact their string form, keep type as str
        # in log args (handlers only need a printable representation).
        text = str(value)
        if "://" not in text:
            return value
        return _redact_url_text(text)
    if "://" not in value and "/v2/" not in value.lower() and "/v3/" not in value.lower():
        return value
    return _redact_url_text(value)


def _redact_url_text(text: str) -> str:
    # Fast path: whole string is a single URL (any scheme with ://).
    stripped = text.strip()
    if "://" in stripped and (" " not in stripped) and ("\n" not in stripped):
        return _redact_one_url(stripped)

    # Log lines may embed URLs among other text — redact each URL-looking token.
    # Include common RPC schemes (http/https/ws/wss); urlsplit still handles
    # the credential path segments for any scheme that reaches _redact_one_url.
    def _sub(match: re.Match[str]) -> str:
        return _redact_one_url(match.group(0))

    return re.sub(
        r"(?:https?|wss?)://[^\s\"'<>]+",
        _sub,
        text,
        flags=re.IGNORECASE,
    )


def _redact_one_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:  # noqa: BLE001
        return _fallback_redact(url)

    # Drop userinfo (user:pass@host).
    hostname = parts.hostname or ""
    if parts.port:
        netloc = f"{hostname}:{parts.port}"
    else:
        netloc = hostname
    # Preserve brackets for IPv6 if present in original netloc.
    if parts.netloc.startswith("["):
        netloc = parts.netloc.split("@")[-1]

    path = parts.path or ""
    lower_path = path.lower()
    for prefix in _CREDENTIAL_PATH_PREFIXES:
        # Match "/v2/<credential>" or "/v2/<credential>/..."
        marker = prefix.rstrip("/")  # "/v2"
        idx = lower_path.find(marker + "/")
        if idx >= 0:
            head = path[: idx + len(marker)]
            rest = path[idx + len(marker) + 1 :]  # after "/v2/"
            # Keep any trailing path after the credential segment.
            if "/" in rest:
                _cred, tail = rest.split("/", 1)
                path = f"{head}/[REDACTED]/{tail}"
            else:
                path = f"{head}/[REDACTED]"
            break

    query = parts.query
    if query:
        pairs = []
        for k, v in parse_qsl(query, keep_blank_values=True):
            if k.lower() in _SENSITIVE_QUERY_KEYS:
                # Keep literal [REDACTED] (do not percent-encode the marker).
                pairs.append(f"{k}=[REDACTED]")
            else:
                pairs.append(urlencode([(k, v)]))
        query = "&".join(pairs)

    return urlunsplit((parts.scheme, netloc, path, query, parts.fragment))


def _fallback_redact(url: str) -> str:
    out = _USERINFO_RE.sub(r"\1[REDACTED]@", url)
    out = _V2_PATH_RE.sub(r"\1/\2/[REDACTED]", out)
    return out


class CredentialUrlLogFilter(logging.Filter):
    """Rewrite log records so credential-bearing URLs never reach handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # If msg is a %-format template with args, only redact args.
            # Redacting "/v2/%s" templates would remove placeholders and break
            # logging.getMessage(). Fully-formed messages (typical httpx lines
            # once rendered, or URL-only args) are still redacted.
            if isinstance(record.msg, str):
                if not (record.args and "%" in record.msg):
                    record.msg = redact_credential_url(record.msg)
            args = record.args
            if args is None:
                return True
            if isinstance(args, dict):
                record.args = {k: redact_credential_url(v) for k, v in args.items()}
            elif isinstance(args, tuple):
                record.args = tuple(redact_credential_url(a) for a in args)
            else:
                # logging allows a single non-tuple mapping arg
                record.args = redact_credential_url(args)
        except Exception:  # noqa: BLE001 — never break logging
            pass
        return True


_INSTALLED = False


def install_credential_url_log_redaction(
    logger_names: Optional[Iterable[str]] = None,
) -> None:
    """Install the redaction filter on root + HTTP client loggers (idempotent)."""
    global _INSTALLED
    names = list(logger_names or ("httpx", "httpcore", "urllib3", "aiohttp", "web3"))
    filt = CredentialUrlLogFilter()
    root = logging.getLogger()
    # Attach to root so any handler sees redacted records.
    if not any(isinstance(f, CredentialUrlLogFilter) for f in root.filters):
        root.addFilter(filt)
    for name in names:
        lg = logging.getLogger(name)
        if not any(isinstance(f, CredentialUrlLogFilter) for f in lg.filters):
            lg.addFilter(filt)
    _INSTALLED = True
