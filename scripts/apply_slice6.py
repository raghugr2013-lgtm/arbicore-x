"""Slice 6 canonical portfolio block — pasted verbatim into server.py."""
BLOCK = '''# ---------------------------------------------------------------------------
# Slice 6 — Portfolio Canonicalization (2026-08-05).
#
# All hardcoded position/balance/transfer/ledger/treasury/exposure/allocation
# arrays removed. Every endpoint is now either backed by a canonical
# repository or returns a graceful empty payload preserving the UI contract.
# See \u00a7TODO comments per endpoint for the future canonical wiring path.
#
# Auth: every route uses ``dependencies=[Depends(_require_operator_dep)]``.
# Anonymous requests receive 401 (not_authenticated) uniformly.
# ---------------------------------------------------------------------------

@api_router.get(
    "/arbicore/portfolio/positions",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_positions(venue: Optional[str] = None,
                        side: Optional[str] = None) -> Dict[str, Any]:
    """Open position snapshot.

    TODO: wire ``ExecutionPositionRepository.snapshot()`` once the executor
    contract is deployed and paper/shadow execution begins writing rows to
    ``arbicore_execution_positions``. No canonical source exists today
    \u2192 empty items + zero totals.
    """
    _ = venue, side  # noqa: F841 \u2014 contract preserved for UI filter chips
    return {"items": [], "total": 0, "total_size_usd": 0.0,
            "total_upnl_usd": 0.0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/balances",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_balances(venue: Optional[str] = None) -> Dict[str, Any]:
    """Aggregated per-venue balance snapshot.

    TODO: wire ``VenueBalanceService.aggregate()`` \u2014 requires per-venue
    balance polling to be enabled (part of the P1 execution readiness
    milestone). No canonical source exists today \u2192 empty.
    """
    _ = venue  # noqa: F841
    return {"items": [], "total": 0, "total_usd": 0.0,
            "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/transfers",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_transfers(status: Optional[str] = None,
                        limit: int = 100) -> Dict[str, Any]:
    """Treasury transfer log.

    TODO: wire ``TreasuryLedger.transfers(window)`` once the treasury ledger
    substrate lands (P1 execution readiness). No canonical source today
    \u2192 empty.
    """
    _ = status, limit  # noqa: F841
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/deployable",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_deployable() -> Dict[str, Any]:
    """Deployable-capital snapshot.

    TODO: wire ``CapitalRouter.deployable_snapshot()``. The existing
    ``CapitalPolicyRepo`` today holds policy configuration only, not a
    runtime per-venue deployable/utilised state \u2014 that requires the P1
    executor + balance-polling wiring. Empty per-venue \u2192 zero totals.
    """
    return {
        "total_deployable_usd": 0.0,
        "total_utilised_usd": 0.0,
        "total_capital_usd": 0.0,
        "utilisation_pct": 0.0,
        "per_venue": [],
        "generated_at": _iso_now(),
    }


@api_router.get(
    "/arbicore/portfolio/treasury",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_treasury() -> Dict[str, Any]:
    """Treasury vault snapshot.

    TODO: wire ``TreasuryLedger.vault_snapshot()``. No canonical source
    exists today \u2192 empty vaults + zero total.
    """
    return {"vaults": [], "total_usd": 0.0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/ledger",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_ledger(kind: Optional[str] = None,
                     limit: int = 100) -> Dict[str, Any]:
    """Treasury ledger entries.

    TODO: wire ``TreasuryLedger.entries(window, kind)``. No canonical
    source exists today \u2192 empty.
    """
    _ = kind, limit  # noqa: F841
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/exposure",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_exposure() -> Dict[str, Any]:
    """Exposure breakdown by asset + by chain.

    TODO: wire ``ExposureAnalyzer.breakdown()``. Derives from
    balances + positions once those canonical sources exist. Empty today.
    """
    return {"by_asset": [], "by_chain": [], "total_usd": 0.0,
            "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/allocation",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_allocation() -> Dict[str, Any]:
    """Allocation target vs. actual per strategy bucket.

    TODO: wire ``AllocationPolicy.status()`` \u2014 requires the treasury
    ledger + capital router substrate. No canonical source today \u2192 empty
    items + zero totals.
    """
    return {"items": [], "total_target_usd": 0.0,
            "total_actual_usd": 0.0, "generated_at": _iso_now()}
'''

with open('/app/app/backend/server.py', 'r') as f:
    src = f.read()

# Locate start (the pre-existing portfolio block header) and end (last
# hardcoded allocation function's closing brace).
start_marker = '# ---------------------------------------------------------------------------\n# UI v2 \u00b7 Slice 4 preview endpoints \u2014 Portfolio'
start_idx = src.find(start_marker)
assert start_idx >= 0, 'portfolio start marker not found'

# End index: the closing of v2_allocation (line beginning with `return {"items": items, "total_target_usd":`)
# Find "return {" line inside v2_allocation
alloc_marker = 'async def v2_allocation()'
alloc_idx = src.find(alloc_marker, start_idx)
assert alloc_idx >= 0, 'allocation marker not found'
# Find the next blank line separator (two consecutive newlines) then include up to it
return_end = src.find(
    '"total_actual_usd": sum(x["actual_usd"] for x in items), '
    '"generated_at": _iso_now()}\n',
    alloc_idx,
)
assert return_end >= 0, 'allocation return marker not found'
end_idx = src.find('\n\n', return_end)
assert end_idx >= 0, 'end of allocation function not found'
end_idx += 2  # keep one blank line separator via the BLOCK trailing newline

new_src = src[:start_idx] + BLOCK + src[end_idx:]
with open('/app/app/backend/server.py', 'w') as f:
    f.write(new_src)
print('OK slice 6 replaced. bytes before:', len(src), 'after:', len(new_src))
