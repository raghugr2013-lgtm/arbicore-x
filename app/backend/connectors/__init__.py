from connectors.bitmart import BitMartConnector
from connectors.coinstore import CoinstoreConnector
from connectors.gate import GateConnector
from connectors.mexc import MEXCConnector
from connectors.sim import SimExchangeConnector
from connectors.stubs import make_stubs
from connectors.xt import XTConnector
from core import registry


def register_all():
    for conn in [XTConnector(), MEXCConnector(), GateConnector(), BitMartConnector(), CoinstoreConnector()]:
        registry.register_exchange(conn)
    for stub in make_stubs():
        registry.register_exchange(stub)
    registry.set_sim_factory(SimExchangeConnector)
