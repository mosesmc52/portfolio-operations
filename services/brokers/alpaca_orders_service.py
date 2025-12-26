from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import alpaca_trade_api as tradeapi


@dataclass
class AlpacaOrderFill:
    external_order_id: str
    external_fill_id: str  # you can treat order.id as fill_id in this simplified model
    symbol: str
    side: str
    filled_qty: float
    filled_avg_price: float
    filled_at: datetime
    raw: Dict[str, Any]


class AlpacaOrdersService:
    """
    Alpaca API wrapper for retrieving filled orders.
    No Django imports here.
    """

    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.api = tradeapi.REST(key_id, secret_key, base_url, api_version="v2")

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def list_filled_orders_last_days(
        self, *, days: int, limit: int = 500
    ) -> List[AlpacaOrderFill]:
        """
        Returns filled orders from the last N days.
        Uses Alpaca 'orders' endpoint. One record per filled order.
        """
        now_utc = datetime.now(timezone.utc)
        after = now_utc - timedelta(days=days)

        # Alpaca expects RFC3339 timestamps.
        after_str = after.isoformat()
        until_str = now_utc.isoformat()

        # 'closed' includes filled/canceled; we filter to filled with filled_at
        orders = self.api.list_orders(
            status="closed",
            after=after_str,
            until=until_str,
            direction="asc",
            limit=limit,
            nested=True,
        )

        out: List[AlpacaOrderFill] = []
        for o in orders:
            # alpaca_trade_api returns objects; ._raw contains dict
            raw = getattr(o, "_raw", None) or {}
            status = raw.get("status") or getattr(o, "status", None)

            filled_at = raw.get("filled_at") or getattr(o, "filled_at", None)
            if not filled_at:
                continue
            # filled_at might be string; alpaca_trade_api often parses but not always
            if isinstance(filled_at, str):
                filled_at_dt = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
            else:
                filled_at_dt = filled_at

            if status != "filled":
                continue

            symbol = raw.get("symbol") or getattr(o, "symbol", None)
            side = raw.get("side") or getattr(o, "side", None)

            filled_qty = raw.get("filled_qty") or getattr(o, "filled_qty", None)
            filled_avg_price = raw.get("filled_avg_price") or getattr(
                o, "filled_avg_price", None
            )

            if not symbol or not side or not filled_qty or not filled_avg_price:
                continue

            external_order_id = raw.get("id") or getattr(o, "id", None)
            if not external_order_id:
                continue

            out.append(
                AlpacaOrderFill(
                    external_order_id=str(external_order_id),
                    external_fill_id=str(
                        external_order_id
                    ),  # simplified: one fill per order
                    symbol=str(symbol),
                    side=str(side),
                    filled_qty=float(filled_qty),
                    filled_avg_price=float(filled_avg_price),
                    filled_at=self._as_utc(filled_at_dt),
                    raw=raw,
                )
            )

        return out
