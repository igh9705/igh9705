# core/feed.py
import asyncio, json, logging, decimal as D
import websockets


class AbstractFeed:
    def __init__(self, q: asyncio.Queue):
        self.q   = q
        self.log = logging.getLogger(self.__class__.__name__)


# ────────────────────────────── Upbit (현물)
class UpbitFeed(AbstractFeed):
    URL = "wss://api.upbit.com/websocket/v1"

    def __init__(self,
                 q: asyncio.Queue,
                 symbol: str = "USDT-BTC",          # “거래통화-기준통화”
                 depth: int = 1):                   # 1 레벨 호가만
        super().__init__(q)
        self.symbol = symbol
        self.depth  = depth
        self.topic  = "orderbook"                  # 구독 타입

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.URL, ping_interval=20) as ws:
                    sub = [
                        {"ticket": "feed"},
                        {"type": "orderbook", "codes": [self.symbol], "depth": 1}
                    ]
                    await ws.send(json.dumps(sub))
                    self.log.info("WS connected")

                    async for raw in ws:
                        j = json.loads(raw)

                        if j.get("type") != "orderbook":
                            continue

                        units = j.get("orderbook_units")
                        if not units:
                            continue

                        best = units[0]  # 1‑레벨
                        ask = D.Decimal(best["ask_price"])
                        bid = D.Decimal(best["bid_price"])

                        await self.q.put({"ex": "spot", "ask": ask, "bid": bid})
            except Exception as e:
                self.log.warning("WS error: %s – reconnect in 5 s", e)
                await asyncio.sleep(5)


# ────────────────────────────── Binance USDT‑Perp (선물)
class BinanceFeed(AbstractFeed):
    URL_BASE = "wss://fstream.binance.com/ws"

    def __init__(self,
                 q: asyncio.Queue,
                 stream: str = "btcusdt@bookTicker"):
        super().__init__(q)
        self.stream = stream
        self.URL    = f"{self.URL_BASE}/{self.stream}"

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.URL, ping_interval=20) as ws:
                    self.log.info("WS connected")
                    async for raw in ws:
                        j = json.loads(raw)
                        await self.q.put({"ex":"hedge",
                                          "ask_f": D.Decimal(j["a"]),
                                          "bid_f": D.Decimal(j["b"])})
            except Exception as e:
                self.log.warning("WS error: %s – reconnect in 5 s", e)
                await asyncio.sleep(5)
