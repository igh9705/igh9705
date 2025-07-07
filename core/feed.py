import asyncio, json, websockets, decimal as D
from abc import ABC, abstractmethod

class AbstractFeed(ABC):
    def __init__(self, q: asyncio.Queue):      # market_q 주입
        self.q = q
    @abstractmethod
    async def run(self): ...

class UpbitFeed(AbstractFeed):
    URL = "wss://api.upbit.com/websocket/v1"
    def __init__(self, q, symbol="USDT-BTC"):
        super().__init__(q); self.sym = symbol
    async def run(self):
        sub = [{"ticket":"t"},{"type":"orderbook","codes":[self.sym]}]
        async with websockets.connect(self.URL, ping_interval=20) as ws:
            await ws.send(json.dumps(sub))
            async for msg in ws:
                data = json.loads(msg)
                best = data["obu"][0]
                await self.q.put({"ex":"spot",
                                  "bid": D.Decimal(best["bid_price"]),
                                  "ask": D.Decimal(best["ask_price"])})

class BinanceFeed(AbstractFeed):
    def __init__(self, q, stream="btcusdt@bookTicker"):
        super().__init__(q); self.url=f"wss://stream.binance.com:9443/ws/{stream}"
    async def run(self):
        async with websockets.connect(self.url) as ws:
            async for raw in ws:
                j = json.loads(raw)
                await self.q.put({"ex":"hedge",
                                  "bid_f": D.Decimal(j["b"]),
                                  "ask_f": D.Decimal(j["a"])})

class BybitFeed(AbstractFeed):
    URL = "wss://stream.bybit.com/v5/public/linear"
    def __init__(self, q, topic="orderbook.1.BTCUSDT"):
        super().__init__(q); self.topic = topic
    async def run(self):
        async with websockets.connect(self.URL) as ws:
            await ws.send(json.dumps({"op":"subscribe","args":[self.topic]}))
            async for raw in ws:
                j=json.loads(raw)
                if j.get("topic")!=self.topic: continue
                best = j["data"]["a"][0], j["data"]["b"][0]
                await self.q.put({"ex":"hedge",
                                  "ask_f": D.Decimal(best[0][0]),
                                  "bid_f": D.Decimal(best[1][0])})
