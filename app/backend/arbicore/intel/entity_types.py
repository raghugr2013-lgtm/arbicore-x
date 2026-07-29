"""Frozen EntityType enum — additions are deliberate vocabulary changes."""
from __future__ import annotations
from enum import Enum


class EntityType(str, Enum):
    """One vocabulary for every kind of intelligence subject in the platform.

    Wallets are one type among many; the same collections / scorers /
    cluster detectors serve all values.
    """
    WALLET             = "WALLET"
    SMART_MONEY        = "SMART_MONEY"
    EXCHANGE_WALLET    = "EXCHANGE_WALLET"
    MARKET_MAKER       = "MARKET_MAKER"
    LIQUIDITY_PROVIDER = "LIQUIDITY_PROVIDER"
    LAUNCH_PARTICIPANT = "LAUNCH_PARTICIPANT"
    CEX_ACCOUNT        = "CEX_ACCOUNT"
    DEX_POOL           = "DEX_POOL"
    UNKNOWN            = "UNKNOWN"
