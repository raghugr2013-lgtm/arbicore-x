"""ArbiCore X — canonical read-only Limited-Live verifier (P0-P3).

Ships in the backend image at /app/verify_readiness.py. Runs P0->P1->P2->P3
sequentially in ONE fresh Python process, explicitly bootstrapping the real
provider registry first. Read-only: NO signing, NO broadcast, NO LIMITED_LIVE.
Never prints RPC URLs / keys / secrets — only counts, addresses and statuses.

Run:  docker exec -w /app <container> python /app/verify_readiness.py
Each stage prints exactly one line:  RESULT P0 <STATUS> <k=v ...>  (etc.)
STATUS is PASS | BLOCKED | FAIL.
"""
import asyncio
import os


def result(stage: str, status: str, **kv) -> None:
    detail = " ".join(f"{k}={v}" for k, v in kv.items())
    print(f"RESULT {stage} {status} {detail}".rstrip())


async def _run() -> None:
    from arbicore.providers.bootstrap import ensure_default_registry
    from arbicore.providers.rpc_failover import get_registry_rpc_provider
    from arbicore.discovery import base_pool_registry as R

    # Explicit, deterministic registry bootstrap BEFORE P0.
    ensure_default_registry()
    rpc = get_registry_rpc_provider("base")
    if rpc is None:
        for s in ("P0", "P1", "P2", "P3"):
            result(s, "FAIL", reason="no_base_rpc_provider_after_bootstrap")
        print("VERIFY_DONE")
        return

    async def eth_call(to, data, block="latest"):
        return await rpc.eth_call({"to": to, "data": data}, block)

    # ---------- P0: Aerodrome resolution + canonical pool graph ----------
    try:
        from arbicore.searcher.aero_resolver import resolve_and_propagate
        total0 = len(R.get_canonical_pools())
        unresolved0 = len(R.unresolved_pools())
        applied = await resolve_and_propagate(
            eth_call, [p.canonical_id for p in R.unresolved_pools()])
        nodes, _ = R.build_canonical_pool_graph(resolved_only=True)
        real = sum(1 for x in nodes if R.canonical_pool_by_id(x.pool_address).address)
        leaks = sum(1 for x in nodes
                    if R.canonical_pool_by_id(x.pool_address).address is None)
        s = R.registry_summary()
        resolved_final = s.get("deterministic_verified", 0) + s.get("runtime_resolved", 0)
        ok = (total0 == 30 and len(nodes) == 30 and real == 30 and leaks == 0)
        result("P0", "PASS" if ok else "FAIL",
                initial_total=total0, initial_unresolved=unresolved0,
                applied=applied, loader_nodes=len(nodes), real_addr=real,
                leaks=leaks, resolved_final=resolved_final)
        print("P0_REGISTRY_SUMMARY", s)
    except Exception as e:  # noqa: BLE001
        result("P0", "FAIL", error=f"{type(e).__name__}:{e}")

    # ---------- P1: real Uniswap V3 quote + invalid-fee fallback ----------
    try:
        from arbicore.execution.quoter import QuoterRegistry
        p = next(x for x in R.get_canonical_pools()
                 if x.dex == "uniswap_v3" and x.address)
        envk = ("ARBICORE_RPC_URL_BASE" if os.environ.get("ARBICORE_RPC_URL_BASE")
                else "ARBICORE_RPC_URL")
        hop = {"dex": "uniswap_v3", "token_in": p.token0_address,
               "token_out": p.token1_address,
               "amount_in_wei": 100 * 10 ** p.token0_decimals, "fee": p.fee_ppm}
        q = await QuoterRegistry(rpc_url_env=envk).quote_route(chain="base", hops=[hop])
        h0 = q.hops[0] if q.hops else None
        ok = (q.status == "ok" and (q.final_amount_out_wei or 0) > 0
              and h0 and h0.quoter_contract and h0.block_number)
        result("P1", "PASS" if ok else "FAIL", pool=p.canonical_id,
                quote_status=q.status, out_wei=q.final_amount_out_wei,
                quoter=getattr(h0, "quoter_contract", None),
                block=getattr(h0, "block_number", None),
                rpc_env=envk, rpc_host=getattr(h0, "rpc_host", None),
                hop_status=getattr(h0, "status", None),
                hop_error=getattr(h0, "error", None))
        qb = await QuoterRegistry(rpc_url_env=envk).quote_route(
            chain="base", hops=[dict(hop, fee=1234567)])
        result("P1_BADFEE", "PASS" if str(qb.status).startswith("fallback") else "FAIL",
                fallback_status=qb.status)
    except Exception as e:  # noqa: BLE001
        result("P1", "FAIL", error=f"{type(e).__name__}:{e}")

    # ---------- P2: Balancer vault liquidity / usable notional ----------
    try:
        vault = os.environ.get("BASE_BALANCER_V2_VAULT")
        if not vault:
            result("P2", "BLOCKED", missing_env="BASE_BALANCER_V2_VAULT")
        else:
            p = next(x for x in R.get_canonical_pools()
                     if x.dex == "uniswap_v3" and x.address)
            data = "0x70a08231" + vault.lower().replace("0x", "").rjust(64, "0")
            bal = int(await eth_call(p.token0_address, data), 16)
            result("P2", "PASS" if bal > 0 else "FAIL",
                    vault_bal_wei=bal, token=p.token0_symbol,
                    decimals=p.token0_decimals)
    except Exception as e:  # noqa: BLE001
        result("P2", "FAIL", error=f"{type(e).__name__}:{e}")

    # ---------- P3: executor identity + signer readiness ----------
    try:
        from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
            resolve_executor_address, probe_executor_identity,
            probe_signer_readiness)
        RPC = (os.environ.get("ARBICORE_RPC_URL_BASE")
               or os.environ.get("ARBICORE_RPC_URL")
               or os.environ.get("BASE_RPC_URL"))
        ex = resolve_executor_address()
        if not ex:
            result("P3", "BLOCKED", missing_env="ARBICORE_EXECUTOR_ADDRESS_BASE")
        else:
            ident = await probe_executor_identity(
                executor_address=ex, rpc_url=RPC, chain="8453")
            st = ident.get("status")
            sig = probe_signer_readiness(executor_owner=ident.get("owner"))
            ready = sig.get("ready") if isinstance(sig, dict) else sig
            ok = st in ("READY", "ok") and bool(ready)
            result("P3", "PASS" if ok else "BLOCKED",
                    identity_status=st, reason=ident.get("reason"),
                    signer_ready=ready)
    except Exception as e:  # noqa: BLE001
        result("P3", "FAIL", error=f"{type(e).__name__}:{e}")

    print("VERIFY_DONE")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
