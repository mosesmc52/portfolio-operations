from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from alpaca.trading.client import TradingClient


@dataclass
class BrokerValuation:
    equity: Decimal
    cash: Decimal


class AlpacaValuationService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.client = TradingClient(
            api_key=key_id,
            secret_key=secret_key,
            url_override=base_url,
        )

    def get_account_valuation(self) -> BrokerValuation:
        acct = self.client.get_account()

        # alpaca-py account fields are strings (Decimal-safe)
        equity = Decimal(acct.equity)
        cash = Decimal(acct.cash)

        return BrokerValuation(
            equity=equity,
            cash=cash,
        )
