"""Hermetic test for C-1 — the deep-merge that makes persisted Mongo config
authoritative over the runtime boot baseline. Extracts the pure ``_deep_merge_cfg``
from composition.py by source slice (composition imports the whole arbicore
runtime, so we don't import it — we exec only the pure function).
"""
import os

_SRC = os.environ.get("ACX_SRC")
if not _SRC:
    _SRC = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "arbicore")
    )


def _extract_fn(path, name):
    with open(path) as fh:
        lines = fh.readlines()
    start = next(i for i, ln in enumerate(lines)
                 if ln.startswith(f"def {name}("))
    body = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() == "" or ln[:1] in (" ", "\t"):
            body.append(ln)
        else:
            break
    ns = {}
    exec(compile("".join(body), "extract", "exec"), ns)
    return ns[name]


_deep_merge_cfg = _extract_fn(os.path.join(_SRC, "runtime/composition.py"),
                             "_deep_merge_cfg")

# The exact fail-closed boot baseline the C-1 patch installs in composition.
_BOOT_CFG = {"interval_s": 60.0,
             "chains": {"base": {"enabled": True}},
             "providers": {"balancer_v2": {"enabled": True}},
             "route_search": {"max_hops": 4, "wall_clock_cap_s": 5.0,
                              "candidate_cap": 64, "min_pool_tvl_usd": 100_000.0},
             "gate_thresholds": {"default": {}}}


def test_persisted_partial_route_search_overrides_and_preserves_siblings():
    """THE mismatch fix: a persisted partial (only max_hops) must WIN for max_hops
    yet PRESERVE sibling route_search keys (min_pool_tvl_usd, caps). The old
    shallow merge dropped them — the root cause of persisted != runtime."""
    persisted = {"route_search": {"max_hops": 3}}
    merged = _deep_merge_cfg(_BOOT_CFG, persisted)
    assert merged["route_search"]["max_hops"] == 3               # persisted wins
    assert merged["route_search"]["min_pool_tvl_usd"] == 100_000.0  # sibling preserved
    assert merged["route_search"]["candidate_cap"] == 64            # sibling preserved


def test_persisted_enables_more_chains_and_providers():
    persisted = {"chains": {"arbitrum": {"enabled": True},
                            "polygon": {"enabled": True}},
                 "providers": {"aave_v3": {"enabled": True}}}
    merged = _deep_merge_cfg(_BOOT_CFG, persisted)
    # base stays, new chains added (deep-merge, not replace)
    assert merged["chains"]["base"]["enabled"] is True
    assert merged["chains"]["arbitrum"]["enabled"] is True
    assert merged["chains"]["polygon"]["enabled"] is True
    assert merged["providers"]["balancer_v2"]["enabled"] is True
    assert merged["providers"]["aave_v3"]["enabled"] is True


def test_empty_persisted_is_pure_boot_default():
    assert _deep_merge_cfg(_BOOT_CFG, {}) == _BOOT_CFG


def test_non_dict_values_are_replaced():
    merged = _deep_merge_cfg(_BOOT_CFG, {"interval_s": 30.0})
    assert merged["interval_s"] == 30.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} C-1 tests passed")
