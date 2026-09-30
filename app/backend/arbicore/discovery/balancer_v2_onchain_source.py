"""P1 follow-up — on-chain Balancer V2 ``PoolRegistered`` candidate-discovery
source.

Implements the existing ``BalancerV2PoolSource`` protocol using ONLY read-only
``eth_getLogs`` against the canonical per-chain Balancer V2 Vault. It is a
CANDIDATE-DISCOVERY source only: it never establishes token membership, never
quotes, and never fabricates a pool identity. Every candidate it emits is
re-validated on-chain by the frozen P0 path (``discover_and_quote`` →
``getPoolTokens`` → membership / balances / decimals / fee / staleness /
liquidity → ``queryBatchSwap``) inside the unchanged P1 ``enumerate_and_quote``.

Design invariants
-----------------
* Uses the canonical ``BALANCER_V2_VAULT_BY_CHAIN`` (Ethereum/Base/Arbitrum/
  Optimism/Polygon). BNB → ``UNSUPPORTED_CHAIN``.
* Never scans unbounded history in one request — bounded, chunked block ranges.
* No external API key. The default log fetcher uses the existing canonical RPC
  env (``ARBICORE_RPC_URL_<CHAIN>``). RPC URLs/credentials are never logged.
* Fail-closed result semantics (identical to the rest of P1):
    - ``DISCOVERY_UNAVAILABLE``  (no fetcher / unresolved range / RPC error /
      rate-limit) — DISTINCT from "OK + zero candidates", never collapsed to 0.
    - ``MALFORMED_DISCOVERY``    (malformed log / wrong Vault emitter / poolId
      not embedding poolAddress).
    - ``UNSUPPORTED_CHAIN``.
    - ``OK`` with candidates (possibly empty = genuinely no registrations).
* ``PoolRegistered`` does NOT prove token-pair membership — that is deliberately
  left to the downstream P0 ``getPoolTokens`` validation.

The log fetcher and (optional) block-number resolver are INJECTED so the source
is fully unit-testable offline; the same public API (`find_pools`,
`discover_candidates`) is what Codex/VPS drives against live RPCs.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from eth_utils import keccak, to_checksum_address

from .balancer_v2_pool_discovery import BALANCER_V2_VAULT_BY_CHAIN
from .balancer_v2_pool_enumeration import (
    SRC_DISCOVERY_UNAVAILABLE,
    SRC_MALFORMED,
    SRC_OK,
    SRC_UNSUPPORTED_CHAIN,
    DiscoverySourceResult,
    PoolCandidate,
)

# event PoolRegistered(bytes32 indexed poolId, address indexed poolAddress, uint8 specialization)
POOL_REGISTERED_SIGNATURE = "PoolRegistered(bytes32,address,uint8)"
POOL_REGISTERED_TOPIC = "0x" + keccak(text=POOL_REGISTERED_SIGNATURE).hex()

_DEFAULT_WINDOW_BLOCKS = 100_000
_DEFAULT_CHUNK_SIZE = 10_000

# Injected fetcher contract:
#   async (chain, address, topics, from_block:int, to_block:int) -> List[dict]
EthGetLogsFn = Callable[..., Any]
EthBlockNumberFn = Callable[..., Any]


def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip(), 0)
    except (TypeError, ValueError):
        return default


class _MalformedLog(Exception):
    """Raised internally when a log cannot be trusted → MALFORMED_DISCOVERY."""


class OnChainPoolRegisteredSource:
    """Discovers Balancer V2 pool candidates from the Vault's ``PoolRegistered``
    event log via bounded, chunked, read-only ``eth_getLogs``."""

    source_name = "balancer_v2_onchain_pool_registered"

    def __init__(
        self, *,
        eth_get_logs_fn: Optional[EthGetLogsFn] = None,
        eth_block_number_fn: Optional[EthBlockNumberFn] = None,
        from_block: Optional[int] = None,
        to_block: Optional[int] = None,
        window_blocks: Optional[int] = None,
        chunk_size: Optional[int] = None,
    ):
        self._get_logs = eth_get_logs_fn
        self._block_number = eth_block_number_fn
        self._from_block = from_block
        self._to_block = to_block
        self._window = int(window_blocks) if window_blocks is not None else \
            _env_int("ARBICORE_BALANCER_DISCOVERY_WINDOW_BLOCKS", _DEFAULT_WINDOW_BLOCKS)
        chunk = int(chunk_size) if chunk_size is not None else \
            _env_int("ARBICORE_BALANCER_DISCOVERY_CHUNK_SIZE", _DEFAULT_CHUNK_SIZE)
        self._chunk = max(1, int(chunk or _DEFAULT_CHUNK_SIZE))

    # -- decoding ----------------------------------------------------------- #

    @staticmethod
    def _decode_log(log: Dict[str, Any], vault: str, chain: str) -> PoolCandidate:
        if not isinstance(log, dict):
            raise _MalformedLog("log is not an object")
        emitter = log.get("address")
        if not emitter or to_checksum_address(emitter) != vault:
            raise _MalformedLog("PoolRegistered emitted by a non-canonical Vault")
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) < 3:
            raise _MalformedLog("PoolRegistered requires 3 topics (sig, poolId, poolAddress)")
        if str(topics[0]).lower() != POOL_REGISTERED_TOPIC:
            raise _MalformedLog("topic0 is not PoolRegistered")

        pool_id = str(topics[1])
        if not pool_id.startswith("0x") or len(pool_id) != 66:
            raise _MalformedLog("poolId topic is not a 32-byte value")

        addr_topic = str(topics[2])
        if not addr_topic.startswith("0x") or len(addr_topic) != 66 or \
                addr_topic[2:26] != "0" * 24:
            raise _MalformedLog("poolAddress topic is not a left-padded address")
        pool_address = to_checksum_address("0x" + addr_topic[26:])

        # Balancer invariant: first 20 bytes of poolId == pool address (no fabrication).
        try:
            pid_bytes = bytes.fromhex(pool_id[2:])
        except ValueError as exc:
            raise _MalformedLog(f"poolId not hex: {exc}") from exc
        if to_checksum_address("0x" + pid_bytes[:20].hex()) != pool_address:
            raise _MalformedLog("poolId does not embed the registered pool address")

        specialization: Optional[int] = None
        data = log.get("data")
        if isinstance(data, str) and data.startswith("0x") and len(data) > 2:
            try:
                specialization = int(data, 16)
            except ValueError as exc:
                raise _MalformedLog(f"specialization data not hex: {exc}") from exc

        block_number: Optional[int] = None
        bn = log.get("blockNumber")
        if isinstance(bn, str) and bn.startswith("0x"):
            try:
                block_number = int(bn, 16)
            except ValueError:
                block_number = None
        elif isinstance(bn, int):
            block_number = bn

        return PoolCandidate(
            chain=chain, pool_id=pool_id, pool_address=pool_address,
            declared_vault=vault, source=OnChainPoolRegisteredSource.source_name,
            raw={"specialization": specialization, "block_number": block_number})

    # -- discovery ---------------------------------------------------------- #

    async def discover_candidates(
        self, chain: str, *, from_block: Optional[int] = None,
        to_block: Optional[int] = None,
    ) -> DiscoverySourceResult:
        """Deterministic, explicit-range candidate discovery. This is the API
        Codex/VPS drives with an explicit ``from_block``/``to_block`` window."""
        c = (chain or "").strip().lower()
        vault = BALANCER_V2_VAULT_BY_CHAIN.get(c)
        if not vault:
            return DiscoverySourceResult(SRC_UNSUPPORTED_CHAIN, source_name=self.source_name,
                                         error=f"Balancer V2 not deployed on chain '{chain}'")
        if self._get_logs is None:
            return DiscoverySourceResult(SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                                         error="no eth_getLogs fetcher configured")
        if from_block is None or to_block is None:
            return DiscoverySourceResult(
                SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                error="from_block/to_block could not be resolved")
        if int(from_block) < 0 or int(to_block) < 0 or int(from_block) > int(to_block):
            return DiscoverySourceResult(
                SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                error=f"invalid block range [{from_block}, {to_block}]")

        seen: set = set()
        candidates: List[PoolCandidate] = []
        chunks = 0
        start = int(from_block)
        end_total = int(to_block)
        while start <= end_total:
            end = min(start + self._chunk - 1, end_total)
            chunks += 1
            try:
                logs = await self._get_logs(c, vault, [POOL_REGISTERED_TOPIC], start, end)
            except Exception as exc:  # noqa: BLE001 — RPC/rate-limit fails closed
                return DiscoverySourceResult(
                    SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                    error=f"eth_getLogs failed [{start},{end}]: {type(exc).__name__}",
                    provenance={"chain": c, "vault": vault, "chunks": chunks})
            if logs is None or not isinstance(logs, (list, tuple)):
                return DiscoverySourceResult(
                    SRC_MALFORMED, source_name=self.source_name,
                    error="eth_getLogs returned a non-list result")
            for log in logs:
                try:
                    cand = self._decode_log(log, vault, c)
                except _MalformedLog as exc:
                    return DiscoverySourceResult(
                        SRC_MALFORMED, source_name=self.source_name,
                        error=str(exc), provenance={"chain": c, "vault": vault})
                key = str(cand.pool_id).lower()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(cand)
            start = end + 1

        return DiscoverySourceResult(
            SRC_OK, candidates=candidates, source_name=self.source_name,
            provenance={"chain": c, "vault": vault, "from_block": int(from_block),
                        "to_block": int(to_block), "chunks": chunks,
                        "chunk_size": self._chunk, "returned": len(candidates),
                        "event_topic0": POOL_REGISTERED_TOPIC})

    async def find_pools(self, chain: str, token_a: str,
                         token_b: str) -> DiscoverySourceResult:
        """``BalancerV2PoolSource`` entrypoint. Resolves a bounded default block
        window then delegates to :meth:`discover_candidates`. ``token_a/token_b``
        are NOT used to filter here — membership is validated on-chain by P0
        downstream. Fails closed if the window cannot be resolved."""
        c = (chain or "").strip().lower()
        vault = BALANCER_V2_VAULT_BY_CHAIN.get(c)
        if not vault:
            return DiscoverySourceResult(SRC_UNSUPPORTED_CHAIN, source_name=self.source_name,
                                         error=f"Balancer V2 not deployed on chain '{chain}'")
        if self._get_logs is None:
            return DiscoverySourceResult(SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                                         error="no eth_getLogs fetcher configured")

        # Resolve to_block.
        to_block = self._to_block
        if to_block is None and self._block_number is not None:
            try:
                to_block = int(await self._block_number(c))
            except Exception as exc:  # noqa: BLE001
                return DiscoverySourceResult(
                    SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                    error=f"latest block unresolved: {type(exc).__name__}")
        if to_block is None:
            return DiscoverySourceResult(
                SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                error="to_block unresolved (no to_block/eth_blockNumber configured)")

        # Resolve from_block: env override > explicit > bounded window.
        from_block = _env_int(f"ARBICORE_BALANCER_DISCOVERY_FROM_BLOCK_{c.upper()}", None)
        if from_block is None:
            from_block = self._from_block
        if from_block is None:
            from_block = max(0, int(to_block) - int(self._window))

        return await self.discover_candidates(c, from_block=int(from_block),
                                               to_block=int(to_block))
