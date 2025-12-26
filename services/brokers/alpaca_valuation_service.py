from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import alpaca_trade_api as tradeapi


@dataclass
class BrokerValuation:
    equity: Decimal
    cash: Decimal


class AlpacaValuationService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.api = tradeapi.REST(key_id, secret_key, base_url, api_version="v2")

    def get_account_valuation(self) -> BrokerValuation:
        acct = self.api.get_account()
        # alpaca fields are strings
        equity = Decimal(str(getattr(acct, "equity")))
        cash = Decimal(str(getattr(acct, "cash")))
        return BrokerValuation(equity=equity, cash=cash)
