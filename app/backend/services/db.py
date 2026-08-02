import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

routes_col = db.routes
networks_col = db.networks
ticker_snapshots = db.ticker_snapshots
orderbook_snapshots = db.orderbook_snapshots
candles_col = db.candles
fee_snapshots = db.fee_snapshots
evaluations = db.evaluations
positions_col = db.manual_positions
transfers_col = db.transfer_log
events_col = db.system_events
discoveries_col = db.discoveries
treasury_col = db.treasury_ledger
users_col = db.users
login_attempts = db.login_attempts
api_keys_col = db.api_keys
settings_col = db.settings
alerts_log = db.alerts_log
capabilities_col = db.capabilities
capability_history = db.capability_history
balance_snapshots = db.balance_snapshots
exchange_health_snaps = db.exchange_health_snaps
readiness_snapshots = db.readiness_snapshots
episodes_col = db.episodes
gate_cost_ledger = db.gate_cost_ledger
calibration_log = db.calibration_log
portal_price_snapshots = db.portal_price_snapshots
venue_registry = db.venue_registry
execution_config = db.execution_config
execution_cycles = db.execution_cycles
execution_audit = db.execution_audit
integration_health_snaps = db.integration_health_snaps
shadow_campaigns = db.shadow_campaigns
recovery_proofs = db.recovery_proofs
exchange_intelligence = db.exchange_intelligence
production_ledger = db.production_ledger
opportunity_windows = db.opportunity_windows
fresh_cycle_observations = db.fresh_cycle_observations


async def ensure_indexes():
    await routes_col.create_index("id", unique=True)
    await networks_col.create_index("key", unique=True)
    await ticker_snapshots.create_index([("route_id", 1), ("exchange", 1), ("ts", -1)])
    await ticker_snapshots.create_index("created_at", expireAfterSeconds=90 * 86400)
    await orderbook_snapshots.create_index([("route_id", 1), ("exchange", 1), ("ts", -1)])
    await orderbook_snapshots.create_index("created_at", expireAfterSeconds=30 * 86400)
    await candles_col.create_index([("route_id", 1), ("exchange", 1), ("interval_min", 1), ("open_time", 1)], unique=True)
    await fee_snapshots.create_index([("exchange", 1), ("currency", 1), ("ts", -1)])
    await evaluations.create_index([("route_id", 1), ("ts", -1)])
    await evaluations.create_index("created_at", expireAfterSeconds=180 * 86400)
    await positions_col.create_index("id", unique=True)
    await transfers_col.create_index([("route_id", 1), ("sent_at", -1)])
    await events_col.create_index([("ts", -1)])
    await events_col.create_index("created_at", expireAfterSeconds=30 * 86400)
    await discoveries_col.create_index([("asset", 1), ("ts", -1)])
    await treasury_col.create_index([("route_id", 1), ("ts", -1)])
    await users_col.create_index("username", unique=True)
    await login_attempts.create_index("identifier")
    await api_keys_col.create_index("id", unique=True)
    await settings_col.create_index("key", unique=True)
    await alerts_log.create_index([("ts", -1)])
    await alerts_log.create_index("created_at", expireAfterSeconds=30 * 86400)
    await capabilities_col.create_index([("exchange", 1), ("currency", 1)], unique=True)
    await capability_history.create_index([("ts", -1)])
    await balance_snapshots.create_index([("exchange", 1), ("ts", -1)])
    await balance_snapshots.create_index("created_at", expireAfterSeconds=180 * 86400)
    await exchange_health_snaps.create_index([("exchange", 1), ("ts", -1)])
    await exchange_health_snaps.create_index("created_at", expireAfterSeconds=180 * 86400)
    await readiness_snapshots.create_index([("route_id", 1), ("exchange", 1), ("ts", -1)])
    await readiness_snapshots.create_index("created_at", expireAfterSeconds=365 * 86400)
    await episodes_col.create_index([("route_id", 1), ("exchange", 1), ("kind", 1), ("ts", -1)])
    await episodes_col.create_index("created_at", expireAfterSeconds=365 * 86400)
    await gate_cost_ledger.create_index([("route_id", 1), ("exchange", 1), ("ts", -1)])
    await gate_cost_ledger.create_index("created_at", expireAfterSeconds=365 * 86400)
    await calibration_log.create_index([("status", 1), ("resolve_after", 1)])
    await calibration_log.create_index([("route_id", 1), ("ts", -1)])
    await calibration_log.create_index("created_at", expireAfterSeconds=365 * 86400)
    await portal_price_snapshots.create_index([("ts", -1)])
    await portal_price_snapshots.create_index("created_at", expireAfterSeconds=365 * 86400)
    # Phase E2 — execution framework scaffolding (persistent; no TTL on cycles)
    await venue_registry.create_index("exchange", unique=True)
    await execution_config.create_index("key", unique=True)
    await execution_cycles.create_index("id", unique=True)
    await execution_cycles.create_index([("state", 1), ("updated_at", -1)])
    await execution_cycles.create_index([("created_at", -1)])
    await execution_audit.create_index([("cycle_id", 1), ("ts", 1)])
    await execution_audit.create_index("created_at", expireAfterSeconds=365 * 86400)
    await integration_health_snaps.create_index([("exchange", 1), ("ts", -1)])
    await integration_health_snaps.create_index("created_at", expireAfterSeconds=30 * 86400)
    # Phase E4.5 — shadow certification campaign (persistent; no TTL)
    await shadow_campaigns.create_index("id", unique=True)
    await shadow_campaigns.create_index([("status", 1), ("created_at", -1)])
    # Phase E4.6 — recovery proof campaigns (persistent; no TTL)
    await recovery_proofs.create_index("id", unique=True)
    await recovery_proofs.create_index([("created_at", -1)])
    # Exchange Intelligence Registry (persistent; no TTL)
    await exchange_intelligence.create_index("exchange", unique=True)
    # Permanent immutable institutional ledger (persistent; no TTL; one entry per cycle)
    await production_ledger.create_index("cycle_id", unique=True)
    await production_ledger.create_index([("completed_at", -1)])
    # E4.7 — opportunity GO-window history (persistent; no TTL)
    await opportunity_windows.create_index("id", unique=True)
    await opportunity_windows.create_index([("route_id", 1), ("status", 1)])
    await opportunity_windows.create_index([("created_at", -1)])
    # Fresh-Cycle Opportunity Analytics — per-tick observations (90d TTL)
    await fresh_cycle_observations.create_index([("route_id", 1), ("created_at", -1)])
    await fresh_cycle_observations.create_index("created_at", expireAfterSeconds=90 * 86400)
