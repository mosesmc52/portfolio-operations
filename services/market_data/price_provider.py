from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Tuple

import pandas as pd


@dataclass
class PriceSeries:
    dates: List[date]
    close: List[float]


class YFinancePriceProvider:
    """
    MVP provider for benchmark prices.
    Replace later with a DB-backed provider.
    """

    def get_daily_close(self, *, symbol: str, start: date, end: date) -> PriceSeries:
        import yfinance as yf

        df = yf.download(
            symbol, start=str(start), end=str(end), auto_adjust=True, progress=False
        )
        if df is None or df.empty:
            return PriceSeries(dates=[], close=[])

        # yfinance index is datetime; convert to date
        df.columns = df.columns.droplevel(1)
        df = df.reset_index()
        dates = [d.date() for d in df["Date"].tolist()]
        close = [float(x) for x in df["Close"].tolist()]
        return PriceSeries(dates=dates, close=close)
