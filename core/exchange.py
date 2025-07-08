import ccxt.async_support as ccxt
from pydantic import BaseModel
from typing import Any
import logging

class ExchWrapper(BaseModel):
    id: str
    symbol: str
    ccxt_ex: Any | None = None

    async def init(self, keys: dict):
        klass = getattr(ccxt, self.id)
        api_key = keys.get(f"{self.id.upper()}_KEY")     # 예: UPBIT_KEY
        sec_key = keys.get(f"{self.id.upper()}_SECRET")  # 예: UPBIT_SECRET
        self.ccxt_ex = klass({
            "api_key": api_key,
            "secret": sec_key,
            "enableRateLimit": True,
            "verbose": False
        })
        if hasattr(self.ccxt_ex, "load_markets"):
            await self.ccxt_ex.load_markets()
        log = logging.getLogger(f"ExchWrapper[{self.id}]")
        try:
            await self.ccxt_ex.fetch_ticker(self.symbol)   # ping
            log.info("REST auth OK")
        except Exception as e:
            log.error("REST auth FAIL: %s", e, exc_info=True)
            raise

    async def limit(self, side: str, amount: float, price: float):
        fn = self.ccxt_ex.create_limit_buy_order if side == "buy" \
             else self.ccxt_ex.create_limit_sell_order
        return await fn(self.symbol, amount, price)

    async def market(self, side: str, amount: float):
        fn = self.ccxt_ex.create_market_buy_order if side == "buy" \
             else self.ccxt_ex.create_market_sell_order
        return await fn(self.symbol, amount)

    async def cancel(self, order_id: str):
        return await self.ccxt_ex.cancel_order(order_id, self.symbol)
