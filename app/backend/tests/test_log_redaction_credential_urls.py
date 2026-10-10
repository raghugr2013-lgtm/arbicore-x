"""Regression: credential-bearing RPC URLs must never appear in emitted logs.

Uses synthetic tokens only — never production Alchemy keys.
"""
from __future__ import annotations

import io
import logging

import pytest

from arbicore.log_redaction import (
    CredentialUrlLogFilter,
    install_credential_url_log_redaction,
    redact_credential_url,
)

# Long synthetic tokens so fragment checks are meaningful.
SYNTH_ALCHEMY = "SYNTHETIC_ALCHEMY_KEY_DO_NOT_USE_001_ABCDEFGH"
SYNTH_INFURA = "SYNTHETIC_INFURA_KEY_DO_NOT_USE_002_IJKLMNOP"
SYNTH_QUERY = "SYNTHETIC_QUERY_APIKEY_DO_NOT_USE_003"
SYNTH_USER = "synth_user"
SYNTH_PASS = "synth_pass_DO_NOT_USE"


def _assert_no_secret(blob: str, *secrets: str) -> None:
    lower = blob.lower()
    for secret in secrets:
        assert secret not in blob, f"full secret leaked: {secret[:12]}…"
        # Reject contiguous fragments of length >= 12 from the synthetic token.
        for i in range(0, max(0, len(secret) - 11)):
            frag = secret[i : i + 12]
            assert frag not in blob and frag.lower() not in lower, (
                f"secret fragment leaked: {frag}"
            )


def test_redact_alchemy_v2_path_preserves_host():
    url = f"https://base-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY}"
    out = redact_credential_url(url)
    assert "base-mainnet.g.alchemy.com" in out
    assert "/v2/[REDACTED]" in out
    _assert_no_secret(out, SYNTH_ALCHEMY)


def test_redact_infura_v3_path():
    url = f"https://mainnet.infura.io/v3/{SYNTH_INFURA}"
    out = redact_credential_url(url)
    assert "mainnet.infura.io" in out
    assert "/v3/[REDACTED]" in out
    _assert_no_secret(out, SYNTH_INFURA)


def test_redact_sensitive_query_param():
    url = f"https://rpc.example.com/?apikey={SYNTH_QUERY}&safe=1"
    out = redact_credential_url(url)
    assert "apikey=[REDACTED]" in out
    assert "safe=1" in out
    _assert_no_secret(out, SYNTH_QUERY)


def test_redact_userinfo():
    url = f"https://{SYNTH_USER}:{SYNTH_PASS}@rpc.example.com/path"
    out = redact_credential_url(url)
    assert "rpc.example.com" in out
    assert SYNTH_USER not in out
    assert SYNTH_PASS not in out


def test_redact_embedded_url_in_httpx_style_message():
    msg = (
        f'HTTP Request: POST https://arb-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY} '
        f'"HTTP/1.1 200 OK"'
    )
    out = redact_credential_url(msg)
    assert "arb-mainnet.g.alchemy.com" in out
    assert "/v2/[REDACTED]" in out
    assert "HTTP/1.1 200 OK" in out
    _assert_no_secret(out, SYNTH_ALCHEMY)


def test_log_filter_blocks_secret_in_msg_and_args(caplog):
    logger = logging.getLogger("httpx")
    logger.setLevel(logging.INFO)
    logger.propagate = True
    filt = CredentialUrlLogFilter()
    logger.addFilter(filt)
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            logger.info(
                "HTTP Request: POST %s \"HTTP/1.1 429 Too Many Requests\"",
                f"https://base-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY}",
            )
            logger.exception(
                "RPC failed url=%s",
                f"https://eth-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY}",
            )
        blob = "\n".join(r.getMessage() for r in caplog.records)
        assert "base-mainnet.g.alchemy.com" in blob or "eth-mainnet.g.alchemy.com" in blob
        assert "[REDACTED]" in blob
        _assert_no_secret(blob, SYNTH_ALCHEMY)
    finally:
        logger.removeFilter(filt)


def test_install_idempotent_and_redacts_via_stream_handler():
    # Fresh dedicated logger to avoid cross-test pollution of root handlers.
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    prior_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        install_credential_url_log_redaction()
        install_credential_url_log_redaction()  # idempotent
        httpx_log = logging.getLogger("httpx")
        # Mirror httpx: format template + full URL arg (not a bare key).
        httpx_log.info(
            'HTTP Request: POST %s "HTTP/1.1 500 Internal Server Error"',
            f"https://polygon-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY}",
        )
        # Fully-formed diagnostic line (retry / fallback style).
        logging.getLogger("httpcore").warning(
            "connect_tcp.started url=%s",
            f"https://opt-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY}",
        )
        # Pre-rendered message with embedded credential URL (no args).
        httpx_log.info(
            f'HTTP Request: POST https://base-mainnet.g.alchemy.com/v2/{SYNTH_ALCHEMY} '
            f'"HTTP/1.1 429 Too Many Requests"'
        )
        blob = stream.getvalue()
        assert "polygon-mainnet.g.alchemy.com" in blob or "opt-mainnet.g.alchemy.com" in blob or (
            "base-mainnet.g.alchemy.com" in blob
        )
        assert "[REDACTED]" in blob
        _assert_no_secret(blob, SYNTH_ALCHEMY)
    finally:
        root.removeHandler(handler)
        root.setLevel(prior_level)


def test_non_url_messages_pass_through_unchanged():
    msg = "quoter hop ok chain=base amount_in=1"
    assert redact_credential_url(msg) == msg
