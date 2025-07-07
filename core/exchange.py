import ccxt.async_support as ccxt
from pydantic import BaseModel
from typing import Any

class ExchWrapper(BaseModel):
    id: str
    symbol: str
    ccxt_ex: Any | None = None

    async def init(self, keys: dict):
        klass = getattr(ccxt, self.id)
        self.ccxt_ex = klass({
            "apiKey": keys[self.id]["key"],
            "secret": keys[self.id]["secret"],
            "enableRateLimit": True,
        })
        if hasattr(self.ccxt_ex, "load_markets"):
            await self.ccxt_ex.load_markets()

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
