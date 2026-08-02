"""E4.6 — Verified Fee Model (editable overrides) for BDAG cycle accounting.

Defaults are the VERIFIED / conservative figures audited from published fee
schedules (BitMart Zendesk tiered fees, CoinGecko Coinstore rate, BlockDAG gas
docs, BNB Smart Chain avg gas, BitMart withdrawal docs). Every value is an
editable override persisted in `execution_config` under key 'execution_fees'.

NOTE: exchange withdrawal fees (USDT & BDAG) are only finalized in each
exchange's withdrawal UI and fluctuate; BDAG deposit/withdraw has been
intermittently gated. Treat low-confidence values as overridable estimates.
"""
import copy

from core.models import now_iso
from services import db

FEE_KEY = "execution_fees"

FEE_DEFAULTS = {
    "key": FEE_KEY,
    "purchase_gas_usd": 0.10,            # BSC gas for the portal purchase (actual ~$0.00–0.01)
    "bdag_transfer_fee_base": 0.001,     # BlockDAG network gas wallet→exchange (~0.000252 BDAG/tx)
    "bdag_withdrawal_fee_base": 1.0,     # exchange→wallet BDAG withdrawal (per-venue, set at UI time)
    "exchange_deposit_fee_usd": 0.0,     # exchange BDAG deposit is free
    "taker_fee_pct": {"bitmart": 0.25, "coinstore": 0.20, "default": 0.25},
    "maker_fee_pct": {"bitmart": 0.25, "coinstore": 0.20, "default": 0.25},
    "usdt_withdrawal_fee_usd": {"bitmart": 0.80, "coinstore": 1.00, "default": 1.00},
    "usdt_min_withdrawal_usd": {"bitmart": 10.0, "coinstore": 500.0, "default": 10.0},
}

# Provenance shown in the UI so operators see WHERE each default came from.
FEE_PROVENANCE = [
    {"item": "BitMart spot taker/maker", "value": "0.25% / 0.25% (VIP1)", "confidence": "high",
     "source": "BitMart Zendesk tiered trading-fee schedule (→0.08% VIP8, −25% with BMX)"},
    {"item": "Coinstore spot taker/maker", "value": "0.20% / 0.20%", "confidence": "medium",
     "source": "CoinGecko Coinstore exchange page; per-pair rate shown at trade time"},
    {"item": "BDAG transfer gas (wallet→exchange)", "value": "~0.000252 BDAG/tx → default 0.001", "confidence": "high",
     "source": "BlockDAG docs: 21,000 gas × ~12 gwei (negligible)"},
    {"item": "BDAG withdrawal (exchange→wallet)", "value": "flat per-venue (default 1 BDAG)", "confidence": "low",
     "source": "Not publicly fixed; shown in exchange withdrawal UI — override per venue"},
    {"item": "USDT withdrawal BEP20", "value": "BitMart $0.80 / Coinstore $1.00", "confidence": "medium",
     "source": "BitMart withdrawal docs ($0.18–1.50 range); Coinstore shown at withdrawal"},
    {"item": "BSC purchase gas", "value": "$0.10 (actual ~$0.00–0.01)", "confidence": "high",
     "source": "BNB Smart Chain avg ~0.82 gwei (2026); buffered for contract calls"},
    {"item": "BDAG exchange deposit", "value": "$0 (free); deposit gating intermittent", "confidence": "medium",
     "source": "Exchange deposits free; Coinstore 'Deposit: TBD', BitMart listing delayed historically"},
]


def _deep_merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def get_fees() -> dict:
    doc = await db.execution_config.find_one({"key": FEE_KEY}, {"_id": 0})
    merged = _deep_merge(FEE_DEFAULTS, doc or {})
    merged["key"] = FEE_KEY
    return merged


async def get_effective_fees() -> dict:
    """Same as get_fees() but with the BDAG transfer fee replaced by the
    measured rolling average when evidence exists. Used by surfaces that want
    to display the value actually consumed by ROI math."""
    fees = await get_fees()
    from services.execution import bdag_transfers
    eff = await bdag_transfers.effective_transfer_fee_bdag(fees["bdag_transfer_fee_base"])
    fees["bdag_transfer_fee_base"] = eff["value"]
    fees["bdag_transfer_fee_source"] = eff["source"]
    fees["bdag_transfer_fee_evidence_count"] = eff["evidence_count"]
    fees["bdag_transfer_fee_evidence"] = eff["rolling_average"]
    return fees


async def ensure_seeded():
    existing = await db.execution_config.find_one({"key": FEE_KEY})
    if not existing:
        await db.execution_config.insert_one({**copy.deepcopy(FEE_DEFAULTS), "updated_at": now_iso()})


async def update_fees(patch: dict) -> dict:
    cur = await get_fees()
    # only allow known top-level keys
    allowed = {k: v for k, v in (patch or {}).items() if k in FEE_DEFAULTS and k != "key"}
    merged = _deep_merge(cur, allowed)
    merged["updated_at"] = now_iso()
    merged["key"] = FEE_KEY
    await db.execution_config.update_one({"key": FEE_KEY}, {"$set": merged}, upsert=True)
    return await get_fees()


# ---- accessors ----
def taker_pct(fees: dict, venue: str) -> float:
    t = fees["taker_fee_pct"]
    return float(t.get((venue or "").lower(), t.get("default", 0.25)))


def usdt_withdrawal_usd(fees: dict, venue: str) -> float:
    w = fees["usdt_withdrawal_fee_usd"]
    return float(w.get((venue or "").lower(), w.get("default", 1.0)))
