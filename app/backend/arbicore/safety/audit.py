"""AuditLog — MID-backed append-only audit trail."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..data.mid.writers import MidWriter, make_meta

logger = logging.getLogger(__name__)


class AuditLog:
    """Every safety decision, kill-switch change, approval verdict,
    and config-file reload lands here via ``mid_opportunities`` with an
    ``audit.*`` ``event_type`` prefix — reusing the canonical MID
    substrate instead of a separate collection."""

    def __init__(self, writer: MidWriter) -> None:
        self._writer = writer

    async def log(self, *, event: str, by: str,
                  payload: Optional[Dict[str, Any]] = None,
                  opp_id: str = "__audit__") -> None:
        try:
            meta = make_meta(execution_mode="audit")
            await self._writer.write_opportunity_event(
                opp_id=opp_id,
                event_type=f"audit.{event}",
                payload={"by": by, **(payload or {})},
                meta=meta,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("audit log failed: %s", exc)
