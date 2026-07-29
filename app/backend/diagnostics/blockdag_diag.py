"""BlockDAG Connectivity Diagnostic — real probes, no assumptions.

Validates the 4 sources the operator provided:
  PRIMARY   RPC      https://rpc.bdagscan.com
  SECONDARY RPC      https://rpc.blockdag.engineering
  PRIMARY   EXPLORER https://bdagscan.com
  SECONDARY EXPLORER https://explorer.blockdag.engineering

For each source we measure:
  • Reachability (HTTP status, latency, stability across N samples)
  • EVM compatibility (chainId, blockNumber, getBalance, getTransactionByHash,
    getTransactionReceipt, getLogs)
  • Explorer capabilities (address page, etherscan-style + blockscout v2 APIs,
    transaction lookup, token-transfer history)
  • Automated-observation suitability (can the Wallet Observer poll this source
    reliably to detect IN/OUT BDAG transactions for an address?)

Real reference data (operator-supplied):
  TEST_ADDR  = 0xA52fD71308E8a36b5C6497FbDB8E36949A673974
  TEST_TX    = 0x7a8a61c0849383fcd6794aa98e004b072cb34d8812c777da2353b0902e983b2d
  EXPECTED_CHAIN_ID = 1404
"""
import asyncio
import json
import statistics
import time
from typing import Any

import httpx

TEST_ADDR = "0xA52fD71308E8a36b5C6497FbDB8E36949A673974"
TEST_TX = "0x7a8a61c0849383fcd6794aa98e004b072cb34d8812c777da2353b0902e983b2d"
EXPECTED_CHAIN_ID = 1404

RPC_PRIMARY = "https://rpc.bdagscan.com"
RPC_SECONDARY = "https://rpc.blockdag.engineering"
EXPL_PRIMARY = "https://bdagscan.com"
EXPL_SECONDARY = "https://explorer.blockdag.engineering"

HEADERS = {"User-Agent": "ArbiCore-Diagnostic/1.0", "Accept": "application/json"}
STABILITY_SAMPLES = 4


# ---------------------------------------------------------------- helpers

async def _http(method: str, url: str, **kw) -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as cx:
            r = await cx.request(method, url, headers=HEADERS, **kw)
            return {
                "ok": r.status_code < 500,
                "status": r.status_code,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "body_excerpt": (r.text[:300] if r.text else ""),
                "headers_x_ratelimit": {
                    k: v for k, v in r.headers.items()
                    if "ratelimit" in k.lower() or "retry" in k.lower()
                },
                "content_type": r.headers.get("content-type", ""),
                "json": _try_json(r),
            }
    except (httpx.HTTPError, ValueError) as e:
        return {
            "ok": False, "status": None,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "error": f"{type(e).__name__}: {e}",
        }


def _try_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except (ValueError, json.JSONDecodeError):
        return None


async def _rpc_call(url: str, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return await _http("POST", url, json=payload)


def _verdict(passed: bool, note: str = "") -> dict:
    return {"verdict": "PASS" if passed else "FAIL", "note": note}


# ---------------------------------------------------------------- reachability

async def reachability(url: str) -> dict:
    samples = []
    for _ in range(STABILITY_SAMPLES):
        r = await _http("GET", url)
        samples.append(r)
    latencies = [s["latency_ms"] for s in samples if s.get("status")]
    statuses = [s.get("status") for s in samples]
    ok = sum(1 for s in samples if s.get("ok"))
    return {
        "url": url,
        "samples_taken": STABILITY_SAMPLES,
        "ok_samples": ok,
        "stability_pct": round(ok / STABILITY_SAMPLES * 100, 1),
        "latency_ms_avg": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_min": min(latencies) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "statuses": statuses,
        "first_body_excerpt": samples[0].get("body_excerpt"),
        "verdict": _verdict(ok >= STABILITY_SAMPLES - 1)["verdict"],
    }


# ---------------------------------------------------------------- EVM compat

async def evm_compat(rpc_url: str) -> dict:
    out: dict[str, Any] = {"url": rpc_url}
    # eth_chainId
    r = await _rpc_call(rpc_url, "eth_chainId", [])
    cid_hex = (r.get("json") or {}).get("result")
    cid_int = None
    try:
        cid_int = int(cid_hex, 16) if cid_hex else None
    except (TypeError, ValueError):
        pass
    out["eth_chainId"] = {
        "raw": cid_hex, "decoded_int": cid_int,
        "expected_int": EXPECTED_CHAIN_ID,
        "matches_expected": cid_int == EXPECTED_CHAIN_ID,
        **_verdict(cid_int == EXPECTED_CHAIN_ID, f"got {cid_int}, expected {EXPECTED_CHAIN_ID}"),
        "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
        "error": r.get("error"),
    }

    # eth_blockNumber
    r = await _rpc_call(rpc_url, "eth_blockNumber", [])
    bn_hex = (r.get("json") or {}).get("result")
    bn_int = None
    try:
        bn_int = int(bn_hex, 16) if bn_hex else None
    except (TypeError, ValueError):
        pass
    out["eth_blockNumber"] = {
        "raw": bn_hex, "decoded_int": bn_int,
        **_verdict(bn_int is not None and bn_int > 0, f"head={bn_int}"),
        "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
        "error": r.get("error"),
    }

    # eth_getBalance
    r = await _rpc_call(rpc_url, "eth_getBalance", [TEST_ADDR, "latest"])
    bal_hex = (r.get("json") or {}).get("result")
    bal_int = None
    try:
        bal_int = int(bal_hex, 16) if bal_hex else None
    except (TypeError, ValueError):
        pass
    out["eth_getBalance"] = {
        "raw": bal_hex, "decoded_wei": bal_int,
        "decoded_bdag": (bal_int / 1e18) if bal_int is not None else None,
        **_verdict(bal_int is not None,
                   f"{(bal_int / 1e18) if bal_int is not None else '—'} BDAG (might legitimately be 0)"),
        "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
        "error": r.get("error"),
    }

    # eth_getTransactionByHash — operator's test_tx (may legitimately not exist
    # on this chain). We follow up with a positive-control lookup of a real
    # recent tx so the report can distinguish "method broken" from "wrong chain".
    r = await _rpc_call(rpc_url, "eth_getTransactionByHash", [TEST_TX])
    tx = (r.get("json") or {}).get("result")
    out["eth_getTransactionByHash"] = {
        "found": bool(tx), "blockNumber": tx and tx.get("blockNumber"),
        "from": tx and tx.get("from"), "to": tx and tx.get("to"),
        "value_hex": tx and tx.get("value"),
        "value_bdag": (int(tx["value"], 16) / 1e18) if (tx and tx.get("value")) else None,
        **_verdict(bool(tx),
                   f"resolved → block {tx and tx.get('blockNumber')}" if tx else "tx not found"),
        "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
        "rpc_error": (r.get("json") or {}).get("error"),
    }

    # POSITIVE CONTROL — find a recent populated block and look up its first tx
    # to prove eth_getTransactionByHash actually functions on this RPC.
    pc = {"verdict": "FAIL", "note": "skipped"}
    try:
        head_int = bn_int or 0
        sample_hash = None
        for offset in range(0, 50):
            blk_body = await _rpc_call(rpc_url, "eth_getBlockByNumber",
                                        [hex(max(0, head_int - offset)), False])
            blk = (blk_body.get("json") or {}).get("result") or {}
            txs = blk.get("transactions") or []
            if txs:
                sample_hash = txs[0]
                break
        if sample_hash:
            r2 = await _rpc_call(rpc_url, "eth_getTransactionByHash", [sample_hash])
            tx2 = (r2.get("json") or {}).get("result")
            if tx2:
                pc = {"verdict": "PASS",
                      "sample_tx_hash": sample_hash,
                      "block": tx2.get("blockNumber"),
                      "note": f"resolved real BDAG tx {sample_hash[:14]}… (proves method works)"}
                # if the positive control passes, the operator's test tx failing
                # is "not on this chain" not "RPC broken" — annotate above.
                if not out["eth_getTransactionByHash"]["found"]:
                    out["eth_getTransactionByHash"]["note"] = (
                        "operator's test tx not on BlockDAG mainnet (positive control "
                        f"{sample_hash[:14]}… resolved successfully — method is functional)"
                    )
                    out["eth_getTransactionByHash"]["verdict"] = "PASS"
            else:
                pc = {"verdict": "FAIL",
                      "note": f"positive control lookup of {sample_hash[:14]}… returned null"}
        else:
            pc = {"verdict": "FAIL",
                  "note": "no populated blocks in last 50 — chain quiet, cannot run positive control"}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        pc = {"verdict": "FAIL", "note": f"positive control errored: {e}"}
    out["eth_getTransactionByHash_positive_control"] = pc

    # eth_getTransactionReceipt — same logic: try operator's tx, then positive control
    r = await _rpc_call(rpc_url, "eth_getTransactionReceipt", [TEST_TX])
    rcpt = (r.get("json") or {}).get("result")
    receipt_block = {
        "found": bool(rcpt), "status_hex": rcpt and rcpt.get("status"),
        "logs_count": len(rcpt.get("logs") or []) if rcpt else 0,
        "blockNumber": rcpt and rcpt.get("blockNumber"),
        **_verdict(bool(rcpt), f"status={rcpt and rcpt.get('status')}, "
                               f"logs={len(rcpt.get('logs') or []) if rcpt else 0}"),
        "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
        "rpc_error": (r.get("json") or {}).get("error"),
    }
    # positive control on the same recent tx
    if pc.get("verdict") == "PASS" and pc.get("sample_tx_hash"):
        r3 = await _rpc_call(rpc_url, "eth_getTransactionReceipt", [pc["sample_tx_hash"]])
        rcpt2 = (r3.get("json") or {}).get("result")
        if rcpt2:
            if not receipt_block["found"]:
                receipt_block["note"] = (
                    f"operator's tx not on this chain (positive control receipt for "
                    f"{pc['sample_tx_hash'][:14]}… resolved — method works)"
                )
                receipt_block["verdict"] = "PASS"
            receipt_block["positive_control_logs"] = len(rcpt2.get("logs") or [])
    out["eth_getTransactionReceipt"] = receipt_block

    # eth_getLogs (last 1000 blocks worth — bounded query)
    from_block_hex = hex(max(0, (bn_int or 0) - 1000)) if bn_int else "0x0"
    r = await _rpc_call(rpc_url, "eth_getLogs", [{
        "fromBlock": from_block_hex, "toBlock": "latest", "address": TEST_ADDR,
    }])
    logs_res = (r.get("json") or {}).get("result")
    rpc_err = (r.get("json") or {}).get("error")
    out["eth_getLogs"] = {
        "queried_from": from_block_hex,
        "returned_count": (len(logs_res) if isinstance(logs_res, list) else None),
        **_verdict(isinstance(logs_res, list),
                   f"returned {len(logs_res) if isinstance(logs_res, list) else 'ERR'} logs"),
        "rpc_error": rpc_err, "latency_ms": r.get("latency_ms"), "http_status": r.get("status"),
    }

    # also probe debug call: 'net_version' which most EVM chains expose
    r = await _rpc_call(rpc_url, "net_version", [])
    out["net_version"] = (r.get("json") or {}).get("result")
    return out


# ---------------------------------------------------------------- explorer

async def explorer_capabilities(base: str) -> dict:
    """Probe explorer surfaces:
       • root reachability
       • etherscan-style API: ?module=account&action=txlist&address=...
       • blockscout v2 API: /api/v2/addresses/{addr}/transactions
       • blockscout v2 API: /api/v2/transactions/{tx}
       • blockscout v2 API: /api/v2/addresses/{addr}/token-transfers
    """
    out: dict[str, Any] = {"url": base}
    # root
    r = await _http("GET", base)
    out["root"] = {"status": r.get("status"), "latency_ms": r.get("latency_ms"),
                   "content_type": r.get("content_type"),
                   **_verdict((r.get("status") or 0) < 500, f"HTTP {r.get('status')}")}

    # etherscan-style — both naked base and /api
    etherscan_attempts = []
    for api_url in (f"{base}/api", f"{base}"):
        r = await _http("GET", api_url, params={
            "module": "account", "action": "txlist",
            "address": TEST_ADDR, "sort": "desc", "page": 1, "offset": 10,
        })
        body = r.get("json") or {}
        is_etherscan = isinstance(body, dict) and ("status" in body or "result" in body or "message" in body)
        sample = body.get("result") if isinstance(body, dict) else None
        etherscan_attempts.append({
            "url": api_url, "http_status": r.get("status"),
            "latency_ms": r.get("latency_ms"),
            "looks_like_etherscan": is_etherscan,
            "status_field": body.get("status") if isinstance(body, dict) else None,
            "message_field": body.get("message") if isinstance(body, dict) else None,
            "result_count": len(sample) if isinstance(sample, list) else None,
            "result_sample_first": sample[0] if isinstance(sample, list) and sample else None,
            "body_excerpt": r.get("body_excerpt"),
            "error": r.get("error"),
        })
    out["etherscan_style_txlist"] = etherscan_attempts
    out["etherscan_works"] = any(a.get("looks_like_etherscan") and (a.get("result_count") or 0) >= 0
                                  for a in etherscan_attempts)

    # blockscout v2 — txs for address
    bs_attempts: dict[str, Any] = {}
    for path in (
            f"/api/v2/addresses/{TEST_ADDR}/transactions",
            f"/api/v2/addresses/{TEST_ADDR}/token-transfers",
            f"/api/v2/transactions/{TEST_TX}",
            f"/api/v2/addresses/{TEST_ADDR}",
    ):
        r = await _http("GET", base + path)
        body = r.get("json")
        bs_attempts[path] = {
            "http_status": r.get("status"), "latency_ms": r.get("latency_ms"),
            "json_shape": (
                {"keys": list(body.keys())[:8]} if isinstance(body, dict) else
                ({"list_len": len(body)} if isinstance(body, list) else None)
            ),
            "items_count": (len(body.get("items") or []) if isinstance(body, dict) else None),
            "sample_item": (
                (body.get("items") or [None])[0] if isinstance(body, dict) and body.get("items")
                else None
            ),
            "error": r.get("error"),
            "body_excerpt": r.get("body_excerpt"),
        }
    out["blockscout_v2"] = bs_attempts
    bs_addr_tx = bs_attempts.get(f"/api/v2/addresses/{TEST_ADDR}/transactions", {})
    bs_token_tx = bs_attempts.get(f"/api/v2/addresses/{TEST_ADDR}/token-transfers", {})
    bs_single_tx = bs_attempts.get(f"/api/v2/transactions/{TEST_TX}", {})
    out["blockscout_works_address_history"] = (
        (bs_addr_tx.get("http_status") == 200) and (bs_addr_tx.get("items_count") is not None)
    )
    out["blockscout_works_token_transfers"] = (
        (bs_token_tx.get("http_status") == 200) and (bs_token_tx.get("items_count") is not None)
    )
    out["blockscout_works_tx_lookup"] = (
        (bs_single_tx.get("http_status") == 200)
        and isinstance(bs_single_tx.get("json_shape"), dict)
    )
    return out


# ---------------------------------------------------------------- suitability

def suitability(rpc_result: dict, explorer_result: dict) -> dict:
    """Translate raw probes into Wallet Observer-relevant capabilities."""
    addr_lookup = (
        rpc_result.get("eth_getBalance", {}).get("verdict") == "PASS"
        or explorer_result.get("blockscout_works_address_history")
        or explorer_result.get("etherscan_works")
    )
    tx_lookup = (
        rpc_result.get("eth_getTransactionByHash", {}).get("verdict") == "PASS"
        or explorer_result.get("blockscout_works_tx_lookup")
    )
    history_retrieval = (
        explorer_result.get("blockscout_works_address_history")
        or explorer_result.get("etherscan_works")
    )
    token_transfer_history = explorer_result.get("blockscout_works_token_transfers", False)
    can_detect_incoming = history_retrieval and tx_lookup
    can_detect_outgoing = history_retrieval and tx_lookup
    can_detect_transfer_complete = (
        rpc_result.get("eth_getTransactionReceipt", {}).get("verdict") == "PASS"
        or explorer_result.get("blockscout_works_tx_lookup")
    )
    return {
        "address_lookup": addr_lookup,
        "transaction_history_retrieval": history_retrieval,
        "transaction_lookup": tx_lookup,
        "transaction_receipt_retrieval": can_detect_transfer_complete,
        "token_transfer_history": token_transfer_history,
        "wallet_observer_detect_incoming_bdag": can_detect_incoming,
        "wallet_observer_detect_outgoing_bdag": can_detect_outgoing,
        "wallet_observer_detect_transfer_complete": can_detect_transfer_complete,
        "wallet_observer_detect_coinstore_deposit": can_detect_outgoing,
    }


def reliability_score(reach: dict, evm: dict | None, expl: dict | None) -> int:
    """0-100 weighted score across the three pillars."""
    s = 0
    s += int(reach.get("stability_pct", 0) * 0.3)  # 30 pts
    if evm:
        for k in ("eth_chainId", "eth_blockNumber", "eth_getBalance",
                  "eth_getTransactionByHash", "eth_getTransactionReceipt"):
            if (evm.get(k) or {}).get("verdict") == "PASS":
                s += 7  # 35 pts
    if expl:
        if expl.get("blockscout_works_address_history"):
            s += 15
        if expl.get("blockscout_works_tx_lookup"):
            s += 10
        if expl.get("etherscan_works"):
            s += 10
    return min(100, s)


async def cross_chain_check(test_tx: str) -> dict:
    """If the operator's test_tx doesn't resolve on BlockDAG, check whether
    it lives on BSC mainnet — common when the operator pastes the source-side
    swap payment tx."""
    out = {"tx": test_tx}
    try:
        async with httpx.AsyncClient(timeout=10.0) as cx:
            r = await cx.post("https://bsc-dataseed.binance.org",
                              json={"jsonrpc": "2.0", "id": 1,
                                    "method": "eth_getTransactionByHash",
                                    "params": [test_tx]})
            tx = (r.json() or {}).get("result")
            out["bsc_mainnet"] = {
                "found": bool(tx),
                "block_decimal": int(tx["blockNumber"], 16) if tx and tx.get("blockNumber") else None,
                "from": tx and tx.get("from"),
                "to": tx and tx.get("to"),
                "value_bnb": (int(tx["value"], 16) / 1e18) if tx and tx.get("value") else None,
                "note": ("Tx lives on BSC, not BlockDAG — typical for the source-side payment "
                         "of a swap into BDAG.") if tx else None,
            }
    except (httpx.HTTPError, ValueError) as e:
        out["bsc_mainnet"] = {"found": False, "error": str(e)}
    return out


async def address_activity_demo(rpc_url: str, address: str, lookback: int = 200) -> dict:
    """Demonstrate that the Wallet Observer can detect activity on the given
    address by walking the last `lookback` blocks via JSON-RPC."""
    out = {"url": rpc_url, "address": address, "lookback_blocks": lookback}
    address_lc = address.lower()
    try:
        async with httpx.AsyncClient(timeout=15.0) as cx:
            r = await cx.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                              "method": "eth_blockNumber", "params": []})
            head = int(r.json()["result"], 16)
            out["head_block"] = head
            matched = []
            for offset in range(0, lookback):
                bn = hex(head - offset)
                rr = await cx.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                                   "method": "eth_getBlockByNumber",
                                                   "params": [bn, True]})
                blk = (rr.json() or {}).get("result") or {}
                for tx in (blk.get("transactions") or []):
                    if (tx.get("from") or "").lower() == address_lc \
                            or (tx.get("to") or "").lower() == address_lc:
                        matched.append({
                            "block": int(blk["number"], 16),
                            "tx_hash": tx["hash"],
                            "from": tx["from"], "to": tx["to"],
                            "direction": ("OUT" if (tx.get("from") or "").lower() == address_lc
                                          else "IN"),
                            "value_bdag": int(tx.get("value", "0x0"), 16) / 1e18,
                        })
                        if len(matched) >= 5:
                            break
                if len(matched) >= 5:
                    break
            out["matched"] = matched
            out["found_activity"] = bool(matched)
            out["verdict"] = ("PASS" if matched
                              else f"NEUTRAL: no activity in last {lookback} blocks "
                                   f"(address may be inactive right now — try expanding the window)")
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = str(e)
        out["verdict"] = "FAIL"
    return out


# ---------------------------------------------------------------- entrypoint

async def run() -> dict:
    rpc_reach_p, rpc_reach_s, ex_reach_p, ex_reach_s = await asyncio.gather(
        reachability(RPC_PRIMARY), reachability(RPC_SECONDARY),
        reachability(EXPL_PRIMARY), reachability(EXPL_SECONDARY),
    )
    evm_p, evm_s = await asyncio.gather(
        evm_compat(RPC_PRIMARY), evm_compat(RPC_SECONDARY),
    )
    expl_p, expl_s = await asyncio.gather(
        explorer_capabilities(EXPL_PRIMARY), explorer_capabilities(EXPL_SECONDARY),
    )
    primary_rpc_score = reliability_score(rpc_reach_p, evm_p, None)
    secondary_rpc_score = reliability_score(rpc_reach_s, evm_s, None)
    primary_expl_score = reliability_score(ex_reach_p, None, expl_p)
    secondary_expl_score = reliability_score(ex_reach_s, None, expl_s)

    suit_primary = suitability(evm_p, expl_p)
    suit_secondary = suitability(evm_s, expl_s)

    # cross-chain + live address activity demo (using primary RPC if it's healthy)
    cross = await cross_chain_check(TEST_TX) if rpc_reach_p["verdict"] == "PASS" else {}
    activity = await address_activity_demo(RPC_PRIMARY, TEST_ADDR) \
        if rpc_reach_p["verdict"] == "PASS" else {}

    return {
        "ran_at": time.time(), "test_address": TEST_ADDR, "test_tx": TEST_TX,
        "expected_chain_id": EXPECTED_CHAIN_ID,
        "rpc_primary":   {"name": "rpc.bdagscan.com",      "reachability": rpc_reach_p,
                          "evm": evm_p,    "score": primary_rpc_score,   "suitability": suit_primary},
        "rpc_secondary": {"name": "rpc.blockdag.engineering", "reachability": rpc_reach_s,
                          "evm": evm_s,    "score": secondary_rpc_score, "suitability": suit_secondary},
        "explorer_primary":   {"name": "bdagscan.com",         "reachability": ex_reach_p,
                               "explorer": expl_p, "score": primary_expl_score},
        "explorer_secondary": {"name": "explorer.blockdag.engineering", "reachability": ex_reach_s,
                               "explorer": expl_s, "score": secondary_expl_score},
        "cross_chain_check": cross,
        "address_activity_demo": activity,
    }


if __name__ == "__main__":
    out = asyncio.run(run())
    print(json.dumps(out, indent=2, default=str))
