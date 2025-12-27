from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus  # <-- FIX
from alpaca.trading.requests import GetOrdersRequest


@dataclass
class AlpacaOrderFill:
    external_order_id: str
    external_fill_id: str
    symbol: str
    side: str
    filled_qty: float
    filled_avg_price: float
    filled_at: datetime
    raw: Dict[str, Any]


class AlpacaOrdersService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.client = TradingClient(
            api_key=key_id,
            secret_key=secret_key,
            url_override=base_url,
        )

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    def list_filled_orders_last_days(
        self, *, days: int, limit: int = 500
    ) -> List[AlpacaOrderFill]:
        now_utc = datetime.now(timezone.utc)
        after = now_utc - timedelta(days=days)

        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,  # <-- FIX
            after=after,
            until=now_utc,
            direction="asc",  # alpaca-py expects "asc"/"desc"
            limit=limit,
            nested=True,
        )

        orders = self.client.get_orders(req)

        out: List[AlpacaOrderFill] = []
        for o in orders:
            raw = o.model_dump() if hasattr(o, "model_dump") else {}

            # Filter to FILLED orders specifically
            status = raw.get("status") or getattr(o, "status", None)
            if str(status) != "filled":
                continue

            filled_at = raw.get("filled_at") or getattr(o, "filled_at", None)
            filled_at_dt = self._parse_dt(filled_at)
            if not filled_at_dt:
                continue

            symbol = raw.get("symbol") or getattr(o, "symbol", None)
            side = raw.get("side") or getattr(o, "side", None)
            filled_qty = raw.get("filled_qty") or getattr(o, "filled_qty", None)
            filled_avg_price = raw.get("filled_avg_price") or getattr(
                o, "filled_avg_price", None
            )

            if (
                not symbol
                or not side
                or filled_qty in (None, "", 0)
                or filled_avg_price in (None, "", 0)
            ):
                continue

            external_order_id = raw.get("id") or getattr(o, "id", None)
            if not external_order_id:
                continue

            out.append(
                AlpacaOrderFill(
                    external_order_id=str(external_order_id),
                    external_fill_id=str(external_order_id),
                    symbol=str(symbol),
                    side=str(side),
                    filled_qty=float(filled_qty),
                    filled_avg_price=float(filled_avg_price),
                    filled_at=self._as_utc(filled_at_dt),
                    raw=raw,
                )
            )

        return out
