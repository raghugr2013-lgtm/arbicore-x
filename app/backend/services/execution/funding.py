"""Funding Asset Flexibility (E2) — supports USDT / BNB / ETH funding.

Given a target cycle size in USD, computes how much of each supported funding
asset is required and the BDAG quantity obtainable at the live portal price.
Pure read-only math sourced from the E1 portal connector (coinPrices + bdagPrice).
No swaps, no transfers, no execution.
"""
from services.portal_price import portal_price

SUPPORTED = ["USDT", "BNB", "ETH"]


def _coin_usd(asset: str):
    asset = asset.upper()
    if asset == "USDT":
        return 1.0
    prices = portal_price.coin_prices or {}
    p = prices.get(asset)
    if p is None:
        p = prices.get(asset.lower())
    return float(p) if isinstance(p, (int, float)) and p > 0 else None


def funding_breakdown(size_usd: float) -> dict:
    bdag_price = portal_price.current_bdag_price()
    assets = []
    for a in SUPPORTED:
        usd = _coin_usd(a)
        assets.append({
            "asset": a,
            "usd_price": usd,
            "amount_required": round(size_usd / usd, 8) if (usd and size_usd) else None,
            "available": usd is not None,
        })
    bdag_qty = round(size_usd / bdag_price, 2) if (bdag_price and size_usd) else None
    return {
        "size_usd": size_usd,
        "bdag_price": bdag_price,
        "bdag_qty_gross": bdag_qty,
        "portal_stale": bdag_price is None,
        "funding_assets": assets,
        "note": "Gross conversion at the live portal price; excludes purchase / "
                "network / trading fees. Read-only — no swaps, no transfers.",
    }
