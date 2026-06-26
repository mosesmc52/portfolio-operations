from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetPortfolioHistoryRequest


@dataclass
class PortfolioHistoryPoint:
    as_of_datetime: datetime
    equity: Decimal
    profit_loss: Decimal
    profit_loss_pct: Decimal | None
    base_value: Decimal | None
    timeframe: str
    raw: dict[str, Any]


class AlpacaPortfolioHistoryService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.client = TradingClient(
            api_key=key_id,
            secret_key=secret_key,
            url_override=base_url,
        )

    def get_daily_portfolio_history(self, *, period: str = "1A") -> list[PortfolioHistoryPoint]:
        req = GetPortfolioHistoryRequest(period=period, timeframe="1D")
        history = self.client.get_portfolio_history(req)

        timestamps = list(getattr(history, "timestamp", []) or [])
        equities = list(getattr(history, "equity", []) or [])
        pnl = list(getattr(history, "profit_loss", []) or [])
        pnl_pct = list(getattr(history, "profit_loss_pct", []) or [])
        base_value = getattr(history, "base_value", None)
        timeframe = getattr(history, "timeframe", "1D") or "1D"

        points: list[PortfolioHistoryPoint] = []
        for idx, ts in enumerate(timestamps):
            if idx >= len(equities) or idx >= len(pnl):
                continue
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            pct = None
            if idx < len(pnl_pct) and pnl_pct[idx] is not None:
                pct = Decimal(str(pnl_pct[idx]))
            point = PortfolioHistoryPoint(
                as_of_datetime=dt,
                equity=Decimal(str(equities[idx])),
                profit_loss=Decimal(str(pnl[idx])),
                profit_loss_pct=pct,
                base_value=Decimal(str(base_value)) if base_value is not None else None,
                timeframe=timeframe,
                raw={
                    "timestamp": int(ts),
                    "equity": equities[idx],
                    "profit_loss": pnl[idx],
                    "profit_loss_pct": pnl_pct[idx] if idx < len(pnl_pct) else None,
                    "base_value": base_value,
                    "timeframe": timeframe,
                },
            )
            points.append(point)

        return points
