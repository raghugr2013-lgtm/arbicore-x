"""Connector registry — resolves (exchange key, mode) to a connector instance.

The Intelligence Core only ever calls registry.resolve(); it never imports a
concrete connector. Simulation mode swaps every exchange for its simulated twin.
"""

_EXCHANGES = {}   # key -> connector instance (live)
_SIM_FACTORY = None


def register_exchange(connector):
    _EXCHANGES[connector.key] = connector


def set_sim_factory(factory):
    global _SIM_FACTORY
    _SIM_FACTORY = factory


def resolve(key: str, mode: str = "live"):
    if mode == "simulation":
        return _SIM_FACTORY(key)
    conn = _EXCHANGES.get(key)
    if conn is None:
        raise KeyError(f"Unknown exchange connector: {key}")
    return conn


def available():
    return [
        {
            "key": c.key,
            "name": c.name,
            "kind": "exchange",
            "live": c.capabilities.get("public_market_data", False),
            "capabilities": c.capabilities,
        }
        for c in _EXCHANGES.values()
    ]
